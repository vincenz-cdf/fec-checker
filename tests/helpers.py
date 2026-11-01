"""Builders for small in-memory FEC files."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from my_actor.fec.validator import EXPECTED_HEADERS, FecValidator, ValidationResult

GOOD_NAME = '123456782FEC20251231.txt'
HEADERS = list(EXPECTED_HEADERS)


def row(journal: str = 'VE', num: str = '000001', edate: str = '20250310', account: str = '411000',
        debit: str = '0,00', credit: str = '0,00', *, journal_lib: str = 'Ventes', account_lib: str = 'Clients',
        aux_num: str = '', aux_lib: str = '', piece: str = 'F1', piece_date: str | None = None,
        label: str = 'Facture', let: str = '', date_let: str = '', valid: str | None = None,
        fx: str = '', idevise: str = '') -> list[str]:
    return [journal, journal_lib, num, edate, account, account_lib, aux_num, aux_lib, piece,
            piece_date or edate, label, debit, credit, let, date_let, valid or edate, fx, idevise]


def entry(num: str, amount: str = '100,00', edate: str = '20250310', journal: str = 'VE',
          valid: str | None = None, debit_account: str = '411000', credit_account: str = '706000') -> list[list[str]]:
    """A balanced two-line entry."""
    return [
        row(journal, num, edate, debit_account, amount, '0,00', valid=valid),
        row(journal, num, edate, credit_account, '0,00', amount, account_lib='Prestations', valid=valid),
    ]


def write_fec(rows: list[list[str]], *, header: list[str] | None = None, sep: str = '|',
              name: str = GOOD_NAME, encoding: str = 'utf-8', bom: bool = False,
              extra_lines: list[str] | None = None) -> Path:
    directory = Path(tempfile.mkdtemp(prefix='fec-test-'))
    lines = [sep.join(header or HEADERS)] + [sep.join(r) for r in rows] + (extra_lines or [])
    data = ('\r\n'.join(lines) + '\r\n').encode(encoding)
    if bom:
        data = b'\xef\xbb\xbf' + data
    path = directory / name
    path.write_bytes(data)
    return path


def check(rows: list[list[str]], *, fye: date | None = None, max_issues: int = 50, **kwargs) -> ValidationResult:
    path = write_fec(rows, **kwargs)
    return FecValidator(path, path.name, fye, max_issues).run()


def counts(result: ValidationResult) -> dict[str, int]:
    return {rule: issues.count for rule, issues in result.issues.items()}


def signals(result: ValidationResult) -> dict[str, dict]:
    return {s['signal']: s for s in result.risk_signals}
