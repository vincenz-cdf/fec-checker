"""Report building, scoring, messages and the sanitized AI payload."""

from __future__ import annotations

import json
import unittest

from my_actor.fec.messages import RULES, SIGNALS, rule_message
from my_actor.fec.report import build_report, compute_score, compute_verdict, report_for_llm
from helpers import check, entry, row


class TestScore(unittest.TestCase):
    def test_clean_is_100(self) -> None:
        self.assertEqual(compute_score({}, {}, []), 100)

    def test_error_caps_at_49(self) -> None:
        self.assertEqual(compute_score({'num_gap': 1}, {}, []), 49)

    def test_volume_lowers_score(self) -> None:
        few = compute_score({'a': 1, 'b': 1, 'c': 1, 'd': 1, 'e': 1, 'f': 1}, {}, [])
        many = compute_score({'a': 10_000, 'b': 1, 'c': 1, 'd': 1, 'e': 1, 'f': 1}, {}, [])
        self.assertLess(many, few)

    def test_warnings_and_signals(self) -> None:
        self.assertEqual(compute_score({}, {'zero_line': 3}, []), 98)
        self.assertEqual(compute_score({}, {}, ['high', 'medium', 'low']), 83)
        self.assertEqual(compute_score({}, {f'w{i}': 1 for i in range(9)}, []), 90)  # warnings capped at -10

    def test_floor_is_zero(self) -> None:
        self.assertEqual(compute_score({f'r{i}': 10**6 for i in range(20)}, {}, []), 0)

    def test_verdict(self) -> None:
        self.assertEqual(compute_verdict(True, True), 'invalid')
        self.assertEqual(compute_verdict(False, True), 'valid_with_warnings')
        self.assertEqual(compute_verdict(False, False), 'valid')


class TestMessages(unittest.TestCase):
    def test_every_rule_has_both_languages(self) -> None:
        for catalogue in (RULES, SIGNALS):
            for key, entry_ in catalogue.items():
                self.assertTrue(entry_['fr'], key)
                self.assertTrue(entry_['en'], key)

    def test_missing_param_does_not_crash(self) -> None:
        self.assertIn('?', rule_message('num_gap', 'en'))

    def test_language(self) -> None:
        rows = [row(num='1', debit='100,00'), row(num='1', account='706000', credit='90,00')]
        result = check(rows)
        fr = build_report(result, 'fr')
        en = build_report(result, 'en')
        fr_msg = next(g for g in fr['errors'] if g['rule'] == 'entry_unbalanced')['occurrences'][0]['message']
        en_msg = next(g for g in en['errors'] if g['rule'] == 'entry_unbalanced')['occurrences'][0]['message']
        self.assertIn('déséquilibrée', fr_msg)
        self.assertIn('Unbalanced', en_msg)
        self.assertIn('10,00', en_msg)


class TestReport(unittest.TestCase):
    def test_shape_for_clean_file(self) -> None:
        report = build_report(check(entry('1') + entry('2')), 'en')
        self.assertEqual(report['verdict'], 'valid')
        self.assertEqual(report['score'], 100)
        self.assertEqual(report['errors'], [])
        self.assertIsNone(report['aiSummary'])
        json.dumps(report)  # serializable

    def test_errors_and_warnings_are_split(self) -> None:
        rows = entry('1') + [row(num='1')] + [row(num='2', debit='5,00', credit='5,00')]
        report = build_report(check(rows), 'en')
        self.assertIn('debit_and_credit', [g['rule'] for g in report['errors']])
        self.assertIn('zero_line', [g['rule'] for g in report['warnings']])
        self.assertEqual(report['verdict'], 'invalid')

    def test_truncated_flag(self) -> None:
        rows = [row(num=str(n), debit='1,00', credit='1,00') for n in range(1, 11)]
        report = build_report(check(rows, max_issues=3), 'en')
        group = next(g for g in report['errors'] if g['rule'] == 'debit_and_credit')
        self.assertTrue(group['truncated'])
        self.assertEqual(group['count'], 10)


class TestLlmPayload(unittest.TestCase):
    def test_no_raw_values_or_labels(self) -> None:
        rows = entry('1')
        rows[0][5] = 'SECRET-ACCOUNT-LABEL'
        rows[0][10] = 'SECRET-ENTRY-LABEL Jean Dupont'
        rows[0][9] = 'SECRET-DATE'
        rows[1][11] = '12.34'  # bad decimal: the raw value must not leak either
        report = build_report(check(rows), 'en')
        self.assertIn('SECRET-DATE', json.dumps(report))  # the full report keeps values for the user
        payload = json.dumps(report_for_llm(report))
        for secret in ('SECRET', 'Jean Dupont', '12.34'):
            self.assertNotIn(secret, payload)
        self.assertIn('date_format', payload)
        self.assertIn('decimal_point', payload)


if __name__ == '__main__':
    unittest.main()
