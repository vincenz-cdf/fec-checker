"""Streaming FEC validator (art. A47 A-1 du Livre des procédures fiscales).

The file is read line by line. Memory grows with the number of entries (EcritureNum), not with the
number of lines, and per-entry state is kept as small as possible so files of 1M+ lines fit in 1 GB.
This module is pure Python and does not depend on the Apify SDK, so it can be unit tested directly.
"""

from __future__ import annotations

import codecs
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date
from pathlib import Path

from my_actor.fec.signals import benford_test, compute_risk_signals, fmt_cents

EXPECTED_HEADERS = (
    'JournalCode', 'JournalLib', 'EcritureNum', 'EcritureDate', 'CompteNum', 'CompteLib',
    'CompAuxNum', 'CompAuxLib', 'PieceRef', 'PieceDate', 'EcritureLib', 'Debit', 'Credit',
    'EcritureLet', 'DateLet', 'ValidDate', 'Montantdevise', 'Idevise',
)
REQUIRED_FIELDS = (
    'JournalCode', 'JournalLib', 'EcritureNum', 'EcritureDate', 'CompteNum', 'CompteLib',
    'PieceRef', 'PieceDate', 'EcritureLib', 'Debit', 'Credit', 'ValidDate',
)
DATE_FIELDS = ('EcritureDate', 'PieceDate', 'DateLet', 'ValidDate')

FILE_NAME_RE = re.compile(r'^(\d{9})FEC(\d{8})\.txt$', re.IGNORECASE)
AMOUNT_RE = re.compile(r'^(-?)(\d+)(?:,(\d{1,2}))?$')
DOT_AMOUNT_RE = re.compile(r'^(-?)(\d+)\.(\d{1,2})$')
TRAILING_NUMBER_RE = re.compile(r'^(.*?)(\d+)$')

# Share of EcritureNum values reused across journals above which numbering is considered per journal.
PER_JOURNAL_SHARED_RATIO = 0.10

DATE_FORMAT_ERROR = -1
DATE_INVALID = -2


@dataclass
class Occurrence:
    line: int | None
    field: str | None = None
    value: str | None = None
    entry: str | None = None
    params: dict = dc_field(default_factory=dict)


@dataclass
class RuleIssues:
    count: int = 0
    occurrences: list[Occurrence] = dc_field(default_factory=list)


class IssueCollector:
    """Counts every occurrence of a rule, keeps only the first `max_per_rule` for the report."""

    def __init__(self, max_per_rule: int) -> None:
        self.max_per_rule = max_per_rule
        self.rules: dict[str, RuleIssues] = {}

    def add(self, rule: str, line: int | None, field: str | None = None, value: str | None = None,
            entry: str | None = None, **params: object) -> None:
        issues = self.rules.get(rule)
        if issues is None:
            issues = self.rules[rule] = RuleIssues()
        issues.count += 1
        if len(issues.occurrences) < self.max_per_rule:
            issues.occurrences.append(Occurrence(line, field, value, entry, params))


@dataclass
class ValidationResult:
    file_name: str
    issues: dict[str, RuleIssues]
    risk_signals: list[dict]
    stats: dict
    skipped_checks: list[str]
    fatal: bool


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def parse_yyyymmdd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def check_file_name(file_name: str, fiscal_year_end: date | None, issues: IssueCollector) -> date | None:
    """Check the SIRENFECAAAAMMJJ.txt naming rule. Returns the closing date it encodes, if valid."""
    match = FILE_NAME_RE.match(file_name)
    if not match:
        issues.add('file_name', None, value=file_name)
        return None
    siren, closing = match.groups()
    if not luhn_valid(siren):
        issues.add('siren_checksum', None, value=siren)
    closing_date = parse_yyyymmdd(closing)
    if closing_date is None:
        issues.add('file_name_date', None, value=closing)
        return None
    if fiscal_year_end is not None and closing_date != fiscal_year_end:
        issues.add('fye_mismatch', None, value=closing, input_date=fiscal_year_end.isoformat())
    return closing_date


