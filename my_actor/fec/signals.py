"""Risk signals: patterns that are not format errors but that a tax auditor would look at."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from my_actor.fec.validator import FecValidator

BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
BENFORD_MIN_SAMPLE = 300
BENFORD_P_MEDIUM = 0.01
BENFORD_P_HIGH = 0.001
ROUND_SHARE_MEDIUM = 0.05
ROUND_SHARE_HIGH = 0.15
CALENDAR_SHARE_MEDIUM = 0.05


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def french_public_holidays(year: int) -> set[date]:
    """The 11 national public holidays (Alsace-Moselle extras are not included)."""
    easter = easter_sunday(year)
    return {
        date(year, 1, 1), easter + timedelta(days=1), date(year, 5, 1), date(year, 5, 8),
        easter + timedelta(days=39), easter + timedelta(days=50), date(year, 7, 14),
        date(year, 8, 15), date(year, 11, 1), date(year, 11, 11), date(year, 12, 25),
    }


def chi_square_p_value_df8(x: float) -> float:
    """Survival function of the chi-square distribution with 8 degrees of freedom (closed form for even df)."""
    half = x / 2
    return math.exp(-half) * sum(half**i / math.factorial(i) for i in range(4))


def benford_test(first_digits: dict[int, int]) -> dict:
    n = sum(first_digits.values())
    observed = {d: first_digits.get(d, 0) for d in range(1, 10)}
    if n == 0:
        return {'sampleSize': 0, 'chiSquare': None, 'pValue': None, 'observed': observed}
    chi2 = sum((observed[d] - n * p) ** 2 / (n * p) for d, p in BENFORD_EXPECTED.items())
    return {
        'sampleSize': n,
        'chiSquare': round(chi2, 3),
        'pValue': round(chi_square_p_value_df8(chi2), 6),
        'observed': observed,
    }


def compute_risk_signals(v: FecValidator) -> list[dict]:
    signals: list[dict] = []
    entries = sum(v.entry_dates.values())

    # The earliest date carries the opening entries (à-nouveaux), often dated 1 January: not a signal.
    opening = min(v.entry_dates, default=None)
    calendar_dates = [o for o in v.entry_dates if o != opening]
    weekend = [o for o in calendar_dates if date.fromordinal(o).weekday() >= 5]
    holidays_by_year: dict[int, set[date]] = {}
    holiday = []
    for o in calendar_dates:
        d = date.fromordinal(o)
        if d.year not in holidays_by_year:
            holidays_by_year[d.year] = french_public_holidays(d.year)
        if d in holidays_by_year[d.year]:
            holiday.append(o)
    for signal, ordinals in (('weekend_postings', weekend), ('holiday_postings', holiday)):
        count = sum(v.entry_dates[o] for o in ordinals)
        if count:
            share = count / entries
            signals.append({
                'signal': signal,
                'level': 'medium' if share >= CALENDAR_SHARE_MEDIUM else 'low',
                'count': count,
                'details': {'share': round(share, 4), 'dates': sorted(date.fromordinal(o).isoformat() for o in ordinals)[:50]},
                'lines': sorted(v.entry_date_first_line[o] for o in ordinals)[: v.issues.max_per_rule],
            })

    if v.nonzero_amount_count:
        share = v.round_amount_count / v.nonzero_amount_count
        if share >= ROUND_SHARE_MEDIUM:
            signals.append({
                'signal': 'round_amounts',
                'level': 'high' if share >= ROUND_SHARE_HIGH else 'medium',
                'count': v.round_amount_count,
                'details': {'share': round(share, 4), 'threshold': ROUND_SHARE_MEDIUM},
                'lines': v.round_amount_lines,
            })

    benford = benford_test(v.amount_first_digits)
    if benford['sampleSize'] >= BENFORD_MIN_SAMPLE and benford['pValue'] < BENFORD_P_MEDIUM:
        signals.append({
            'signal': 'benford_deviation',
            'level': 'high' if benford['pValue'] < BENFORD_P_HIGH else 'medium',
            'count': benford['sampleSize'],
            'details': benford,
            'lines': [],
        })

    cash_by_account: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for (account, ordinal), net in v.cash_daily.items():
        cash_by_account[account].append((ordinal, net))
    for account, days in sorted(cash_by_account.items()):
        running = 0
        first_negative = None
        lowest = 0
        for ordinal, net in sorted(days):
            running += net
            if running < 0 and first_negative is None:
                first_negative = ordinal
            lowest = min(lowest, running)
        if first_negative is not None:
            signals.append({
                'signal': 'negative_cash_balance',
                'level': 'high',
                'count': 1,
                'details': {
                    'account': account,
                    'firstNegativeDate': date.fromordinal(first_negative).isoformat(),
                    'lowestBalance': fmt_cents(lowest),
                    'closingBalance': fmt_cents(running),
                },
                'lines': [],
            })

    for account, balance in sorted(v.account_balances.items()):
        if account.startswith('471') and balance != 0:
            signals.append({
                'signal': 'suspense_account_not_cleared',
                'level': 'medium',
                'count': 1,
                'details': {'account': account, 'closingBalance': fmt_cents(balance)},
                'lines': [],
            })

    if v.after_fye_count:
        signals.append({
            'signal': 'entries_after_fiscal_year_end',
            'level': 'high',
            'count': v.after_fye_count,
            'details': {'fiscalYearEnd': v.fiscal_year_end.isoformat() if v.fiscal_year_end else None},
            'lines': v.after_fye_lines,
        })
    return signals


def fmt_cents(cents: int) -> str:
    """Format cents the FEC way: 1234,56."""
    sign = '-' if cents < 0 else ''
    cents = abs(cents)
    return f'{sign}{cents // 100},{cents % 100:02d}'
