# Example tasks

Three saved tasks to create in Apify Console after `apify push`, each with its own public page. For each one: open the Actor, click **Save as a new task**, paste the JSON file as the input, set the name, title and description below, then make the task public in its **Settings**.

None of them sets `fecFile`. A visitor who runs the task as it is gets the bundled demo report (not charged). To check their own file, they upload it in the task's input form.

## 1. Check a FEC before a tax audit

- **Name:** `check-fec-before-tax-audit`
- **Input:** [check-fec-before-tax-audit.json](check-fec-before-tax-audit.json)
- **Title:** Check a FEC before a tax audit (contrôle fiscal)
- **Description:** Validate your Fichier des Écritures Comptables against article A47 A-1 LPF before handing it to the tax administration: file name, the 18 columns, dates, decimal comma, balance per entry and numbering gaps. French report with an AI-written, prioritized fix list. Technical check, not tax advice.

## 2. Find risky entries in a FEC

- **Name:** `find-risky-entries-in-fec`
- **Input:** [find-risky-entries-in-fec.json](find-risky-entries-in-fec.json)
- **Title:** Find risky entries in a French FEC
- **Description:** Flag the entries a tax auditor looks at first: weekend and public-holiday postings, round amounts, Benford's-law deviation, cash accounts (53x) in the red, uncleared suspense accounts (471) and entries after the closing date. Lists up to 500 lines per finding. English report.

## 3. Check a FEC with an English report

- **Name:** `check-fec-english-report`
- **Input:** [check-fec-english-report.json](check-fec-english-report.json)
- **Title:** Check a French FEC with an English report
- **Description:** For auditors, group finance teams and investors outside France: validate a French FEC (Fichier des Écritures Comptables) and get the full report and an AI-written fix list in English, with the line number of every issue. Technical check, not tax advice.

"Bulk-check client files" is not offered: the Actor checks one file per run.
