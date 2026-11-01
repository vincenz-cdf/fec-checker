"""FEC Checker: validate a French FEC file and output one JSON report."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from apify import Actor, Event

from my_actor.fec.ai_report import DEFAULT_MODEL, AiReportError, generate_ai_report
from my_actor.fec.report import build_report, report_for_llm
from my_actor.fec.validator import FecValidator

EVENT_FILE_CHECKED = 'fec-file-checked'
EVENT_AI_REPORT = 'ai-report'
PROGRESS_LOG_SECONDS = 10
DOWNLOAD_CHUNK = 1 << 20


class InputError(Exception):
    pass


def parse_fiscal_year_end(value: object) -> date | None:
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise InputError('fiscalYearEnd must be a date string (YYYY-MM-DD)')
    try:
        return date.fromisoformat(value[:10])
    except ValueError as e:
        raise InputError(f'fiscalYearEnd is not a valid date: {value[:20]!r}') from e


def file_name_from_response(url: str, content_disposition: str | None) -> str:
    if content_disposition:
        match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", content_disposition, re.IGNORECASE)
        if match:
            return Path(urllib.parse.unquote(match.group(1).strip('"'))).name
        match = re.search(r'filename="?([^";]+)"?', content_disposition, re.IGNORECASE)
        if match:
            return Path(match.group(1)).name
    return Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name


def download(url: str, target: Path, max_bytes: int) -> str:
    """Stream the file to disk (never fully in memory). Returns the file name the server reports."""
    request = urllib.request.Request(url, headers={'User-Agent': 'fec-checker (Apify Actor)'})
    host = urllib.parse.urlparse(url).hostname or ''
    token = os.environ.get('APIFY_TOKEN')
    if token and host == 'api.apify.com':
        # Records uploaded through the input form live in the user's own key-value store.
        # Unredirected, so the token never follows a redirect to another host.
        request.add_unredirected_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(request, timeout=120) as response, target.open('wb') as out:  # noqa: S310
        written = 0
        while chunk := response.read(DOWNLOAD_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise InputError(f'The file is larger than the {max_bytes // (1 << 20)} MB limit')
            out.write(chunk)
        return file_name_from_response(url, response.headers.get('Content-Disposition'))


async def fetch_input_file(source: str, workdir: Path, max_bytes: int) -> tuple[Path, str]:
    scheme = urllib.parse.urlparse(source).scheme.lower()
    if scheme in ('http', 'https'):
        target = workdir / 'input.fec'
        name = await asyncio.to_thread(download, source, target, max_bytes)
        return target, name
    if Actor.is_at_home():
        raise InputError('fecFile must be an http(s) URL or an uploaded file')
    # Local runs (`apify run`) may point at a file on disk.
    path = Path(source)
    if not path.is_file():
        raise InputError(f'fecFile not found: {source}')
    return path, path.name


async def log_progress(validator: FecValidator) -> None:
    while True:
        await asyncio.sleep(PROGRESS_LOG_SECONDS)
        Actor.log.info(f'Checked {validator.lines_read:,} lines...')


async def main() -> None:
    async with Actor:
        validator: FecValidator | None = None

        async def on_aborting(_event_data: object = None) -> None:
            if validator:
                validator.cancel_requested = True
            await Actor.set_value('STATE', {'aborted': True, 'linesRead': validator.lines_read if validator else 0})
            await Actor.exit()

        Actor.on(Event.ABORTING, on_aborting)

        actor_input = await Actor.get_input() or {}
        try:
            source = actor_input.get('fecFile')
            if not isinstance(source, str) or not source.strip():
                raise InputError('fecFile is required (upload a file or paste a URL)')
            language = actor_input.get('language', 'fr')
            if language not in ('fr', 'en'):
                raise InputError('language must be "fr" or "en"')
            include_ai = bool(actor_input.get('includeAiReport', False))
            fiscal_year_end = parse_fiscal_year_end(actor_input.get('fiscalYearEnd'))
            file_name_override = (actor_input.get('fileName') or '').strip()
            max_issues = int(actor_input.get('maxIssuesPerRule', 50))
            if not 1 <= max_issues <= 10_000:
                raise InputError('maxIssuesPerRule must be between 1 and 10000')
        except (InputError, ValueError, TypeError) as e:
            await Actor.fail(status_message=str(e))
            return

        charging = Actor.get_charging_manager()
        if charging.is_event_charge_limit_reached(EVENT_FILE_CHECKED):
            await Actor.fail(status_message='The maximum cost per run does not allow checking a file.')
            return

        max_bytes = int(os.environ.get('FEC_MAX_FILE_MB', '2048')) * (1 << 20)
        workdir = Path(tempfile.mkdtemp(prefix='fec-'))
        try:
            await Actor.set_status_message('Downloading the FEC file')
            try:
                path, served_name = await fetch_input_file(source.strip(), workdir, max_bytes)
            except InputError as e:
                await Actor.fail(status_message=str(e))
                return
            except OSError as e:
                await Actor.fail(status_message=f'Could not download fecFile: {e.__class__.__name__}')
                return
            file_name = file_name_override or served_name
            Actor.log.info(f'Checking {file_name} ({path.stat().st_size:,} bytes)')

            await Actor.set_status_message('Checking the FEC file')
            validator = FecValidator(path, file_name, fiscal_year_end, max_issues)
            progress = asyncio.create_task(log_progress(validator))
            try:
                result = await asyncio.to_thread(validator.run)
            finally:
                progress.cancel()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        report = build_report(result, language)
        await Actor.charge(EVENT_FILE_CHECKED)
        Actor.log.info(
            f'Verdict {report["verdict"]}, score {report["score"]}: {report["summary"]["errorCount"]} errors, '
            f'{report["summary"]["warningCount"]} warnings, {report["summary"]["riskSignalCount"]} risk signals '
            f'in {result.stats["lineCount"]:,} lines'
        )

        if include_ai:
            report['aiReport'] = await build_ai_report(report, language)

        await Actor.push_data(report)
        await Actor.set_value('REPORT', report)
        await Actor.set_status_message(f'{report["verdict"]} (score {report["score"]}/100)')


async def build_ai_report(report: dict, language: str) -> dict:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        Actor.log.warning('includeAiReport is on but ANTHROPIC_API_KEY is not set; skipping the AI report')
        return {'status': 'skipped', 'reason': 'AI report is not configured for this Actor'}
    if Actor.get_charging_manager().is_event_charge_limit_reached(EVENT_AI_REPORT):
        return {'status': 'skipped', 'reason': 'The maximum cost per run does not allow an AI report'}

    await Actor.set_status_message('Writing the AI report')
    model = os.environ.get('FEC_AI_MODEL', DEFAULT_MODEL)
    try:
        ai = await generate_ai_report(report_for_llm(report), language, api_key, model)
    except AiReportError as e:
        Actor.log.warning(f'AI report failed: {e}')
        return {'status': 'failed', 'reason': str(e)}
    await Actor.charge(EVENT_AI_REPORT)
    return {'status': 'ok', **ai}
