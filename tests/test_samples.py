"""The 5 synthetic files in test_data/fec each trigger exactly their intended defect."""

from __future__ import annotations

import unittest
from pathlib import Path

from my_actor.fec.report import build_report
from my_actor.fec.validator import FecValidator

SAMPLES = Path(__file__).resolve().parent.parent / 'test_data' / 'fec'


def run_sample(case: str) -> dict:
    path = SAMPLES / case / '123456782FEC20251231.txt'
    return build_report(FecValidator(path, path.name).run(), 'en')


def rules(groups: list[dict]) -> set[str]:
    return {g['rule'] for g in groups}


class TestSamples(unittest.TestCase):
    def test_valid(self) -> None:
        report = run_sample('valid')
        self.assertEqual(report['verdict'], 'valid')
        self.assertEqual(report['score'], 100)
        self.assertEqual(report['riskSignals'], [])

    def test_bad_headers(self) -> None:
        report = run_sample('bad_headers')
        self.assertEqual(rules(report['errors']), {'header_count', 'header_missing', 'header_unknown', 'header_order'})
        missing = {o['field'] for g in report['errors'] if g['rule'] == 'header_missing' for o in g['occurrences']}
        self.assertEqual(missing, {'EcritureDate', 'Idevise'})

    def test_unbalanced(self) -> None:
        report = run_sample('unbalanced')
        self.assertEqual(rules(report['errors']), {'entry_unbalanced', 'file_unbalanced'})
        group = next(g for g in report['errors'] if g['rule'] == 'entry_unbalanced')
        self.assertIn('100,00', group['occurrences'][0]['message'])

    def test_numbering_gap(self) -> None:
        report = run_sample('numbering_gap')
        self.assertEqual(rules(report['errors']), {'num_gap'})
        self.assertIn('3 number(s) missing', report['errors'][0]['occurrences'][0]['message'])

    def test_bad_dates(self) -> None:
        report = run_sample('bad_dates')
        self.assertEqual(rules(report['errors']), {'date_invalid', 'date_format', 'validdate_not_chronological'})
        self.assertIn('entries_after_fiscal_year_end', {s['signal'] for s in report['riskSignals']})


if __name__ == '__main__':
    unittest.main()
