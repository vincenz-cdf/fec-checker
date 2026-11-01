"""AI report call, with the Anthropic client replaced by a fake (no network, no key)."""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from my_actor.fec import ai_report
from my_actor.fec.ai_report import AiReportError, generate_ai_report

PAYLOAD = {'verdict': 'invalid', 'errors': [{'rule': 'num_gap', 'count': 1, 'lines': [12]}]}


def fake_client(response: SimpleNamespace, calls: list[dict]) -> mock.MagicMock:
    async def create(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return response

    async def close() -> None:
        return None

    client = mock.MagicMock()
    client.beta.messages.create = create
    client.close = close
    return client


def text_response(data: dict, stop_reason: str = 'end_turn') -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        model='claude-opus-5-5',
        content=[SimpleNamespace(type='thinking', thinking=''), SimpleNamespace(type='text', text=json.dumps(data))],
    )


class TestAiReport(unittest.TestCase):
    def run_with(self, response: SimpleNamespace, language: str = 'fr', **kwargs: str) -> tuple[dict, list[dict]]:
        calls: list[dict] = []
        with mock.patch.object(ai_report.anthropic, 'AsyncAnthropic', return_value=fake_client(response, calls)):
            result = asyncio.run(generate_ai_report(PAYLOAD, language, 'test-key', **kwargs))
        return result, calls

    def test_request_and_parsing(self) -> None:
        data = {'summary': 'Corriger la numérotation.', 'fixes': [
            {'priority': 2, 'severity': 'minor', 'title': 'B', 'rules': [], 'action': 'b', 'where': 'x'},
            {'priority': 1, 'severity': 'blocking', 'title': 'A', 'rules': ['num_gap'], 'action': 'a', 'where': 'y'},
        ]}
        result, calls = self.run_with(text_response(data))
        self.assertEqual([f['title'] for f in result['fixes']], ['A', 'B'])  # sorted by priority
        self.assertEqual(result['model'], 'claude-opus-5-5')  # the model the response reports

        sent = calls[0]
        self.assertEqual(sent['model'], 'claude-haiku-5-5')
        self.assertNotIn('fallbacks', sent)  # Haiku has no server-side fallback
        self.assertNotIn('betas', sent)
        self.assertEqual(sent['output_config']['format']['type'], 'json_schema')
        user_text = sent['messages'][0]['content']
        self.assertIn('French', user_text)
        self.assertIn(json.dumps(PAYLOAD, ensure_ascii=False), user_text)

    def test_fallback_is_sent_to_models_that_support_it(self) -> None:
        for model in ('claude-sonnet-5-5', 'claude-opus-5-5'):
            _, calls = self.run_with(text_response({'summary': 'ok', 'fixes': []}), model=model)
            self.assertEqual(calls[0]['model'], model)
            self.assertEqual(calls[0]['fallbacks'], 'default')
            self.assertEqual(calls[0]['betas'], ['server-side-fallback-2026-07-01'])

    def test_english(self) -> None:
        _, calls = self.run_with(text_response({'summary': 'ok', 'fixes': []}), language='en')
        self.assertIn('English', calls[0]['messages'][0]['content'])

    def test_refusal(self) -> None:
        with self.assertRaises(AiReportError):
            self.run_with(text_response({}, stop_reason='refusal'))

    def test_truncated(self) -> None:
        with self.assertRaises(AiReportError):
            self.run_with(text_response({}, stop_reason='max_tokens'))


if __name__ == '__main__':
    unittest.main()