def detect_encoding(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return 'utf-8' if the whole file decodes as UTF-8, else 'iso-8859-15'. Reads in chunks."""
    decoder = codecs.getincrementaldecoder('utf-8')()
    try:
        with path.open('rb') as f:
            while chunk := f.read(chunk_size):
                decoder.decode(chunk)
            decoder.decode(b'', final=True)
    except UnicodeDecodeError:
        return 'iso-8859-15'
    return 'utf-8'


def split_entry_number(num: str) -> tuple[str, int] | None:
    match = TRAILING_NUMBER_RE.match(num)
    if not match:
        return None
    return match.group(1), int(match.group(2))


class FecValidator:
    """Validate one FEC file. Call `run()` once; `lines_read` can be polled from another thread."""

    def __init__(self, path: Path, file_name: str, fiscal_year_end: date | None = None,
                 max_issues_per_rule: int = 50) -> None:
        self.path = Path(path)
        self.file_name = file_name
        self.fiscal_year_end_input = fiscal_year_end
        self.issues = IssueCollector(max_issues_per_rule)
        self.lines_read = 0
        # Set from another thread (Actor abort) to stop reading at the next checkpoint.
        self.cancel_requested = False
        self.skipped_checks: set[str] = set()

        self._date_cache: dict[str, int] = {}
        # Entry (journal + EcritureNum) currently being read and its running balance in cents.
        self._cur_key: str | None = None
        self._cur_balance = 0
        self._cur_line = 0
        self._cur_date = ''
        self._cur_amount_ok = True
        self._closed_keys: set[str] = set()
        # Unbalanced blocks wait here: a later block of the same entry may balance them.
        self._pending: dict[str, tuple[int, int, str]] = {}
        # Numbering: (journal, prefix) -> {number: (first line, ValidDate ordinal)}
        self._sequences: dict[tuple[str, str], dict[int, tuple[int, int]]] = defaultdict(dict)
        self._num_journal: dict[str, str] = {}
        self._shared_nums: list[tuple[int, str, str, str]] = []
        self._shared_count = 0
        self._non_numeric_nums = 0

        self.total_debit = 0
        self.total_credit = 0
        self.entry_count = 0
        self.journal_lines: Counter[str] = Counter()
        self.account_balances: dict[str, int] = defaultdict(int)
        self.cash_daily: dict[tuple[str, int], int] = defaultdict(int)
        self.entry_dates: Counter[int] = Counter()
        self.entry_date_first_line: dict[int, int] = {}
        self.amount_first_digits: Counter[int] = Counter()
        self.round_amount_lines: list[int] = []
        self.round_amount_count = 0
        self.nonzero_amount_count = 0
        self.after_fye_lines: list[int] = []
        self.after_fye_count = 0
        self.fiscal_year_end: date | None = None

    # ---------------------------------------------------------------- helpers

    def _date(self, value: str) -> int:
        """Return the date ordinal, DATE_FORMAT_ERROR or DATE_INVALID. Distinct values are few, so cache."""
        cached = self._date_cache.get(value)
        if cached is not None:
            return cached
        if len(value) != 8 or not value.isdigit():
            result = DATE_FORMAT_ERROR
        else:
            parsed = parse_yyyymmdd(value)
            result = parsed.toordinal() if parsed else DATE_INVALID
        if len(self._date_cache) < 100_000:
            self._date_cache[value] = result
        return result

    def _amount(self, value: str, field_name: str, line: int, entry: str) -> int | None:
        """Parse an amount into cents, recording format errors. Returns None when it cannot be read."""
        match = AMOUNT_RE.match(value)
        if match is None:
            match = DOT_AMOUNT_RE.match(value)
            if match is None:
                self.issues.add('amount_format', line, field_name, value, entry)
                return None
            self.issues.add('decimal_point', line, field_name, value, entry)
        sign, units, decimals = match.groups()
        cents = int(units) * 100 + int((decimals or '0').ljust(2, '0'))
        return -cents if sign else cents

    def _close_entry(self) -> None:
        if self._cur_key is None:
            return
        if self._cur_amount_ok and self._cur_balance != 0:
            self._pending[self._cur_key] = (self._cur_balance, self._cur_line, self._cur_key)
        self._closed_keys.add(self._cur_key)
        self._cur_key = None

    # ---------------------------------------------------------------- main loop

    def run(self) -> ValidationResult:
        started = time.monotonic()
        closing_from_name = check_file_name(self.file_name, self.fiscal_year_end_input, self.issues)
        self.fiscal_year_end = self.fiscal_year_end_input or closing_from_name
        self._fye_ordinal = self.fiscal_year_end.toordinal() if self.fiscal_year_end else None

        encoding = detect_encoding(self.path)
        separator = None
        columns: dict[str, int] = {}
        fatal = False
        has_bom = False
        empty_lines = 0

        with self.path.open('r', encoding=encoding, newline='') as f:
            header_line = f.readline()
            self.lines_read = 1
            if header_line.startswith('﻿'):
                has_bom = True
                header_line = header_line[1:]
            header_line = header_line.rstrip('\r\n')
            if '\t' in header_line:
                separator = '\t'
            elif '|' in header_line:
                separator = '|'
            else:
                self.issues.add('separator', 1)
                fatal = True

            if not fatal:
                columns = self._check_header(header_line.split(separator))
                fatal = not columns
            if not fatal:
                width = len(header_line.split(separator))
                empty_lines = self._read_rows(f, separator, columns, width)

        self._close_entry()
        stats = self._finish(encoding, separator, has_bom, empty_lines, time.monotonic() - started)
        risk = compute_risk_signals(self) if not fatal else []
        stats['benford'] = benford_test(self.amount_first_digits)
        return ValidationResult(
            file_name=self.file_name,
            issues=self.issues.rules,
            risk_signals=risk,
            stats=stats,
            skipped_checks=sorted(self.skipped_checks),
            fatal=fatal,
        )

    def _check_header(self, names: list[str]) -> dict[str, int]:
        names = [n.strip() for n in names]
        if tuple(names) == EXPECTED_HEADERS:
            return {n: i for i, n in enumerate(names)}

        if len(names) != len(EXPECTED_HEADERS):
            self.issues.add('header_count', 1, value=str(len(names)), expected=len(EXPECTED_HEADERS))
        exact = {n: i for i, n in enumerate(names)}
        lowered = {n.lower(): i for i, n in enumerate(names)}
        columns: dict[str, int] = {}
        for expected in EXPECTED_HEADERS:
            if expected in exact:
                columns[expected] = exact[expected]
            elif expected.lower() in lowered:
                columns[expected] = lowered[expected.lower()]
                self.issues.add('header_case', 1, field=expected, value=names[columns[expected]])
            else:
                self.issues.add('header_missing', 1, field=expected)
        known = {e.lower() for e in EXPECTED_HEADERS}
        for name in names:
            if name.lower() not in known:
                self.issues.add('header_unknown', 1, value=name)
        # Order is checked on the columns that were found, so a missing column does not hide a swap.
        order = [n for n, _ in sorted(columns.items(), key=lambda kv: kv[1])]
        if order != [n for n in EXPECTED_HEADERS if n in columns]:
            self.issues.add('header_order', 1, value=','.join(order))
        return columns

    def _read_rows(self, f, separator: str, columns: dict[str, int], width: int) -> int:  # noqa: C901, PLR0912, PLR0915
        add = self.issues.add
        col = columns.get
        missing = [n for n in EXPECTED_HEADERS if n not in columns]
        for name in missing:
            self.skipped_checks.add(f'column:{name}')
        has_amounts = 'Debit' in columns and 'Credit' in columns
        if not has_amounts:
            self.skipped_checks.update({'balance', 'amounts', 'benford', 'round_amounts', 'account_balances'})
        i_journal, i_num, i_edate = col('JournalCode'), col('EcritureNum'), col('EcritureDate')
        i_account, i_debit, i_credit = col('CompteNum'), col('Debit'), col('Credit')
        i_valid = col('ValidDate')
        if i_journal is None or i_num is None:
            self.skipped_checks.update({'balance', 'numbering', 'validdate_chronology'})
        required = [(n, columns[n]) for n in REQUIRED_FIELDS if n in columns]
        dates = [(n, columns[n]) for n in DATE_FIELDS if n in columns]
        pairs = [(a, b) for a, b in (('CompAuxNum', 'CompAuxLib'), ('EcritureLet', 'DateLet'),
                                     ('Montantdevise', 'Idevise')) if a in columns and b in columns]
        i_fx = col('Montantdevise')
        fye = self._fye_ordinal
        empty_lines = 0
        line_no = 1

        for raw in f:
            line_no += 1
            self.lines_read = line_no
            if line_no % 65_536 == 0 and self.cancel_requested:
                break
            text = raw.rstrip('\r\n')
            if not text.strip():
                empty_lines += 1
                add('empty_line', line_no)
                continue
            row = text.split(separator)
            if len(row) != width:
                add('field_count', line_no, value=str(len(row)), expected=width)
                continue
            row = [v.strip() for v in row]

            journal = row[i_journal] if i_journal is not None else ''
            num = row[i_num] if i_num is not None else ''
            entry_label = f'{journal}/{num}' if journal or num else None

            for name, idx in required:
                if not row[idx]:
                    add('required_field', line_no, name, None, entry_label)
            for a, b in pairs:
                if bool(row[columns[a]]) != bool(row[columns[b]]):
                    add('pair_incomplete', line_no, b if row[columns[a]] else a, None, entry_label, pair=f'{a}/{b}')

            ordinals: dict[str, int] = {}
            for name, idx in dates:
                value = row[idx]
                if not value:
                    continue
                ordinal = self._date(value)
                if ordinal == DATE_FORMAT_ERROR:
                    add('date_format', line_no, name, value, entry_label)
                elif ordinal == DATE_INVALID:
                    add('date_invalid', line_no, name, value, entry_label)
                else:
                    ordinals[name] = ordinal
            edate = ordinals.get('EcritureDate')
            vdate = ordinals.get('ValidDate')
            if edate is not None and vdate is not None and vdate < edate:
                add('validdate_before_entry', line_no, 'ValidDate', row[i_valid], entry_label)

            debit = credit = None
            if has_amounts:
                debit = self._amount(row[i_debit], 'Debit', line_no, entry_label) if row[i_debit] else None
                credit = self._amount(row[i_credit], 'Credit', line_no, entry_label) if row[i_credit] else None
                if debit is not None and credit is not None:
                    if debit < 0 or credit < 0:
                        add('negative_amount', line_no, 'Debit' if debit < 0 else 'Credit', None, entry_label)
                    if debit and credit:
                        add('debit_and_credit', line_no, None, None, entry_label)
                    elif not debit and not credit:
                        add('zero_line', line_no, None, None, entry_label)
            if i_fx is not None and row[i_fx] and not (AMOUNT_RE.match(row[i_fx]) or DOT_AMOUNT_RE.match(row[i_fx])):
                add('amount_format', line_no, 'Montantdevise', row[i_fx], entry_label)

            self.journal_lines[journal] += 1
            amounts_ok = debit is not None and credit is not None

            # ---- entry tracking (balance, contiguity, numbering)
            if i_journal is not None and i_num is not None and num:
                key = f'{journal}\x1f{num}'
                if key != self._cur_key:
                    self._close_entry()
                    self.entry_count += 1
                    if key in self._closed_keys:
                        add('entry_not_contiguous', line_no, 'EcritureNum', None, entry_label)
                        pending = self._pending.pop(key, None)
                        self._cur_balance = pending[0] if pending else 0
                        self._cur_line = pending[1] if pending else line_no
                    else:
                        self._cur_balance = 0
                        self._cur_line = line_no
                        self._register_number(journal, num, line_no, vdate)
                        if edate is not None:
                            self.entry_dates[edate] += 1
                            self.entry_date_first_line.setdefault(edate, line_no)
                    self._cur_key = key
                    self._cur_date = row[i_edate] if i_edate is not None else ''
                    self._cur_amount_ok = True
                elif i_edate is not None and row[i_edate] != self._cur_date:
                    add('entry_date_mismatch', line_no, 'EcritureDate', row[i_edate], entry_label)
                if amounts_ok:
                    self._cur_balance += debit - credit
                elif has_amounts:
                    self._cur_amount_ok = False

            if edate is not None and fye is not None and edate > fye:
                self.after_fye_count += 1
                if len(self.after_fye_lines) < self.issues.max_per_rule:
                    self.after_fye_lines.append(line_no)

            if not amounts_ok:
                continue
            self.total_debit += debit
            self.total_credit += credit
            account = row[i_account] if i_account is not None else ''
            self.account_balances[account] += debit - credit
            if account.startswith('53') and edate is not None:
                self.cash_daily[(account, edate)] += debit - credit
            amount = abs(debit or credit)
            if amount:
                self.nonzero_amount_count += 1
                if amount >= 100_000 and amount % 100_000 == 0:
                    self.round_amount_count += 1
                    if len(self.round_amount_lines) < self.issues.max_per_rule:
                        self.round_amount_lines.append(line_no)
                if amount >= 1_000:
                    self.amount_first_digits[int(str(amount)[0])] += 1
        return empty_lines

    def _register_number(self, journal: str, num: str, line_no: int, vdate: int | None) -> None:
        first_journal = self._num_journal.get(num)
        if first_journal is None:
            self._num_journal[num] = journal
        elif first_journal != journal:
            self._shared_count += 1
            if len(self._shared_nums) < self.issues.max_per_rule:
                self._shared_nums.append((line_no, num, first_journal, journal))
        split = split_entry_number(num)
        if split is None:
            self._non_numeric_nums += 1
            return
        prefix, number = split
        self._sequences[(journal, prefix)][number] = (line_no, vdate if vdate is not None else -1)

    # ---------------------------------------------------------------- end of file checks

    def _finish(self, encoding: str, separator: str | None, has_bom: bool, empty_lines: int,
                duration: float) -> dict:
        add = self.issues.add
        for balance, line, key in sorted(self._pending.values(), key=lambda p: p[1]):
            journal, num = key.split('\x1f', 1)
            add('entry_unbalanced', line, None, None, f'{journal}/{num}', difference=fmt_cents(balance))
        if self.total_debit != self.total_credit:
            add('file_unbalanced', None, difference=fmt_cents(self.total_debit - self.total_credit),
                total_debit=fmt_cents(self.total_debit), total_credit=fmt_cents(self.total_credit))

        distinct_nums = len(self._num_journal)
        per_journal = distinct_nums > 0 and self._shared_count / distinct_nums > PER_JOURNAL_SHARED_RATIO
        if not per_journal:
            for line, num, first_journal, journal in self._shared_nums:
                add('num_duplicate', line, 'EcritureNum', num, f'{journal}/{num}', other_journal=first_journal)
            if self._shared_count > len(self._shared_nums):
                self.issues.rules['num_duplicate'].count += self._shared_count - len(self._shared_nums)

        sequences = self._merged_sequences(per_journal)
        for (journal, prefix), numbers in sorted(sequences.items()):
            self._check_sequence(journal, prefix, numbers)

        dates = sorted(self.entry_dates)
        return {
            'encoding': encoding,
            'separator': {'\t': 'tab', '|': 'pipe'}.get(separator or '', None),
            'hasBom': has_bom,
            'lineCount': max(self.lines_read - 1 - empty_lines, 0),
            'entryCount': self.entry_count,
            'journalCount': len(self.journal_lines),
            'journals': dict(sorted(self.journal_lines.items())),
            'accountCount': len(self.account_balances),
            'totalDebit': fmt_cents(self.total_debit),
            'totalCredit': fmt_cents(self.total_credit),
            'firstEntryDate': date.fromordinal(dates[0]).isoformat() if dates else None,
            'lastEntryDate': date.fromordinal(dates[-1]).isoformat() if dates else None,
            'fiscalYearEnd': self._effective_fye(dates),
            'numberingScope': 'per_journal' if per_journal else 'global',
            'nonNumericEntryNumbers': self._non_numeric_nums,
            'durationSeconds': round(duration, 2),
        }

    def _effective_fye(self, dates: list[int]) -> str | None:
        if self.fiscal_year_end:
            return self.fiscal_year_end.isoformat()
        return date.fromordinal(dates[-1]).isoformat() if dates else None

    def _merged_sequences(self, per_journal: bool) -> dict[tuple[str, str], dict[int, tuple[int, int]]]:
        if per_journal:
            return self._sequences
        merged: dict[tuple[str, str], dict[int, tuple[int, int]]] = defaultdict(dict)
        for (_, prefix), numbers in self._sequences.items():
            target = merged[('', prefix)]
            for number, info in numbers.items():
                if number not in target or info[0] < target[number][0]:
                    target[number] = info
        return merged

    def _check_sequence(self, journal: str, prefix: str, numbers: dict[int, tuple[int, int]]) -> None:
        add = self.issues.add
        label = journal or None
        previous = None
        max_valid = -1
        max_valid_number = None
        for number in sorted(numbers):
            line, valid = numbers[number]
            if previous is not None and number > previous + 1:
                add('num_gap', line, 'EcritureNum', None, label, sequence=prefix or None,
                    missing_from=previous + 1, missing_to=number - 1, missing_count=number - previous - 1)
            if valid >= 0:
                if valid < max_valid:
                    add('validdate_not_chronological', line, 'ValidDate', date.fromordinal(valid).strftime('%Y%m%d'),
                        label, number=number, previous_number=max_valid_number,
                        previous_date=date.fromordinal(max_valid).strftime('%Y%m%d'))
                else:
                    max_valid = valid
                    max_valid_number = number
            previous = number
