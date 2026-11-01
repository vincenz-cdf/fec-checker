"""Uploads that are not plain .txt FECs: zip, UTF-16, semicolons, and files that are not a FEC at all."""

from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from helpers import GOOD_NAME, HEADERS, check, counts, entry
from my_actor.fec.inputfile import NotAFecError, prepare_input, utf16_variant
from my_actor.fec.validator import FecValidator

ROWS = entry('1') + entry('2')
FEC_TEXT = '\r\n'.join(['|'.join(HEADERS)] + ['|'.join(r) for r in ROWS]) + '\r\n'


def write(data: bytes, name: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix='fec-in-')) / name
    path.write_bytes(data)
    return path


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def prepare(data: bytes, name: str = 'upload.bin', max_bytes: int = 1 << 30) -> tuple[Path, str | None]:
    return prepare_input(write(data, name), Path(tempfile.mkdtemp(prefix='fec-work-')), max_bytes)


class TestPlainText(unittest.TestCase):
    def test_text_passes_through(self) -> None:
        path, inner = prepare(FEC_TEXT.encode('utf-8'), GOOD_NAME)
        self.assertIsNone(inner)
        self.assertEqual(path.name, GOOD_NAME)

    def test_csv_extension_is_checked_but_fails_the_name_rule(self) -> None:
        path, _ = prepare(FEC_TEXT.encode('utf-8'), '123456782FEC20251231.csv')
        self.assertEqual(counts(FecValidator(path, path.name).run()), {'file_name': 1})

    def test_upper_case_extension_is_accepted(self) -> None:
        path, _ = prepare(FEC_TEXT.encode('utf-8'), '123456782FEC20251231.TXT')
        self.assertEqual(counts(FecValidator(path, path.name).run()), {})


class TestZip(unittest.TestCase):
    def test_single_fec_is_unzipped(self) -> None:
        path, inner = prepare(zipped({'export/123456782FEC20251231.txt': FEC_TEXT.encode('utf-8')}), 'fec.zip')
        self.assertEqual(inner, GOOD_NAME)  # folders in the archive are dropped
        self.assertEqual(path.name, 'unzipped.fec')
        self.assertEqual(counts(FecValidator(path, inner).run()), {})

    def test_mac_metadata_is_ignored(self) -> None:
        data = zipped({GOOD_NAME: FEC_TEXT.encode('utf-8'), '__MACOSX/._x.txt': b'\x00\x05', '.hidden.txt': b'x'})
        # '__MACOSX/._x.txt' has a dot-name and '.hidden.txt' too: only the FEC counts.
        _, inner = prepare(data, 'fec.zip')
        self.assertEqual(inner, GOOD_NAME)

    def test_several_txt_files_are_refused(self) -> None:
        data = zipped({'a.txt': b'x', 'b.txt': b'y'})
        with self.assertRaisesRegex(NotAFecError, 'exactly one .txt'):
            prepare(data, 'fec.zip')

    def test_no_txt_file_is_refused(self) -> None:
        with self.assertRaisesRegex(NotAFecError, 'contains 0'):
            prepare(zipped({'notes.csv': b'x'}), 'fec.zip')

    def test_xlsx_is_refused(self) -> None:
        data = zipped({'[Content_Types].xml': b'<Types/>', 'xl/workbook.xml': b'<workbook/>'})
        with self.assertRaisesRegex(NotAFecError, 'Excel or Word'):
            prepare(data, 'fec.xlsx')

    def test_size_limit(self) -> None:
        data = zipped({GOOD_NAME: b'0' * 5000})  # compresses to almost nothing
        with self.assertRaisesRegex(NotAFecError, 'larger than'):
            prepare(data, 'fec.zip', max_bytes=1000)

    def test_binary_inside_zip_is_refused(self) -> None:
        with self.assertRaisesRegex(NotAFecError, 'inside the zip is a PDF'):
            prepare(zipped({GOOD_NAME: b'%PDF-1.7 ...'}), 'fec.zip')

    def test_broken_zip(self) -> None:
        with self.assertRaisesRegex(NotAFecError, 'cannot be opened'):
            prepare(b'PK\x03\x04 not really a zip', 'fec.zip')


class TestNotAFec(unittest.TestCase):
    def test_known_formats(self) -> None:
        cases = {
            b'%PDF-1.7\n': 'PDF',
            b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest': 'old Excel',
            b'\x89PNG\r\n\x1a\n': 'PNG',
            b'\xff\xd8\xff\xe0': 'JPEG',
            b'\x1f\x8b\x08\x00': 'gzip',
            b'<?xml version="1.0"?><fec/>': 'XML',
        }
        for data, label in cases.items():
            with self.assertRaisesRegex(NotAFecError, label):
                prepare(data)

    def test_unknown_binary(self) -> None:
        with self.assertRaisesRegex(NotAFecError, 'binary file'):
            prepare(bytes(range(256)) * 10)

    def test_empty_file(self) -> None:
        with self.assertRaisesRegex(NotAFecError, 'empty'):
            prepare(b'  \r\n')


class TestUtf16(unittest.TestCase):
    def test_detection(self) -> None:
        self.assertEqual(utf16_variant('abc'.encode('utf-16')), 'utf-16')
        self.assertEqual(utf16_variant(('JournalCode\t' * 5).encode('utf-16-le')), 'utf-16-le')
        self.assertEqual(utf16_variant(('JournalCode\t' * 5).encode('utf-16-be')), 'utf-16-be')
        self.assertIsNone(utf16_variant(('JournalCode\t' * 5).encode('utf-8')))

    def test_excel_unicode_export_is_read_with_a_warning(self) -> None:
        for codec in ('utf-16', 'utf-16-le'):
            text = FEC_TEXT.replace('|', '\t')
            path, _ = prepare(text.encode(codec), GOOD_NAME)
            result = FecValidator(path, path.name).run()
            self.assertEqual(counts(result), {'encoding_utf16': 1}, codec)
            self.assertEqual(result.stats['lineCount'], 4)
            self.assertEqual(result.stats['totalDebit'], '200,00')


class TestSemicolon(unittest.TestCase):
    def test_semicolon_separator_has_its_own_rule(self) -> None:
        result = check(ROWS, sep=';')
        self.assertEqual(counts(result), {'separator_semicolon': 1})
        self.assertTrue(result.fatal)

    def test_other_separator_keeps_the_generic_rule(self) -> None:
        self.assertEqual(counts(check(ROWS, sep=',')), {'separator': 1})


if __name__ == '__main__':
    unittest.main()
