"""Turn a ValidationResult into the JSON report: localized messages, score and verdict."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from my_actor.fec.messages import ERROR, RULES, rule_message, signal_message
from my_actor.fec.validator import ValidationResult

ERROR_RULE_PENALTY = 10
ERROR_VOLUME_PENALTY_MAX = 10
WARNING_RULE_PENALTY = 2
WARNING_PENALTY_MAX = 10
SIGNAL_PENALTY = {'high': 10, 'medium': 5, 'low': 2}
INVALID_SCORE_CAP = 49


def compute_score(error_counts: dict[str, int], warning_counts: dict[str, int], signal_levels: list[str]) -> int:
    """100 minus penalties. Each failing error rule costs 10, plus up to 10 more as its count grows
    (log10); each warning rule costs 2 (10 at most); each risk signal costs 2/5/10 by level.
    A file with any error is capped at 49 so the score never contradicts an 'invalid' verdict."""
    score = 100.0
    for count in error_counts.values():
        score -= ERROR_RULE_PENALTY + min(ERROR_VOLUME_PENALTY_MAX, 2 * math.log10(max(count, 1)))
    score -= min(WARNING_PENALTY_MAX, WARNING_RULE_PENALTY * len(warning_counts))
    score -= sum(SIGNAL_PENALTY[level] for level in signal_levels)
    if error_counts:
        score = min(score, INVALID_SCORE_CAP)
    return max(0, min(100, round(score)))


def compute_verdict(has_errors: bool, has_warnings_or_signals: bool) -> str:
    if has_errors:
        return 'invalid'
    return 'valid_with_warnings' if has_warnings_or_signals else 'valid'


def build_report(result: ValidationResult, language: str) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    for rule, issues in result.issues.items():
        severity = RULES[rule]['severity']
        group = {
            'rule': rule,
            'severity': severity,
            'count': issues.count,
            'truncated': issues.count > len(issues.occurrences),
            'occurrences': [
                {
                    'line': o.line,
                    'field': o.field,
                    'entry': o.entry,
                    'value': o.value,
                    'message': rule_message(rule, language, field=o.field, **o.params),
                }
                for o in issues.occurrences
            ],
        }
        (errors if severity == ERROR else warnings).append(group)
    errors.sort(key=_group_order)
    warnings.sort(key=_group_order)

    signals = [
        {**s, 'message': signal_message(s['signal'], language, count=s['count'], **s['details'])}
        for s in result.risk_signals
    ]
    error_counts = {g['rule']: g['count'] for g in errors}
    warning_counts = {g['rule']: g['count'] for g in warnings}
    score = compute_score(error_counts, warning_counts, [s['level'] for s in signals])

    return {
        'fileName': result.file_name,
        'checkedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'language': language,
        'verdict': compute_verdict(bool(errors), bool(warnings or signals)),
        'score': score,
        'summary': {
            'errorCount': sum(error_counts.values()),
            'errorRuleCount': len(errors),
            'warningCount': sum(warning_counts.values()),
            'warningRuleCount': len(warnings),
            'riskSignalCount': len(signals),
            'fatal': result.fatal,
        },
        'errors': errors,
        'warnings': warnings,
        'riskSignals': signals,
        'stats': result.stats,
        'skippedChecks': result.skipped_checks,
        'aiSummary': None,
    }


def _group_order(group: dict) -> tuple:
    first_line = next((o['line'] for o in group['occurrences'] if o['line'] is not None), 0)
    return (first_line, group['rule'])


def report_for_llm(report: dict) -> dict:
    """The report without raw field values or account labels: rules, counts, line numbers, stats only."""
    def strip(groups: list[dict]) -> list[dict]:
        return [
            {
                'rule': g['rule'],
                'count': g['count'],
                'message': g['occurrences'][0]['message'] if g['occurrences'] else None,
                'lines': [o['line'] for o in g['occurrences'][:10] if o['line'] is not None],
            }
            for g in groups
        ]

    stats = report['stats']
    return {
        'verdict': report['verdict'],
        'score': report['score'],
        'summary': report['summary'],
        'errors': strip(report['errors']),
        'warnings': strip(report['warnings']),
        'riskSignals': [
            {'signal': s['signal'], 'level': s['level'], 'count': s['count'], 'lines': s['lines'][:10]}
            for s in report['riskSignals']
        ],
        'stats': {
            k: stats.get(k)
            for k in ('encoding', 'separator', 'lineCount', 'entryCount', 'journalCount', 'accountCount',
                      'firstEntryDate', 'lastEntryDate', 'fiscalYearEnd', 'numberingScope')
        },
        'skippedChecks': report['skippedChecks'],
    }
