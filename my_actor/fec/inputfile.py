"""Decide whether an uploaded file can be checked, before any check runs (and before anything is charged).

A zip holding one .txt FEC is unpacked. PDFs, spreadsheets, images and other binary files are refused
with a message that says what was received.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

SNIFF_BYTES = 64 * 1024

# Leading bytes of common formats people upload by mistake.
MAGIC = (
    (b'%PDF', 'a PDF document'),
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'an old Excel or Word file (.xls/.doc)'),
    (b'\x89PNG', 'a PNG image'),
    (b'\xff\xd8\xff', 'a JPEG image'),
    (b'GIF8', 'a GIF image'),
    (b'\x1f\x8b', 'a gzip archive'),
    (b'Rar!', 'a RAR archive'),
    (b"7z\xbc\xaf'\x1c", 'a 7-Zip archive'),
    (b'<?xml', 'an XML file (only the flat-file FEC is supported, not the XML variant)'),
)


class NotAFecError(Exception):
    """The file cannot be a flat-file FEC. The message is shown to the user as the run's status."""


def utf16_variant(head: bytes) -> str | None:
    """'utf-16' (with BOM), 'utf-16-le' or 'utf-16-be' when the bytes look like UTF-16 text, else None."""
    if head.startswith((b'\xff\xfe', b'\xfe\xff')):
        return 'utf-16'
    sample = head[:4096]
    if len(sample) < 16:
        return None
    even_zeros = sample[0::2].count(0)
    odd_zeros = sample[1::2].count(0)
    half = len(sample) / 2
    if odd_zeros > 0.4 * half and even_zeros < 0.05 * half:
        return 'utf-16-le'
    if even_zeros > 0.4 * half and odd_zeros < 0.05 * half:
        return 'utf-16-be'
    return None


def _describe_binary(head: bytes) -> str | None:
    for magic, label in MAGIC:
        if head.startswith(magic):
            return label
    if b'\x00' in head and utf16_variant(head) is None:
        return 'a binary file'
    return None


def _unzip_single_fec(path: Path, workdir: Path, max_bytes: int) -> tuple[Path, str]:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise NotAFecError('The file looks like a zip archive but cannot be opened.') from e
    with archive:
        names = [i for i in archive.infolist() if not i.is_dir()]
        if any(i.filename == '[Content_Types].xml' for i in names):
            raise NotAFecError(
                'The file is an Excel or Word document (.xlsx/.docx), not a FEC. '
                'Export the FEC from your accounting software as a .txt file.'
            )
        fecs = [i for i in names if i.filename.lower().endswith('.txt') and not Path(i.filename).name.startswith('.')]
        if len(fecs) != 1:
            raise NotAFecError(
                f'The zip archive must contain exactly one .txt FEC file; it contains {len(fecs)}. '
                'Upload the FEC file itself, or a zip holding only that file.'
            )
        info = fecs[0]
        if info.flag_bits & 0x1:
            raise NotAFecError('The zip archive is password-protected. Upload the FEC file itself.')
        if info.file_size > max_bytes:
            raise NotAFecError(f'The FEC inside the zip is larger than the {max_bytes // (1 << 20)} MB limit.')
        target = workdir / 'unzipped.fec'  # fixed name: the archive's paths are never used on disk
        written = 0
        with archive.open(info) as src, target.open('wb') as dst:
            while chunk := src.read(1 << 20):
                written += len(chunk)
                if written > max_bytes:  # sizes in the zip header can lie
                    raise NotAFecError(f'The FEC inside the zip is larger than the {max_bytes // (1 << 20)} MB limit.')
                dst.write(chunk)
        return target, Path(info.filename).name


def prepare_input(path: Path, workdir: Path, max_bytes: int) -> tuple[Path, str | None]:
    """Return the file to check and, for a zip, the name of the FEC inside it.

    Raises NotAFecError when the file is obviously not a flat-file FEC.
    """
    with path.open('rb') as f:
        head = f.read(SNIFF_BYTES)
    if not head.strip():
        raise NotAFecError('The file is empty.')
    if head.startswith(b'PK\x03\x04'):
        inner_path, inner_name = _unzip_single_fec(path, workdir, max_bytes)
        with inner_path.open('rb') as f:
            inner_head = f.read(SNIFF_BYTES)
        label = _describe_binary(inner_head)
        if label:
            raise NotAFecError(f'The file inside the zip is {label}, not a FEC text file.')
        return inner_path, inner_name
    label = _describe_binary(head)
    if label:
        raise NotAFecError(
            f'The file is {label}, not a FEC. '
            'Export the FEC from your accounting software as a tab- or pipe-separated .txt file.'
        )
    return path, None
