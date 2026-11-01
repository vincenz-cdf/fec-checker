"""One test (or more) per format rule of the validator."""

from __future__ import annotations

import unittest
from datetime import date

from my_actor.fec.validator import FecValidator, luhn_valid, split_entry_number
from helpers import GOOD_NAME, HEADERS, check, counts, entry, row, write_fec


class TestValidBaseline(unittest.TestCase):
    def test_clean_file_has_no_issue(self) -> None:
        result = check(entry('000001') + entry('000002', '250,50'))
        self.assertEqual(counts(result), {})
        self.assertFalse(result.fatal)
        self.assertEqual(result.stats['lineCount'], 4)
        self.assertEqual(result.stats['entryCount'], 2)
        self.assertEqual(result.stats['totalDebit'], '350,50')
        self.assertEqual(result.stats['separator'], 'pipe')


class TestFileName(unittest.TestCase):
    def test_bad_pattern(self) -> None:
        self.assertIn('file_name', counts(check(entry('1'), name='export_fec.txt')))

    def test_wrong_extension(self) -> None:
        self.assertIn('file_name', counts(check(entry('1'), name='123456782FEC20251231.csv')))

    def test_siren_checksum(self) -> None:
        self.assertIn('siren_checksum', counts(check(entry('1'), name='123456789FEC20251231.txt')))

    def test_invalid_closing_date(self) -> None:
        self.assertIn('file_name_date', counts(check(entry('1'), name='123456782FEC20251332.txt')))

    def test_fiscal_year_end_mismatch(self) -> None:
        result = check(entry('1'), fye=date(2025, 6, 30))
        self.assertIn('fye_mismatch', counts(result))
        self.assertEqual(result.issues['fye_mismatch'].occurrences[0].params['input_date'], '2025-06-30')

    def test_luhn(self) -> None:
        self.assertTrue(luhn_valid('123456782'))
        self.assertTrue(luhn_valid('732829320'))
        self.assertFalse(luhn_valid('123456789'))


class TestEncodingAndSeparator(unittest.TestCase):
    def test_iso_8859_15(self) -> None:
        rows = entry('1')
        rows[0][10] = 'Facture réglée €'
        result = check(rows, encoding='iso-8859-15')
        self.assertEqual(result.stats['encoding'], 'iso-8859-15')
        self.assertEqual(counts(result), {})

    def test_utf8_with_bom(self) -> None:
        result = check(entry('1'), bom=True)
        self.assertEqual(result.stats['encoding'], 'utf-8')
        self.assertTrue(result.stats['hasBom'])
        self.assertEqual(counts(result), {})

    def test_tab_separator(self) -> None:
        result = check(entry('1'), sep='\t')
        self.assertEqual(result.stats['separator'], 'tab')
        self.assertEqual(counts(result), {})

    def test_no_separator_is_fatal(self) -> None:
        result = check(entry('1'), sep=';')
        self.assertIn('separator', counts(result))
        self.assertTrue(result.fatal)


class TestHeader(unittest.TestCase):
    def test_missing_column(self) -> None:
        header = HEADERS[:-1]
        rows = [r[:-1] for r in entry('1')]
        result = check(rows, header=header)
        c = counts(result)
        self.assertEqual(c['header_count'], 1)
        self.assertEqual(c['header_missing'], 1)
        self.assertEqual(result.issues['header_missing'].occurrences[0].field, 'Idevise')
        self.assertIn('column:Idevise', result.skipped_checks)

    def test_unknown_column(self) -> None:
        header = HEADERS.copy()
        header[3] = 'DateEcriture'
        c = counts(check(entry('1'), header=header))
        self.assertIn('header_unknown', c)
        self.assertIn('header_missing', c)

    def test_order(self) -> None:
        header = HEADERS.copy()
        header[11], header[12] = header[12], header[11]
        result = check(entry('1'), header=header)
        self.assertIn('header_order', counts(result))
        # Columns are read by name, so the swapped amounts still balance.
        self.assertNotIn('entry_unbalanced', counts(result))

    def test_case(self) -> None:
        header = HEADERS.copy()
        header[0] = 'journalcode'
        c = counts(check(entry('1'), header=header))
        self.assertIn('header_case', c)
        self.assertNotIn('header_missing', c)


