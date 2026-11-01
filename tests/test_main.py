"""Input helpers of the Actor entry point."""

from __future__ import annotations

import unittest
from datetime import date

from my_actor.main import InputError, file_name_from_response, parse_fiscal_year_end


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
