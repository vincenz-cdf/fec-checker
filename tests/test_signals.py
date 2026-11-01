"""Risk signals and their statistics helpers."""

from __future__ import annotations

import math
import unittest
from datetime import date

from my_actor.fec.signals import (
    benford_test,
    chi_square_p_value_df8,
    easter_sunday,
    french_public_holidays,
)
from helpers import check, entry, row, signals


def numbered_entries(amounts: list[str], edate: str = '20250310') -> list[list[str]]:
    rows = []
    for n, amount in enumerate(amounts, start=1):
        rows += entry(f'{n:06d}', amount, edate)
    return rows


def cents_to_fec(cents: int) -> str:
    return f'{cents // 100},{cents % 100:02d}'


class TestCalendarSignals(unittest.TestCase):
    def test_weekend(self) -> None:
        rows = entry('1', edate='20250303') + entry('2', edate='20250308')  # Monday (opening), Saturday
        found = signals(check(rows))
        self.assertEqual(found['weekend_postings']['count'], 1)
        self.assertEqual(found['weekend_postings']['lines'], [4])

    def test_holiday(self) -> None:
        rows = entry('1', edate='20250303') + entry('2', edate='20250714')
        self.assertEqual(signals(check(rows))['holiday_postings']['count'], 1)

    def test_opening_date_is_ignored(self) -> None:
        rows = entry('1', edate='20250101') + entry('2', edate='20250310')  # 1 January holds the à-nouveaux
        self.assertNotIn('holiday_postings', signals(check(rows)))

    def test_weekday_is_clean(self) -> None:
        rows = entry('1', edate='20250310') + entry('2', edate='20250311')
        self.assertEqual(signals(check(rows)), {})

    def test_easter(self) -> None:
        self.assertEqual(easter_sunday(2024), date(2024, 3, 31))
        self.assertEqual(easter_sunday(2025), date(2025, 4, 20))
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))

    def test_holiday_list(self) -> None:
        holidays = french_public_holidays(2025)
        self.assertEqual(len(holidays), 11)
        for day in (date(2025, 4, 21), date(2025, 5, 29), date(2025, 6, 9), date(2025, 7, 14), date(2025, 12, 25)):
            self.assertIn(day, holidays)


class TestRoundAmounts(unittest.TestCase):
    def test_round_share_triggers(self) -> None:
        amounts = ['5000,00'] * 3 + ['123,45'] * 7
        found = signals(check(numbered_entries(amounts)))
        self.assertEqual(found['round_amounts']['count'], 6)
        self.assertEqual(found['round_amounts']['level'], 'high')

    def test_few_round_amounts_do_not_trigger(self) -> None:
        amounts = ['1000,00'] + ['123,45'] * 30
        self.assertNotIn('round_amounts', signals(check(numbered_entries(amounts))))

    def test_hundreds_are_not_round(self) -> None:
        amounts = ['1200,00'] * 10
        self.assertNotIn('round_amounts', signals(check(numbered_entries(amounts))))


class TestBenford(unittest.TestCase):
    def test_p_value(self) -> None:
        self.assertAlmostEqual(chi_square_p_value_df8(15.507), 0.05, places=3)
        self.assertAlmostEqual(chi_square_p_value_df8(0), 1.0)

    def test_benford_distributed_amounts_pass(self) -> None:
        golden = (math.sqrt(5) - 1) / 2
        cents = [int(10 ** (3 + 4 * ((i * golden) % 1))) for i in range(1, 801)]
        found = signals(check(numbered_entries([cents_to_fec(c) for c in cents])))
        self.assertNotIn('benford_deviation', found)

    def test_skewed_amounts_fail(self) -> None:
        amounts = [cents_to_fec(90_000 + i) for i in range(400)]  # every amount starts with 9
        found = signals(check(numbered_entries(amounts)))
        self.assertEqual(found['benford_deviation']['level'], 'high')

    def test_small_sample_is_not_tested(self) -> None:
        amounts = [cents_to_fec(90_000 + i) for i in range(50)]
        self.assertNotIn('benford_deviation', signals(check(numbered_entries(amounts))))

    def test_counts(self) -> None:
        result = benford_test({1: 30, 2: 18, 3: 12, 4: 10, 5: 8, 6: 7, 7: 6, 8: 5, 9: 4})
        self.assertEqual(result['sampleSize'], 100)
        self.assertGreater(result['pValue'], 0.5)


class TestBalanceSignals(unittest.TestCase):
    def test_negative_cash(self) -> None:
        rows = [
            row(num='1', edate='20250303', account='530000', debit='100,00', journal='CA'),
            row(num='1', edate='20250303', account='706000', credit='100,00', journal='CA'),
            row(num='2', edate='20250305', account='606000', debit='150,00', journal='CA'),
            row(num='2', edate='20250305', account='530000', credit='150,00', journal='CA'),
        ]
        found = signals(check(rows))['negative_cash_balance']
        self.assertEqual(found['details']['account'], '530000')
        self.assertEqual(found['details']['firstNegativeDate'], '2025-03-05')
        self.assertEqual(found['details']['lowestBalance'], '-50,00')

    def test_cash_back_in_the_black_is_clean(self) -> None:
        rows = [
            row(num='1', account='530000', debit='100,00'),
            row(num='1', account='706000', credit='100,00'),
        ]
        self.assertNotIn('negative_cash_balance', signals(check(rows)))

    def test_suspense_account(self) -> None:
        rows = entry('1', debit_account='471000')
        found = signals(check(rows))['suspense_account_not_cleared']
        self.assertEqual(found['details']['closingBalance'], '100,00')

    def test_cleared_suspense_account(self) -> None:
        rows = entry('1', debit_account='471000') + entry('2', debit_account='411000', credit_account='471000')
        self.assertNotIn('suspense_account_not_cleared', signals(check(rows)))


class TestFiscalYearEnd(unittest.TestCase):
    def test_after_fye_from_file_name(self) -> None:
        rows = entry('1', edate='20251230') + entry('2', edate='20260105')
        found = signals(check(rows))['entries_after_fiscal_year_end']
        self.assertEqual(found['count'], 2)
        self.assertEqual(found['lines'], [4, 5])

    def test_after_fye_from_input(self) -> None:
        rows = entry('1', edate='20250310')
        found = signals(check(rows, fye=date(2025, 3, 1), name='export.txt'))
        self.assertIn('entries_after_fiscal_year_end', found)

    def test_inside_fiscal_year(self) -> None:
        self.assertNotIn('entries_after_fiscal_year_end', signals(check(entry('1', edate='20251231'))))


if __name__ == '__main__':
    unittest.main()