class TestLineStructure(unittest.TestCase):
    def test_field_count(self) -> None:
        rows = entry('1')
        rows.append(row()[:10])
        self.assertEqual(counts(check(rows))['field_count'], 1)

    def test_empty_line(self) -> None:
        path = write_fec(entry('1'), extra_lines=['', *['|'.join(r) for r in entry('2')]])
        result = FecValidator(path, GOOD_NAME).run()
        self.assertEqual(counts(result).get('empty_line'), 1)

    def test_required_field(self) -> None:
        rows = entry('1')
        rows[0][5] = ''  # CompteLib
        result = check(rows)
        self.assertEqual(counts(result)['required_field'], 1)
        self.assertEqual(result.issues['required_field'].occurrences[0].field, 'CompteLib')
        self.assertEqual(result.issues['required_field'].occurrences[0].line, 2)

    def test_aux_pair(self) -> None:
        rows = entry('1')
        rows[0][6] = 'CLI001'  # CompAuxNum without CompAuxLib
        result = check(rows)
        self.assertEqual(result.issues['pair_incomplete'].occurrences[0].field, 'CompAuxLib')

    def test_lettering_pair(self) -> None:
        rows = entry('1')
        rows[0][13] = 'AA'  # EcritureLet without DateLet
        self.assertEqual(check(rows).issues['pair_incomplete'].occurrences[0].field, 'DateLet')

    def test_currency_pair(self) -> None:
        rows = entry('1')
        rows[0][17] = 'USD'  # Idevise without Montantdevise
        self.assertEqual(check(rows).issues['pair_incomplete'].occurrences[0].field, 'Montantdevise')


class TestDates(unittest.TestCase):
    def test_format(self) -> None:
        rows = entry('1')
        rows[0][9] = '10/03/2025'  # PieceDate
        result = check(rows)
        self.assertEqual(counts(result)['date_format'], 1)
        self.assertEqual(result.issues['date_format'].occurrences[0].value, '10/03/2025')

    def test_invalid(self) -> None:
        rows = entry('1', edate='20250230')
        self.assertEqual(counts(check(rows))['date_invalid'], 6)  # EcritureDate, PieceDate, ValidDate on 2 lines

    def test_validdate_before_entry(self) -> None:
        rows = entry('1', valid='20250301')
        self.assertEqual(counts(check(rows))['validdate_before_entry'], 2)

    def test_validdate_chronology(self) -> None:
        rows = entry('1', valid='20250310') + entry('2', valid='20250320') + entry('3', valid='20250315')
        result = check(rows)
        self.assertEqual(counts(result)['validdate_not_chronological'], 1)
        occurrence = result.issues['validdate_not_chronological'].occurrences[0]
        self.assertEqual(occurrence.line, 6)
        self.assertEqual(occurrence.params['previous_number'], 2)

    def test_date_cache_returns_same_result(self) -> None:
        rows = entry('1', edate='20250230') + entry('2', edate='20250230')
        self.assertEqual(counts(check(rows))['date_invalid'], 12)


class TestAmounts(unittest.TestCase):
    def test_decimal_point(self) -> None:
        rows = entry('1')
        rows[0][11] = '100.00'
        result = check(rows)
        self.assertEqual(counts(result)['decimal_point'], 1)
        self.assertNotIn('entry_unbalanced', counts(result))  # the value is still read

    def test_unreadable_amount(self) -> None:
        rows = entry('1')
        rows[0][11] = '1 000,00'
        result = check(rows)
        self.assertEqual(counts(result)['amount_format'], 1)
        self.assertNotIn('entry_unbalanced', counts(result))  # no cascade from an unreadable amount

    def test_empty_amount(self) -> None:
        rows = entry('1')
        rows[0][12] = ''
        self.assertEqual(check(rows).issues['required_field'].occurrences[0].field, 'Credit')

    def test_three_decimals(self) -> None:
        rows = entry('1')
        rows[0][11] = '100,000'
        self.assertIn('amount_format', counts(check(rows)))

    def test_debit_and_credit(self) -> None:
        rows = [row(num='1', debit='100,00', credit='100,00')]
        self.assertEqual(counts(check(rows))['debit_and_credit'], 1)

    def test_zero_line(self) -> None:
        rows = entry('1') + [row(num='1', debit='0,00', credit='0,00')]
        self.assertEqual(counts(check(rows))['zero_line'], 1)

    def test_negative_amount(self) -> None:
        rows = [row(num='1', debit='-50,00'), row(num='1', account='706000', credit='-50,00')]
        self.assertEqual(counts(check(rows))['negative_amount'], 2)

    def test_foreign_amount_format(self) -> None:
        rows = entry('1')
        rows[0][16] = 'abc'
        rows[0][17] = 'USD'
        self.assertEqual(check(rows).issues['amount_format'].occurrences[0].field, 'Montantdevise')


