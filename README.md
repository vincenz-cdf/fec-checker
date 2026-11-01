# FEC Checker

Check a French **FEC** (*Fichier des Écritures Comptables*) before you hand it to the tax administration. FEC Checker reads the file, applies the format rules of **article A47 A-1 du Livre des procédures fiscales**, flags the patterns a tax auditor looks at, and returns one JSON report with a verdict, a 0-100 score and the line number of every problem. It can also add an AI-written, prioritized fix list.

It is built for accountants, auditors, CFOs and accounting-software vendors who want to catch a rejected FEC before a *contrôle fiscal* does.

## What it checks

### Format rules (errors)

| Rule | What is checked |
|---|---|
| `file_name` | File name is `SIRENFECAAAAMMJJ.txt` (SIREN Luhn key is checked too, as a warning) |
| `separator` | Tab or pipe (`\|`) separator |
| `header_*` | Exactly the 18 mandatory columns, spelled and ordered as the law requires: JournalCode, JournalLib, EcritureNum, EcritureDate, CompteNum, CompteLib, CompAuxNum, CompAuxLib, PieceRef, PieceDate, EcritureLib, Debit, Credit, EcritureLet, DateLet, ValidDate, Montantdevise, Idevise |
| `field_count` | Every line has as many fields as the header |
| `required_field`, `pair_incomplete` | Mandatory fields are filled; CompAuxNum/CompAuxLib, EcritureLet/DateLet and Montantdevise/Idevise are filled together |
| `date_format`, `date_invalid` | Dates are `AAAAMMJJ` and exist (no 30 February) |
| `amount_format`, `decimal_point` | Amounts use a decimal comma |
| `debit_and_credit` | A line has a debit or a credit, not both |
| `entry_unbalanced`, `file_unbalanced` | Debit = credit for every entry (EcritureNum) and for the whole file |
| `entry_date_mismatch` | All lines of an entry share one EcritureDate |
| `num_gap`, `num_duplicate`, `entry_not_contiguous` | EcritureNum has no gaps and no duplicates (global or per-journal numbering is detected automatically) |
| `validdate_not_chronological` | Validation dates follow the numbering order |

Warnings: empty lines, zero lines, negative amounts, validation date before entry date, SIREN checksum, file-name date different from the fiscal year end you entered.

### Risk signals

| Signal | Trigger |
|---|---|
| `weekend_postings`, `holiday_postings` | Entries dated on a Saturday, Sunday or French public holiday (the opening-entries date is ignored) |
| `round_amounts` | 5% or more of lines are multiples of 1,000 € |
| `benford_deviation` | First-digit distribution fails Benford's law (chi-square, p < 0.01, at least 300 amounts ≥ 10 €) |
| `negative_cash_balance` | A 53x cash account goes into credit at any date |
| `suspense_account_not_cleared` | A 471 suspense account is not zero at year end |
| `entries_after_fiscal_year_end` | Lines dated after the fiscal year end |

## Input

| Field | Type | Description |
|---|---|---|
| `fecFile` | file upload or URL | The FEC file (.txt, tab- or pipe-separated, UTF-8 or ISO-8859-15). Required. |
| `language` | `fr` / `en` | Language of messages. Default `fr`. |
| `includeAiReport` | boolean | Add an AI-written, prioritized fix list. Default `false`. |
| `fiscalYearEnd` | date | Closing date. Optional; defaults to the date in the file name. |
| `fileName` | string | Original file name, when the upload or URL does not keep it. Optional. |
| `maxIssuesPerRule` | integer | How many occurrences are listed per rule (all are counted). Default 50. |

```json
{
    "fecFile": "https://example.com/123456782FEC20251231.txt",
    "language": "en",
    "includeAiReport": true,
    "fiscalYearEnd": "2025-12-31"
}
```

## Output

One dataset item (also saved as the `REPORT` record in the key-value store):

```json
{
    "fileName": "123456782FEC20251231.txt",
    "verdict": "invalid",
    "score": 49,
    "summary": { "errorCount": 2, "errorRuleCount": 2, "warningCount": 0, "warningRuleCount": 0, "riskSignalCount": 0, "fatal": false },
    "errors": [
        {
            "rule": "entry_unbalanced",
            "severity": "error",
            "count": 1,
            "truncated": false,
            "occurrences": [
                { "line": 95, "field": null, "entry": "VE/000039", "value": null, "message": "Unbalanced entry: debit - credit difference of 100,00." }
            ]
        }
    ],
    "warnings": [],
    "riskSignals": [],
    "stats": { "encoding": "utf-8", "separator": "pipe", "lineCount": 214, "entryCount": 87, "totalDebit": "193104,48", "totalCredit": "193004,48", "fiscalYearEnd": "2025-12-31", "numberingScope": "global" },
    "skippedChecks": [],
    "aiReport": { "status": "ok", "model": "claude-opus-5-5", "summary": "...", "fixes": [{ "priority": 1, "severity": "blocking", "title": "...", "rules": ["entry_unbalanced"], "action": "...", "where": "..." }] }
}
```

**Verdict** is `valid`, `valid_with_warnings` or `invalid`. **Score** starts at 100. Each failed error rule costs 10 points plus up to 10 more as its count grows, each warning rule costs 2 (10 at most), and each risk signal costs 2, 5 or 10 by level. Any error caps the score at 49.

## Privacy and the AI report

The AI fix list is written by Claude (Anthropic). **Only the report is sent: rule codes, counts, line numbers and summary statistics.** No file line, account label, entry label or field value leaves the Actor. The downloaded file is deleted when the check ends.

## Pricing

Pay per event:

- `fec-file-checked`: once per checked file.
- `ai-report`: once per AI fix list, only when it was produced.

## Limits

- Files of 1 million lines and more are streamed and fit in 1 GB of memory.
- Only the Debit/Credit layout is supported (not the Montant/Sens variant), and only `.txt` flat files (not XML).
- Public holidays are the 11 national ones; Alsace-Moselle extras are not included.
- This tool helps you prepare a file. It is not a certification and not tax advice.

## Development

```bash
python -m unittest discover -s tests       # unit tests (stdlib only)
python test_data/generate_samples.py       # regenerate the 5 synthetic FEC files
apify run                                  # run locally with storage/key_value_stores/default/INPUT.json
```

Environment variables for the Actor owner: `ANTHROPIC_API_KEY` (secret, needed for the AI report), `FEC_AI_MODEL` (default `claude-opus-5-5`), `FEC_MAX_FILE_MB` (default 2048).
