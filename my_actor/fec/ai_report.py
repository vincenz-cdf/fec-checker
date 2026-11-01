"""AI-written fix list. Only the sanitized report (see `report_for_llm`) is sent, never file rows."""

from __future__ import annotations

import json

import anthropic

DEFAULT_MODEL = 'claude-opus-5-5'

SYSTEM_PROMPT = """You are a French chartered accountant (expert-comptable) who reviews FEC files \
(Fichier des Écritures Comptables, art. A47 A-1 of the Livre des procédures fiscales) before they are \
handed to the tax administration.

You receive the JSON report of an automated FEC check: errors, warnings and risk signals, each with a \
rule code, an occurrence count and sample line numbers. You never see the file itself.

Write a prioritized fix list for the person who must correct and regenerate the file. Put blocking \
format errors first (a file with them can be rejected during a tax audit), then balance and numbering \
problems, then warnings and risk signals. Group related rules into one fix when one change in the \
accounting software solves them. Say where the fix is usually made (export settings of the accounting \
software, the entries themselves, or year-end closing). Cite line numbers from the report when they \
help. Do not invent problems the report does not contain. If the report has no errors, warnings or \
signals, say the file looks ready and return an empty fix list."""

OUTPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {'type': 'string'},
        'fixes': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'priority': {'type': 'integer'},
                    'severity': {'type': 'string', 'enum': ['blocking', 'major', 'minor']},
                    'title': {'type': 'string'},
                    'rules': {'type': 'array', 'items': {'type': 'string'}},
                    'action': {'type': 'string'},
                    'where': {'type': 'string'},
                },
                'required': ['priority', 'severity', 'title', 'rules', 'action', 'where'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['summary', 'fixes'],
    'additionalProperties': False,
}

LANGUAGE_NAMES = {'fr': 'French', 'en': 'English'}


class AiReportError(Exception):
    pass


async def generate_ai_report(llm_report: dict, language: str, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=3, timeout=300)
    try:
        response = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            output_config={
                'effort': 'medium',
                'format': {'type': 'json_schema', 'schema': OUTPUT_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[{
                'role': 'user',
                'content': (
                    f'Write the summary and every fix in {LANGUAGE_NAMES[language]}.\n\n'
                    f'<fec_check_report>\n{json.dumps(llm_report, ensure_ascii=False)}\n</fec_check_report>'
                ),
            }],
        )
    except anthropic.AuthenticationError as e:
        raise AiReportError('Invalid ANTHROPIC_API_KEY') from e
    except anthropic.RateLimitError as e:
        raise AiReportError('Anthropic API rate limit reached') from e
    except anthropic.APIStatusError as e:
        raise AiReportError(f'Anthropic API error {e.status_code}') from e
    except anthropic.APIConnectionError as e:
        raise AiReportError('Could not reach the Anthropic API') from e
    finally:
        await client.close()

    if response.stop_reason == 'refusal':
        raise AiReportError('The model declined to write the report')
    if response.stop_reason == 'max_tokens':
        raise AiReportError('The AI report was cut off (max_tokens)')
    text = next((b.text for b in response.content if b.type == 'text'), None)
    if text is None:
        raise AiReportError('The model returned no text')
    data = json.loads(text)
    data['fixes'].sort(key=lambda f: f['priority'])
    return {'model': response.model, **data}
