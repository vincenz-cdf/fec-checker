# FEC Checker

**[English](#english) · [Français](#français)**

> **Technical check, not tax advice.** FEC Checker tests a file against the published format rules and flags unusual patterns. It does not certify a file, replace an accountant's review, or tell you how the tax administration will judge your accounts.
>
> **Contrôle technique, pas un conseil fiscal.** FEC Checker vérifie un fichier au regard des règles de format publiées et signale des schémas inhabituels. Il ne certifie pas un fichier, ne remplace pas la revue d'un expert-comptable et ne préjuge pas de l'appréciation de l'administration fiscale.

---

## English

Check a French **FEC** (*Fichier des Écritures Comptables*) before you hand it to the tax administration. FEC Checker reads the file, applies the format rules of **article A47 A-1 du Livre des procédures fiscales**, flags the patterns a tax auditor looks at, and returns one JSON report with a verdict, a 0-100 score and the line number of every problem. It can add an AI-written, prioritized fix list.

**Try it now:** run the Actor with an empty input. It checks a bundled synthetic FEC and shows a full report. Demo runs are not charged.

### Use cases

- **Before a tax audit (*contrôle fiscal*).** A rejected FEC can lead to a fine and a tougher audit. Check the export first and fix it while you still can.
- **Accounting firms.** Check every client's FEC at year end with the same rules, and keep the JSON report as a record of the check.
- **Accounting-software vendors and integrators.** Test your FEC export against the rules in CI, or after each release.
- **Auditors and CFOs.** Spot risky entries fast: weekend postings, round amounts, a cash account in the red, an uncleared suspense account, entries after the closing date.
- **AI agents.** One call in, one JSON report out, with stable rule codes an agent can act on.

### Your FEC file

**You don't build it by hand.** Every French accounting package exports the FEC, usually from its year-end or tax menu: look for "FEC", "Fichier des écritures comptables" or "Export DGFiP" (Sage, Cegid, EBP, ACD, Pennylane, Quadra…). Upload that export as it is. Don't open and re-save it in a spreadsheet: that is the most common way to break the separator, the dates or the accents.

It is a text file with one header line, then one line per accounting line of every entry in the fiscal year, opening balances (*à-nouveaux*) included. Fields are separated by a tab or a pipe (`|`).

The 18 columns, in this order (art. A47 A-1 LPF):

| # | Column | Content | Format | Empty allowed? | Example |
|---|---|---|---|---|---|
| 1 | JournalCode | Journal code | text | no | `VE` |
| 2 | JournalLib | Journal name | text | no | `Ventes` |
| 3 | EcritureNum | Entry number, on a continuous sequence | text or number | no | `000039` |
| 4 | EcritureDate | Accounting date | date `AAAAMMJJ` | no | `20250610` |
| 5 | CompteNum | General ledger account number | text | no | `411000` |
| 6 | CompteLib | Account name | text | no | `Clients` |
| 7 | CompAuxNum | Sub-ledger account (customer, supplier) | text | yes | `CLI001` |
| 8 | CompAuxLib | Sub-ledger account name | text | only if 7 is empty | `Atelier Durand` |
| 9 | PieceRef | Supporting document reference (invoice no.) | text | no | `F2025-06` |
| 10 | PieceDate | Document date | date `AAAAMMJJ` | no | `20250610` |
| 11 | EcritureLib | Entry label | text | no | `Facture F2025-06` |
| 12 | Debit | Debit amount | amount, decimal comma, no thousands separator | no (`0,00` if none) | `3960,00` |
| 13 | Credit | Credit amount | amount, same format | no (`0,00` if none) | `0,00` |
| 14 | EcritureLet | Matching (lettrage) code | text | yes | `AA` |
| 15 | DateLet | Matching date | date `AAAAMMJJ` | only if 14 is empty | `20250712` |
| 16 | ValidDate | Date the entry was validated (became final) | date `AAAAMMJJ` | no | `20250610` |
| 17 | Montantdevise | Amount in foreign currency | amount | yes | `1200,00` |
| 18 | Idevise | Currency code | text | only if 17 is empty | `USD` |

Optional columns stay in the header even when they are empty. One entry (one `EcritureNum`) spans several lines whose debits and credits balance. A complete sale, with its three lines:

```text
JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|EcritureLet|DateLet|ValidDate|Montantdevise|Idevise
VE|Ventes|000039|20250610|411000|Clients|CLI001|Atelier Durand|F2025-06|20250610|Facture F2025-06 Atelier Durand|3960,00|0,00|||20250610||
VE|Ventes|000039|20250610|706000|Prestations de services|||F2025-06|20250610|Facture F2025-06 Atelier Durand|0,00|3300,00|||20250610||
VE|Ventes|000039|20250610|445710|TVA collectee|||F2025-06|20250610|Facture F2025-06 Atelier Durand|0,00|660,00|||20250610||
```

To see a full example and its report, run the Actor with an empty input: it checks a bundled 214-line synthetic FEC.

Not covered: the Montant/Sens layout (one signed amount instead of Debit/Credit) and the 21- or 22-column files of cash-basis BNC and agricultural filers.

### What it checks

#### Format rules (errors)

| Rule | What is checked |
|---|---|
| `file_name` | File name is `SIRENFECAAAAMMJJ.txt` (the SIREN Luhn key is checked too, as a warning) |
| `separator` | Tab or pipe (`\|`) separator |
| `header_*` | Exactly the 18 mandatory columns, spelled and ordered as the law requires (see [Your FEC file](#your-fec-file)) |
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

#### Risk signals

| Signal | Trigger |
|---|---|
| `weekend_postings`, `holiday_postings` | Entries dated on a Saturday, Sunday or French public holiday (the opening-entries date is ignored) |
| `round_amounts` | 5% or more of lines are multiples of 1,000 € |
| `benford_deviation` | First-digit distribution fails Benford's law (chi-square, p < 0.01, at least 300 amounts ≥ 10 €) |
| `negative_cash_balance` | A 53x cash account goes into credit at any date |
| `suspense_account_not_cleared` | A 471 suspense account is not zero at year end |
| `entries_after_fiscal_year_end` | Lines dated after the fiscal year end |

### Input

| Field | Type | Description |
|---|---|---|
| `fecFile` | file upload or URL | The FEC file (.txt, tab- or pipe-separated, UTF-8 or ISO-8859-15), or a .zip holding it. Leave empty for the demo. |
| `language` | `fr` / `en` | Language of the messages and of the AI summary. Default `fr`. |
| `includeAiReport` | boolean | Add an AI-written, prioritized fix list (`aiSummary`). Default `false`. |
| `fiscalYearEnd` | date | Closing date, YYYY-MM-DD. Optional; defaults to the date in the file name. |
| `fileName` | string | Original file name, when the upload or URL does not keep it. Optional. |
| `maxIssuesPerRule` | integer | How many occurrences are listed per rule (all are counted). Default 50. |
| `deleteUploadedFile` | boolean | Delete the file uploaded through the form once the report is written. Default `true`. |

Example:

```json
{
    "fecFile": "https://example.com/123456782FEC20251231.txt",
    "language": "en",
    "includeAiReport": true,
    "fiscalYearEnd": "2025-12-31"
}
```

### Output

One dataset row per file (also saved as the `REPORT` record in the key-value store):

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
    "aiSummary": { "status": "ok", "model": "claude-haiku-5-5", "summary": "...", "fixes": [{ "priority": 1, "severity": "blocking", "title": "...", "rules": ["entry_unbalanced"], "action": "...", "where": "..." }] },
    "demo": false,
    "uploadedFileDeleted": true
}
```

- **`verdict`**: `valid`, `valid_with_warnings` or `invalid`.
- **`score`**: starts at 100. Each failed error rule costs 10 points plus up to 10 more as its count grows, each warning rule costs 2 (10 at most), and each risk signal costs 2, 5 or 10 by level. Any error caps the score at 49.
- **`errors` / `warnings`**: one group per rule, with the total count and the first occurrences (line number, field, entry, value, message).
- **`aiSummary`**: `null` unless `includeAiReport` is on. Its `status` is `ok`, `skipped` or `failed`.

### Pricing

Pay per event (see the **Pricing** tab for the amounts):

- **`fec-file-checked`**: once per checked file.
- **`ai-report`**: once per AI summary, only when it was produced.

The demo (empty input) is not charged for `fec-file-checked`.

### Privacy

- **Only the report is kept.** The Actor's working copy of your file is deleted as soon as the check ends. A file uploaded through the input form is deleted from your Apify storage once the report is written (turn off `deleteUploadedFile` to keep it). Files given by an external URL are never touched.
- **No line of your file is logged.** Logs contain the file name, its size and the counts.
- The report shows the offending value of each listed occurrence (for example `20250230`) so you can find it, and nothing else from the file.
- **AI summary:** written by Claude (Anthropic) from a stripped-down report: rule codes, counts, line numbers and summary statistics. No line, account label, entry label or field value is sent.
- The Actor runs with **limited permissions**: it can only reach its own storages and what you give it as input.

### FAQ

**Is a file with verdict `valid` guaranteed to be accepted in a tax audit?**
No. FEC Checker checks the published format rules and flags unusual patterns. The administration also judges the content of your accounts, which no automatic check can do.

**What is the difference between an error, a warning and a risk signal?**
An error breaks a format rule of article A47 A-1: the file should be fixed and regenerated. A warning is unusual but allowed. A risk signal is a pattern auditors often look at, such as weekend postings or round amounts; it can have a perfectly good explanation.

**What files can I upload?**

| You upload | What happens |
|---|---|
| A `.txt` FEC (tab or pipe, UTF-8 or ISO-8859-15) | Checked |
| A `.zip` holding exactly one `.txt` FEC | Unzipped, then checked; the name of the file inside is used for the naming rule |
| A UTF-16 export (Excel's "Unicode text") | Checked, with an `encoding_utf16` warning |
| The same content as `.csv` | Checked; the `file_name` rule fails, because the checker expects the usual `.txt` extension |
| A semicolon-separated file | Reported with the `separator_semicolon` error: re-export with tab or pipe |
| A PDF, Excel file, image, XML or other non-text file | Refused before the check, with a message saying what was received; not charged |

**Does it support the Montant/Sens layout or XML files?**
Not yet. It supports the Debit/Credit layout in a flat .txt file, tab- or pipe-separated, which is what most accounting software exports.

**My file is huge. Will it work?**
Yes. The file is read line by line: a 1-million-line FEC is checked in about 10 seconds within 1 GB of memory.

**My export has entries numbered per journal. Is that an error?**
No. FEC Checker detects whether numbering is global or per journal and checks gaps and duplicates within each sequence.

**Why does the `file_name` rule fail on a file I uploaded?**
The upload may not keep the original name. Put it in `fileName` (for example `123456782FEC20251231.txt`).

**Why is the 1 January opening entry not a holiday posting?**
Opening balances (*à-nouveaux*) are normally dated on the first day of the year. The earliest date in the file is left out of the weekend and holiday signals.

**Can I check several files?**
One file per run. Start one run per file, or call the Actor from a script or an agent for each file.

**Is my data used to train AI?**
No file content is sent to the AI, only the stripped-down report. The AI summary is optional and off by default.

### Limits

- Only the Debit/Credit layout is supported (not Montant/Sens), and only flat `.txt` files (not XML).
- Public holidays are the 11 national ones; Alsace-Moselle extras are not included.
- One file per run.

---

## Français

Vérifiez votre **FEC** (*Fichier des Écritures Comptables*) avant de le remettre à l'administration fiscale. FEC Checker lit le fichier, applique les règles de format de l'**article A47 A-1 du Livre des procédures fiscales**, signale les schémas qu'un vérificateur examine, et renvoie un rapport JSON avec un verdict, un score de 0 à 100 et le numéro de ligne de chaque anomalie. Il peut y ajouter une liste de corrections priorisée, rédigée par IA.

**Essayez tout de suite :** lancez l'Actor avec une entrée vide. Il contrôle un FEC de démonstration fictif et affiche un rapport complet. Les exécutions de démonstration ne sont pas facturées.

### Cas d'usage

- **Avant un contrôle fiscal.** Un FEC non conforme peut entraîner une amende et un contrôle plus approfondi. Vérifiez l'export d'abord et corrigez-le tant qu'il est temps.
- **Cabinets d'expertise comptable.** Contrôlez le FEC de chaque client à la clôture avec les mêmes règles, et conservez le rapport JSON comme trace du contrôle.
- **Éditeurs de logiciels comptables et intégrateurs.** Testez votre export FEC dans votre intégration continue ou après chaque version.
- **Auditeurs et directeurs financiers.** Repérez vite les écritures à risque : écritures le week-end, montants ronds, caisse créditrice, compte d'attente non soldé, écritures après la clôture.
- **Agents IA.** Un appel, un rapport JSON, avec des codes de règle stables sur lesquels un agent peut agir.

### Votre fichier FEC

**Vous ne le construisez pas à la main.** Tous les logiciels comptables français exportent le FEC, en général depuis le menu de clôture ou le menu fiscal : cherchez « FEC », « Fichier des écritures comptables » ou « Export DGFiP » (Sage, Cegid, EBP, ACD, Pennylane, Quadra…). Envoyez cet export tel quel. Ne l'ouvrez pas pour le réenregistrer dans un tableur : c'est la façon la plus courante de casser le séparateur, les dates ou les accents.

C'est un fichier texte : une ligne d'en-tête, puis une ligne par ligne d'écriture de l'exercice, à-nouveaux compris. Les zones sont séparées par une tabulation ou une barre verticale (`|`).

Les 18 colonnes, dans cet ordre (art. A47 A-1 LPF) :

| N° | Colonne | Contenu | Format | Peut être vide ? | Exemple |
|---|---|---|---|---|---|
| 1 | JournalCode | Code du journal | texte | non | `VE` |
| 2 | JournalLib | Libellé du journal | texte | non | `Ventes` |
| 3 | EcritureNum | Numéro de l'écriture, sur une séquence continue | texte ou nombre | non | `000039` |
| 4 | EcritureDate | Date de comptabilisation | date `AAAAMMJJ` | non | `20250610` |
| 5 | CompteNum | Numéro de compte général | texte | non | `411000` |
| 6 | CompteLib | Libellé du compte | texte | non | `Clients` |
| 7 | CompAuxNum | Compte auxiliaire (client, fournisseur) | texte | oui | `CLI001` |
| 8 | CompAuxLib | Libellé du compte auxiliaire | texte | seulement si la 7 est vide | `Atelier Durand` |
| 9 | PieceRef | Référence de la pièce (n° de facture) | texte | non | `F2025-06` |
| 10 | PieceDate | Date de la pièce | date `AAAAMMJJ` | non | `20250610` |
| 11 | EcritureLib | Libellé de l'écriture | texte | non | `Facture F2025-06` |
| 12 | Debit | Montant au débit | montant, virgule décimale, sans séparateur de milliers | non (`0,00` à défaut) | `3960,00` |
| 13 | Credit | Montant au crédit | montant, même format | non (`0,00` à défaut) | `0,00` |
| 14 | EcritureLet | Code de lettrage | texte | oui | `AA` |
| 15 | DateLet | Date de lettrage | date `AAAAMMJJ` | seulement si la 14 est vide | `20250712` |
| 16 | ValidDate | Date de validation de l'écriture (devenue définitive) | date `AAAAMMJJ` | non | `20250610` |
| 17 | Montantdevise | Montant en devise | montant | oui | `1200,00` |
| 18 | Idevise | Code de la devise | texte | seulement si la 17 est vide | `USD` |

Les colonnes facultatives restent dans l'en-tête même vides. Une écriture (un `EcritureNum`) s'étend sur plusieurs lignes dont les débits et les crédits s'équilibrent. Une vente complète, sur trois lignes :

```text
JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|EcritureLet|DateLet|ValidDate|Montantdevise|Idevise
VE|Ventes|000039|20250610|411000|Clients|CLI001|Atelier Durand|F2025-06|20250610|Facture F2025-06 Atelier Durand|3960,00|0,00|||20250610||
VE|Ventes|000039|20250610|706000|Prestations de services|||F2025-06|20250610|Facture F2025-06 Atelier Durand|0,00|3300,00|||20250610||
VE|Ventes|000039|20250610|445710|TVA collectee|||F2025-06|20250610|Facture F2025-06 Atelier Durand|0,00|660,00|||20250610||
```

Pour voir un exemple complet et son rapport, lancez l'Actor avec une entrée vide : il contrôle un FEC fictif de 214 lignes fourni avec l'Actor.

Non couverts : le format Montant/Sens (un montant signé au lieu de Débit/Crédit) et les fichiers à 21 ou 22 colonnes des BNC et bénéfices agricoles en comptabilité de trésorerie.

### Ce qui est contrôlé

#### Règles de format (erreurs)

| Règle | Contrôle |
|---|---|
| `file_name` | Le nom du fichier est `SIRENFECAAAAMMJJ.txt` (la clé de Luhn du SIREN est aussi vérifiée, en avertissement) |
| `separator` | Séparateur tabulation ou barre verticale (`\|`) |
| `header_*` | Exactement les 18 colonnes obligatoires, orthographiées et ordonnées comme l'exige le texte (voir [Votre fichier FEC](#votre-fichier-fec)) |
| `field_count` | Chaque ligne a autant de champs que l'en-tête |
| `required_field`, `pair_incomplete` | Les champs obligatoires sont renseignés ; CompAuxNum/CompAuxLib, EcritureLet/DateLet et Montantdevise/Idevise vont ensemble |
| `date_format`, `date_invalid` | Les dates sont au format `AAAAMMJJ` et existent (pas de 30 février) |
| `amount_format`, `decimal_point` | Les montants utilisent la virgule décimale |
| `debit_and_credit` | Une ligne a un débit ou un crédit, pas les deux |
| `entry_unbalanced`, `file_unbalanced` | Débit = crédit pour chaque écriture (EcritureNum) et pour tout le fichier |
| `entry_date_mismatch` | Toutes les lignes d'une écriture ont la même EcritureDate |
| `num_gap`, `num_duplicate`, `entry_not_contiguous` | Pas de rupture ni de doublon dans EcritureNum (numérotation globale ou par journal détectée automatiquement) |
| `validdate_not_chronological` | Les dates de validation suivent l'ordre des numéros |

Avertissements : lignes vides, lignes à zéro, montants négatifs, date de validation antérieure à la date d'écriture, clé du SIREN, date du nom de fichier différente de la date de clôture saisie.

#### Signaux de risque

| Signal | Déclencheur |
|---|---|
| `weekend_postings`, `holiday_postings` | Écritures datées un samedi, un dimanche ou un jour férié (la date des à-nouveaux est ignorée) |
| `round_amounts` | Au moins 5 % des lignes sont des multiples de 1 000 € |
| `benford_deviation` | La distribution des premiers chiffres s'écarte de la loi de Benford (khi-deux, p < 0,01, au moins 300 montants ≥ 10 €) |
| `negative_cash_balance` | Un compte de caisse 53x devient créditeur à une date quelconque |
| `suspense_account_not_cleared` | Un compte d'attente 471 n'est pas soldé à la clôture |
| `entries_after_fiscal_year_end` | Lignes datées après la date de clôture |

### Entrée

| Champ | Type | Description |
|---|---|---|
| `fecFile` | fichier ou URL | Le FEC (.txt, séparé par tabulations ou barres verticales, UTF-8 ou ISO-8859-15), ou un .zip qui le contient. Laissez vide pour la démonstration. |
| `language` | `fr` / `en` | Langue des messages et du résumé IA. Par défaut `fr`. |
| `includeAiReport` | booléen | Ajoute une liste de corrections priorisée rédigée par IA (`aiSummary`). Par défaut `false`. |
| `fiscalYearEnd` | date | Date de clôture, AAAA-MM-JJ. Facultatif ; par défaut, la date du nom de fichier. |
| `fileName` | texte | Nom d'origine du fichier, si l'envoi ou l'URL ne le conserve pas. Facultatif. |
| `maxIssuesPerRule` | entier | Nombre d'occurrences listées par règle (toutes sont comptées). Par défaut 50. |
| `deleteUploadedFile` | booléen | Supprime le fichier envoyé via le formulaire une fois le rapport écrit. Par défaut `true`. |

Exemple :

```json
{
    "fecFile": "https://example.com/123456782FEC20251231.txt",
    "language": "fr",
    "includeAiReport": true,
    "fiscalYearEnd": "2025-12-31"
}
```

### Sortie

Une ligne de dataset par fichier (aussi enregistrée dans l'enregistrement `REPORT` du key-value store). La structure est celle de l'exemple en anglais ci-dessus ; avec `"language": "fr"`, les messages sont en français :

```json
{
    "rule": "entry_unbalanced",
    "count": 1,
    "occurrences": [
        { "line": 95, "entry": "VE/000039", "message": "Écriture déséquilibrée : écart débit - crédit de 100,00." }
    ]
}
```

- **`verdict`** : `valid`, `valid_with_warnings` ou `invalid`.
- **`score`** : part de 100. Chaque règle d'erreur en échec coûte 10 points, plus jusqu'à 10 selon le nombre d'occurrences ; chaque règle d'avertissement coûte 2 points (10 au plus) ; chaque signal de risque coûte 2, 5 ou 10 points selon son niveau. Toute erreur plafonne le score à 49.
- **`aiSummary`** : `null` sauf si `includeAiReport` est activé. Son `status` vaut `ok`, `skipped` ou `failed`.

### Tarifs

Paiement à l'événement (montants dans l'onglet **Pricing**) :

- **`fec-file-checked`** : une fois par fichier contrôlé.
- **`ai-report`** : une fois par résumé IA, seulement s'il a été produit.

La démonstration (entrée vide) n'est pas facturée pour `fec-file-checked`.

### Confidentialité

- **Seul le rapport est conservé.** La copie de travail de votre fichier est supprimée dès la fin du contrôle. Un fichier envoyé via le formulaire est supprimé de votre stockage Apify une fois le rapport écrit (désactivez `deleteUploadedFile` pour le garder). Les fichiers fournis par une URL externe ne sont jamais touchés.
- **Aucune ligne de votre fichier n'est journalisée.** Les logs contiennent le nom du fichier, sa taille et les décomptes.
- Le rapport affiche la valeur en cause de chaque occurrence listée (par exemple `20250230`) pour que vous puissiez la retrouver, et rien d'autre du fichier.
- **Résumé IA :** rédigé par Claude (Anthropic) à partir d'un rapport allégé : codes de règle, décomptes, numéros de ligne et statistiques. Aucune ligne, aucun libellé de compte ou d'écriture, aucune valeur n'est envoyé.
- L'Actor fonctionne avec des **permissions limitées** : il n'accède qu'à ses propres stockages et à ce que vous lui fournissez en entrée.

### FAQ

**Un fichier au verdict `valid` sera-t-il forcément accepté lors d'un contrôle fiscal ?**
Non. FEC Checker vérifie les règles de format publiées et signale des schémas inhabituels. L'administration apprécie aussi le contenu de votre comptabilité, ce qu'aucun contrôle automatique ne peut faire.

**Quelle différence entre une erreur, un avertissement et un signal de risque ?**
Une erreur enfreint une règle de format de l'article A47 A-1 : le fichier doit être corrigé et régénéré. Un avertissement est inhabituel mais admis. Un signal de risque est un schéma que les vérificateurs examinent souvent, comme des écritures le week-end ou des montants ronds ; il peut avoir une explication tout à fait légitime.

**Quels fichiers puis-je envoyer ?**

| Vous envoyez | Résultat |
|---|---|
| Un FEC `.txt` (tabulation ou barre verticale, UTF-8 ou ISO-8859-15) | Contrôlé |
| Un `.zip` contenant un seul FEC `.txt` | Décompressé puis contrôlé ; le nom du fichier contenu sert pour la règle de nommage |
| Un export UTF-16 (« texte Unicode » d'Excel) | Contrôlé, avec l'avertissement `encoding_utf16` |
| Le même contenu en `.csv` | Contrôlé ; la règle `file_name` échoue, car l'outil attend l'extension usuelle `.txt` |
| Un fichier séparé par des points-virgules | Signalé par l'erreur `separator_semicolon` : réexportez avec tabulation ou barre verticale |
| Un PDF, un fichier Excel, une image, un XML ou tout autre fichier non texte | Refusé avant le contrôle, avec un message indiquant ce qui a été reçu ; non facturé |

**Le format Montant/Sens ou les fichiers XML sont-ils acceptés ?**
Pas encore. Le format Débit/Crédit en fichier .txt à plat, séparé par tabulations ou barres verticales, est accepté : c'est ce qu'exportent la plupart des logiciels comptables.

**Mon fichier est très volumineux. Est-ce que ça fonctionne ?**
Oui. Le fichier est lu ligne par ligne : un FEC d'un million de lignes est contrôlé en une dizaine de secondes avec moins de 1 Go de mémoire.

**Mon export numérote les écritures par journal. Est-ce une erreur ?**
Non. FEC Checker détecte si la numérotation est globale ou par journal, et contrôle les ruptures et doublons dans chaque séquence.

**Pourquoi la règle `file_name` échoue-t-elle sur un fichier que j'ai envoyé ?**
L'envoi ne conserve pas toujours le nom d'origine. Indiquez-le dans `fileName` (par exemple `123456782FEC20251231.txt`).

**Pourquoi l'écriture d'à-nouveaux du 1er janvier n'est-elle pas signalée comme jour férié ?**
Les à-nouveaux sont normalement datés du premier jour de l'exercice. La date la plus ancienne du fichier est exclue des signaux week-end et jours fériés.

**Puis-je contrôler plusieurs fichiers ?**
Un fichier par exécution. Lancez une exécution par fichier, ou appelez l'Actor depuis un script ou un agent pour chaque fichier.

**Mes données servent-elles à entraîner une IA ?**
Aucun contenu du fichier n'est envoyé à l'IA, seulement le rapport allégé. Le résumé IA est facultatif et désactivé par défaut.

### Limites

- Seul le format Débit/Crédit est accepté (pas Montant/Sens), et seulement en fichier `.txt` à plat (pas XML).
- Les jours fériés sont les 11 jours fériés nationaux ; ceux propres à l'Alsace-Moselle ne sont pas inclus.
- Un fichier par exécution.

---

## Development

```bash
python -m unittest discover -s tests       # unit tests (stdlib only)
python test_data/generate_samples.py       # regenerate the 5 synthetic FEC files and the demo file
apify run                                  # run locally with storage/key_value_stores/default/INPUT.json
```

Environment variables for the Actor owner: `ANTHROPIC_API_KEY` (secret, needed for the AI summary), `FEC_AI_MODEL` (default `claude-haiku-5-5`; set `claude-sonnet-5-5` or `claude-opus-5-5` for a stronger model), `FEC_MAX_FILE_MB` (default 2048).

Example task inputs for Apify Console are in [`tasks/`](tasks/).
