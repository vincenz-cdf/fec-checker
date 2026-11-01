"""Input helpers of the Actor entry point."""

from __future__ import annotations

import unittest
from datetime import date

from my_actor.fec.report import build_report
from my_actor.fec.validator import FecValidator
from my_actor.main import (
    DEMO_FILE,
    InputError,
    apify_record_location,
    file_name_from_response,
    parse_fiscal_year_end,
)


class TestDemoFile(unittest.TestCase):
    def test_demo_file_is_bundled_and_shows_findings(self) -> None:
        self.assertTrue(DEMO_FILE.is_file())
        report = build_report(FecValidator(DEMO_FILE, DEMO_FILE.name).run(), 'en')
        self.assertEqual(report['verdict'], 'invalid')
        self.assertTrue(report['errors'])
        self.assertTrue(report['warnings'])
        self.assertTrue(report['riskSignals'])


class TestUploadedFileLocation(unittest.TestCase):
    def test_apify_record(self) -> None:
        url = 'https://api.apify.com/v2/key-value-stores/aBc123/records/fec-123456782FEC20251231.txt?signature=x'
        self.assertEqual(apify_record_location(url), ('aBc123', 'fec-123456782FEC20251231.txt'))

    def test_username_store_and_encoded_key(self) -> None:
        url = 'https://api.apify.com/v2/key-value-stores/vince~uploads/records/my%20file.txt'
        self.assertEqual(apify_record_location(url), ('vince~uploads', 'my file.txt'))

    def test_external_urls_are_never_deleted(self) -> None:
        for url in (
            'https://example.com/v2/key-value-stores/abc/records/x',
            'http://api.apify.com/v2/key-value-stores/abc/records/x',
            'https://api.apify.com.evil.com/v2/key-value-stores/abc/records/x',
            'https://api.apify.com/v2/datasets/abc/items',
            'C:/files/123456782FEC20251231.txt',
        ):
            self.assertIsNone(apify_record_location(url), url)


class TestInputHelpers(unittest.TestCase):
    def test_fiscal_year_end(self) -> None:
        self.assertIsNone(parse_fiscal_year_end(None))
        self.assertIsNone(parse_fiscal_year_end(''))
        self.assertEqual(parse_fiscal_year_end('2025-12-31'), date(2025, 12, 31))
        self.assertEqual(parse_fiscal_year_end('2025-12-31T00:00:00.000Z'), date(2025, 12, 31))
        with self.assertRaises(InputError):
            parse_fiscal_year_end('31/12/2025')
        with self.assertRaises(InputError):
            parse_fiscal_year_end(20251231)

    def test_file_name_from_url(self) -> None:
        self.assertEqual(
            file_name_from_response('https://example.com/files/123456782FEC20251231.txt?sig=1', None),
            '123456782FEC20251231.txt',
        )
        self.assertEqual(file_name_from_response('https://example.com/a%20b.txt', None), 'a b.txt')

    def test_file_name_from_content_disposition(self) -> None:
        url = 'https://api.apify.com/v2/key-value-stores/abc/records/xyz'
        self.assertEqual(
            file_name_from_response(url, 'attachment; filename="123456782FEC20251231.txt"'),
            '123456782FEC20251231.txt',
        )
        self.assertEqual(
            file_name_from_response(url, "attachment; filename*=UTF-8''FEC%20export.txt"),
            'FEC export.txt',
        )
        self.assertEqual(file_name_from_response(url, 'attachment; filename="../../etc/passwd"'), 'passwd')


if __name__ == '__main__':
    unittest.main()