class TestBalance(unittest.TestCase):
    def test_unbalanced_entry(self) -> None:
        rows = entry('1') + [row(num='2', debit='100,00'), row(num='2', account='706000', credit='90,00')]
        result = check(rows)
        c = counts(result)
        self.assertEqual(c['entry_unbalanced'], 1)
        occurrence = result.issues['entry_unbalanced'].occurrences[0]
        self.assertEqual(occurrence.line, 4)
        self.assertEqual(occurrence.params['difference'], '10,00')
        self.assertEqual(occurrence.entry, 'VE/2')

    def test_file_unbalanced(self) -> None:
        rows = [row(num='1', debit='100,00'), row(num='1', account='706000', credit='90,00')]
        result = check(rows)
        self.assertEqual(counts(result)['file_unbalanced'], 1)
        self.assertEqual(result.issues['file_unbalanced'].occurrences[0].params['difference'], '10,00')

    def test_split_entry_balances_across_blocks(self) -> None:
        rows = [row(num='1', debit='100,00')] + entry('2') + [row(num='1', account='706000', credit='100,00')]
        c = counts(check(rows))
        self.assertEqual(c['entry_not_contiguous'], 1)
        self.assertNotIn('entry_unbalanced', c)

    def test_entry_date_mismatch(self) -> None:
        rows = [row(num='1', debit='100,00'), row(num='1', edate='20250311', account='706000', credit='100,00')]
        self.assertEqual(counts(check(rows))['entry_date_mismatch'], 1)


class TestNumbering(unittest.TestCase):
    def test_gap(self) -> None:
        rows = entry('000001') + entry('000002') + entry('000006')
        result = check(rows)
        self.assertEqual(counts(result)['num_gap'], 1)
        occurrence = result.issues['num_gap'].occurrences[0]
        self.assertEqual((occurrence.params['missing_from'], occurrence.params['missing_to']), (3, 5))
        self.assertEqual(occurrence.params['missing_count'], 3)
        self.assertEqual(occurrence.line, 6)

    def test_duplicate_same_journal(self) -> None:
        rows = entry('1') + entry('2') + entry('1')
        self.assertEqual(counts(check(rows))['entry_not_contiguous'], 1)

    def test_duplicate_across_journals_in_global_numbering(self) -> None:
        rows = []
        for n in range(1, 21):
            rows += entry(str(n))
        rows += entry('5', journal='AC')
        result = check(rows)
        self.assertEqual(result.stats['numberingScope'], 'global')
        self.assertEqual(counts(result)['num_duplicate'], 1)
        self.assertEqual(result.issues['num_duplicate'].occurrences[0].params['other_journal'], 'VE')

    def test_per_journal_numbering_is_detected(self) -> None:
        rows = []
        for journal in ('VE', 'AC', 'BQ'):
            for n in range(1, 6):
                rows += entry(str(n), journal=journal)
        result = check(rows)
        self.assertEqual(result.stats['numberingScope'], 'per_journal')
        self.assertEqual(counts(result), {})

    def test_gap_per_journal(self) -> None:
        rows = []
        for journal in ('VE', 'AC'):
            for n in (1, 2, 3):
                rows += entry(str(n), journal=journal)
        rows += entry('5', journal='AC')
        result = check(rows)
        self.assertEqual(counts(result)['num_gap'], 1)
        self.assertEqual(result.issues['num_gap'].occurrences[0].entry, 'AC')

    def test_prefixed_numbers(self) -> None:
        rows = entry('VE0001') + entry('VE0002') + entry('AC0001', journal='AC') + entry('AC0003', journal='AC')
        result = check(rows)
        self.assertEqual(counts(result)['num_gap'], 1)
        self.assertEqual(result.issues['num_gap'].occurrences[0].params['sequence'], 'AC')

    def test_split_entry_number(self) -> None:
        self.assertEqual(split_entry_number('VE000123'), ('VE', 123))
        self.assertEqual(split_entry_number('42'), ('', 42))
        self.assertIsNone(split_entry_number('ABC'))


class TestIssueCap(unittest.TestCase):
    def test_occurrences_are_capped_but_counted(self) -> None:
        rows = [row(num=str(n), debit='100,00', credit='100,00') for n in range(1, 31)]
        result = check(rows, max_issues=5)
        issues = result.issues['debit_and_credit']
        self.assertEqual(issues.count, 30)
        self.assertEqual(len(issues.occurrences), 5)


if __name__ == '__main__':
    unittest.main()
