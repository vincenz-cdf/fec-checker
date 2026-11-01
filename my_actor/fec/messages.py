"""Rule catalogue: severity and French/English messages.

Messages never embed raw field values. Values travel in a separate `value` field so the AI report
payload can drop them.
"""

from __future__ import annotations

ERROR = 'error'
WARNING = 'warning'

RULES: dict[str, dict[str, str]] = {
    # File and header
    'file_name': {
        'severity': ERROR,
        'fr': 'Le nom du fichier doit suivre le format SIRENFECAAAAMMJJ.txt.',
        'en': 'The file name must follow the SIRENFECAAAAMMJJ.txt pattern.',
    },
    'file_name_date': {
        'severity': ERROR,
        'fr': 'La date de clôture du nom de fichier n\'est pas une date valide.',
        'en': 'The closing date in the file name is not a valid date.',
    },
    'siren_checksum': {
        'severity': WARNING,
        'fr': 'Le SIREN du nom de fichier ne respecte pas la clé de contrôle (Luhn).',
        'en': 'The SIREN in the file name fails the Luhn checksum.',
    },
    'fye_mismatch': {
        'severity': WARNING,
        'fr': 'La date de clôture du nom de fichier diffère de la date de clôture saisie ({input_date}).',
        'en': 'The closing date in the file name differs from the fiscal year end you entered ({input_date}).',
    },
    'separator': {
        'severity': ERROR,
        'fr': 'Séparateur introuvable : la ligne d\'en-tête doit être séparée par des tabulations ou des barres verticales.',
        'en': 'No separator found: the header line must be tab- or pipe-separated.',
    },
    'separator_semicolon': {
        'severity': ERROR,
        'fr': 'Le fichier est séparé par des points-virgules : l\'article A47 A-1 n\'admet que la tabulation ou la barre verticale (|). Réexportez le FEC depuis votre logiciel comptable.',
        'en': 'The file is semicolon-separated: article A47 A-1 only allows tab or pipe (|). Export the FEC again from your accounting software.',
    },
    'encoding_utf16': {
        'severity': WARNING,
        'fr': 'Le fichier est encodé en UTF-16 (export « texte Unicode » d\'Excel) : il a été lu, mais seuls l\'ASCII, l\'ISO-8859-15 et l\'UTF-8 sont prévus. Réexportez-le en UTF-8.',
        'en': 'The file is UTF-16 encoded (Excel "Unicode text" export): it was read, but only ASCII, ISO-8859-15 and UTF-8 are expected. Export it again as UTF-8.',
    },
    'header_count': {
        'severity': ERROR,
        'fr': 'L\'en-tête doit contenir exactement {expected} colonnes.',
        'en': 'The header must contain exactly {expected} columns.',
    },
    'header_missing': {
        'severity': ERROR,
        'fr': 'Colonne obligatoire absente de l\'en-tête : {field}.',
        'en': 'Mandatory column missing from the header: {field}.',
    },
    'header_unknown': {
        'severity': ERROR,
        'fr': 'Colonne non prévue par l\'article A47 A-1 dans l\'en-tête.',
        'en': 'Header column not defined by article A47 A-1.',
    },
    'header_order': {
        'severity': ERROR,
        'fr': 'Les colonnes de l\'en-tête ne sont pas dans l\'ordre réglementaire.',
        'en': 'The header columns are not in the required order.',
    },
    'header_case': {
        'severity': ERROR,
        'fr': 'Nom de colonne mal orthographié (majuscules/minuscules) : {field}.',
        'en': 'Column name has the wrong letter case: {field}.',
    },
    # Lines
    'empty_line': {
        'severity': WARNING,
        'fr': 'Ligne vide.',
        'en': 'Empty line.',
    },
    'field_count': {
        'severity': ERROR,
        'fr': 'La ligne ne contient pas le même nombre de champs que l\'en-tête ({expected}).',
        'en': 'The line does not have the same number of fields as the header ({expected}).',
    },
    'required_field': {
        'severity': ERROR,
        'fr': 'Champ obligatoire vide : {field}.',
        'en': 'Mandatory field is empty: {field}.',
    },
    'pair_incomplete': {
        'severity': ERROR,
        'fr': 'Les champs {pair} doivent être renseignés ensemble ; {field} est vide.',
        'en': 'Fields {pair} must be filled together; {field} is empty.',
    },
    'date_format': {
        'severity': ERROR,
        'fr': 'Date au mauvais format dans {field} (attendu AAAAMMJJ).',
        'en': 'Wrong date format in {field} (expected AAAAMMJJ).',
    },
    'date_invalid': {
        'severity': ERROR,
        'fr': 'Date inexistante dans {field}.',
        'en': 'Non-existent date in {field}.',
    },
    'amount_format': {
        'severity': ERROR,
        'fr': 'Montant illisible dans {field} (chiffres et virgule décimale uniquement).',
        'en': 'Unreadable amount in {field} (digits and a decimal comma only).',
    },
    'decimal_point': {
        'severity': ERROR,
        'fr': 'Le montant de {field} utilise un point décimal au lieu d\'une virgule.',
        'en': 'The amount in {field} uses a decimal point instead of a comma.',
    },
    'debit_and_credit': {
        'severity': ERROR,
        'fr': 'La ligne a un montant au débit et au crédit ; un seul des deux doit être renseigné.',
        'en': 'The line has both a debit and a credit amount; only one may be non-zero.',
    },
    'zero_line': {
        'severity': WARNING,
        'fr': 'Ligne à zéro au débit et au crédit.',
        'en': 'Line with zero debit and zero credit.',
    },
    'negative_amount': {
        'severity': WARNING,
        'fr': 'Montant négatif dans {field}.',
        'en': 'Negative amount in {field}.',
    },
    'validdate_before_entry': {
        'severity': WARNING,
        'fr': 'La date de validation est antérieure à la date de l\'écriture.',
        'en': 'The validation date is earlier than the entry date.',
    },
    # Entries
    'entry_unbalanced': {
        'severity': ERROR,
        'fr': 'Écriture déséquilibrée : écart débit - crédit de {difference}.',
        'en': 'Unbalanced entry: debit - credit difference of {difference}.',
    },
    'file_unbalanced': {
        'severity': ERROR,
        'fr': 'Le fichier est déséquilibré : total débit {total_debit}, total crédit {total_credit}, écart {difference}.',
        'en': 'The file is unbalanced: total debit {total_debit}, total credit {total_credit}, difference {difference}.',
    },
    'entry_date_mismatch': {
        'severity': ERROR,
        'fr': 'Les lignes d\'une même écriture n\'ont pas toutes la même EcritureDate.',
        'en': 'Lines of the same entry do not all share the same EcritureDate.',
    },
    'entry_not_contiguous': {
        'severity': ERROR,
        'fr': 'Numéro d\'écriture déjà utilisé plus haut dans le fichier (doublon ou écriture fractionnée).',
        'en': 'Entry number already used earlier in the file (duplicate or split entry).',
    },
    'num_duplicate': {
        'severity': ERROR,
        'fr': 'Numéro d\'écriture déjà utilisé dans le journal {other_journal}.',
        'en': 'Entry number already used in journal {other_journal}.',
    },
    'num_gap': {
        'severity': ERROR,
        'fr': 'Rupture de séquence : {missing_count} numéro(s) manquant(s), de {missing_from} à {missing_to}.',
        'en': 'Numbering gap: {missing_count} number(s) missing, from {missing_from} to {missing_to}.',
    },
    'validdate_not_chronological': {
        'severity': ERROR,
        'fr': 'Date de validation antérieure à celle de l\'écriture n° {previous_number} ({previous_date}) : la validation doit suivre l\'ordre des numéros.',
        'en': 'Validation date earlier than that of entry no. {previous_number} ({previous_date}): validation must follow numbering order.',
    },
}

