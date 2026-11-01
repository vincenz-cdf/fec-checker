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
from my_actor.fec.inputfile import NotAFecError, prepare_input
from my_actor.fec.report import build_report, report_for_llm
from my_actor.fec.validator import FecValidator

DEMO_FILE = Path(__file__).resolve().parent / 'demo' / '123456782FEC20251231.txt'
APIFY_RECORD_RE = re.compile(r'^https://api\.apify\.com/v2/key-value-stores/([A-Za-z0-9~._-]+)/records/([^/?#]+)')
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
            source = actor_input.get('fecFile') or ''
            if not isinstance(source, str):
                raise InputError('fecFile must be a URL or an uploaded file')
            source = source.strip()
            demo = not source
            language = actor_input.get('language', 'fr')
            if language not in ('fr', 'en'):
                raise InputError('language must be "fr" or "en"')
            include_ai = bool(actor_input.get('includeAiReport', False))
            fiscal_year_end = parse_fiscal_year_end(actor_input.get('fiscalYearEnd'))
            file_name_override = (actor_input.get('fileName') or '').strip()
            max_issues = int(actor_input.get('maxIssuesPerRule', 50))
            if not 1 <= max_issues <= 10_000:
                raise InputError('maxIssuesPerRule must be between 1 and 10000')
            delete_upload = bool(actor_input.get('deleteUploadedFile', True))
        except (InputError, ValueError, TypeError) as e:
            await Actor.fail(status_message=str(e))
            return

        charging = Actor.get_charging_manager()
        if not demo and charging.is_event_charge_limit_reached(EVENT_FILE_CHECKED):
            await Actor.fail(status_message='The maximum cost per run does not allow checking a file.')
            return

        max_bytes = int(os.environ.get('FEC_MAX_FILE_MB', '2048')) * (1 << 20)
        workdir = Path(tempfile.mkdtemp(prefix='fec-'))
        try:
            if demo:
                Actor.log.info('No fecFile given: checking the bundled demo file (synthetic data, not charged)')
                path, served_name = DEMO_FILE, DEMO_FILE.name
            else:
                await Actor.set_status_message('Downloading the FEC file')
                try:
                    path, served_name = await fetch_input_file(source, workdir, max_bytes)
                except InputError as e:
                    await Actor.fail(status_message=str(e))
                    return
                except OSError as e:
                    await Actor.fail(status_message=f'Could not download fecFile: {e.__class__.__name__}')
                    return
                try:
                    path, inner_name = await asyncio.to_thread(prepare_input, path, workdir, max_bytes)
                except NotAFecError as e:
                    # Refused before the check, so nothing is charged.
                    await Actor.fail(status_message=str(e))
                    return
                if inner_name:
                    Actor.log.info('Unzipped the FEC from the uploaded archive')
                    served_name = inner_name
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
        report['demo'] = demo
        if not demo:
            await Actor.charge(EVENT_FILE_CHECKED)
        Actor.log.info(
            f'Verdict {report["verdict"]}, score {report["score"]}: {report["summary"]["errorCount"]} errors, '
            f'{report["summary"]["warningCount"]} warnings, {report["summary"]["riskSignalCount"]} risk signals '
            f'in {result.stats["lineCount"]:,} lines'
        )

        if include_ai:
            report['aiSummary'] = await build_ai_summary(report, language)

        # Only the report is kept: the local copy is already gone, now remove the uploaded original.
        report['uploadedFileDeleted'] = await delete_uploaded_file(source) if delete_upload and not demo else False

        await Actor.push_data(report)
        await Actor.set_value('REPORT', report)
        await Actor.set_status_message(f'{report["verdict"]} (score {report["score"]}/100)')


def apify_record_location(url: str) -> tuple[str, str] | None:
    """(store id, record key) when the URL is a record in an Apify key-value store, else None."""
    match = APIFY_RECORD_RE.match(url)
    if not match:
        return None
    return match.group(1), urllib.parse.unquote(match.group(2))


async def delete_uploaded_file(source: str) -> bool:
    """Delete a file uploaded through the input form. External URLs are never touched."""
    location = apify_record_location(source)
    if location is None or not Actor.is_at_home():
        return False
    store_id, key = location
    if key == 'INPUT':
        return False
    try:
        await Actor.apify_client.key_value_store(store_id).delete_record(key)
    except Exception as e:  # noqa: BLE001 - deletion is best effort and must not fail the run
        Actor.log.warning(f'Could not delete the uploaded file ({e.__class__.__name__}); delete it from your storage')
        return False
    Actor.log.info('Deleted the uploaded file from your key-value store')
    return True


async def build_ai_summary(report: dict, language: str) -> dict:
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