SIGNALS: dict[str, dict[str, str]] = {
    'weekend_postings': {
        'fr': '{count} écriture(s) datée(s) un samedi ou un dimanche.',
        'en': '{count} entr(y/ies) dated on a Saturday or Sunday.',
    },
    'holiday_postings': {
        'fr': '{count} écriture(s) datée(s) un jour férié.',
        'en': '{count} entr(y/ies) dated on a French public holiday.',
    },
    'round_amounts': {
        'fr': '{count} ligne(s) avec un montant rond (multiple de 1 000), soit une part inhabituelle.',
        'en': '{count} line(s) with a round amount (multiple of 1,000), an unusual share.',
    },
    'benford_deviation': {
        'fr': 'La distribution des premiers chiffres des montants s\'écarte de la loi de Benford (khi-deux).',
        'en': 'The first-digit distribution of amounts deviates from Benford\'s law (chi-square).',
    },
    'negative_cash_balance': {
        'fr': 'Le compte de caisse {account} devient créditeur (solde négatif).',
        'en': 'Cash account {account} goes into a credit (negative) balance.',
    },
    'suspense_account_not_cleared': {
        'fr': 'Le compte d\'attente {account} n\'est pas soldé à la clôture.',
        'en': 'Suspense account {account} is not cleared at year end.',
    },
    'entries_after_fiscal_year_end': {
        'fr': '{count} ligne(s) datée(s) après la date de clôture.',
        'en': '{count} line(s) dated after the fiscal year end.',
    },
}


class _Blank(dict):
    def __missing__(self, key: str) -> str:
        return '?'


def rule_message(rule: str, language: str, **params: object) -> str:
    template = RULES[rule][language]
    return template.format_map(_Blank({k: v for k, v in params.items() if v is not None}))


def signal_message(signal: str, language: str, **params: object) -> str:
    template = SIGNALS[signal][language]
    return template.format_map(_Blank({k: v for k, v in params.items() if v is not None}))
