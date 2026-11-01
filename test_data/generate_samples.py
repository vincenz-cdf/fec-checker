"""Generate synthetic FEC files for testing: one valid file and four with a single known defect each.

Run from the repository root: python test_data/generate_samples.py
All data is fictitious (SIREN 123456782, fiscal year 2025-01-01 to 2025-12-31).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

OUT_DIR = Path(__file__).parent / 'fec'
SIREN = '123456782'
CLOSING = '20251231'
SEP = '|'

HEADER = [
    'JournalCode', 'JournalLib', 'EcritureNum', 'EcritureDate', 'CompteNum', 'CompteLib',
    'CompAuxNum', 'CompAuxLib', 'PieceRef', 'PieceDate', 'EcritureLib', 'Debit', 'Credit',
    'EcritureLet', 'DateLet', 'ValidDate', 'Montantdevise', 'Idevise',
]

JOURNALS = {
    'AN': 'A-nouveaux',
    'AC': 'Achats',
    'VE': 'Ventes',
    'BQ': 'Banque',
    'OD': 'Operations diverses',
}

ACCOUNTS = {
    '101000': 'Capital',
    '401000': 'Fournisseurs',
    '411000': 'Clients',
    '445660': 'TVA deductible sur ABS',
    '445710': 'TVA collectee',
    '512000': 'Banque',
    '606100': 'Fournitures non stockables',
    '613200': 'Locations immobilieres',
    '626000': 'Frais postaux et telecom',
    '641000': 'Remunerations du personnel',
    '421000': 'Personnel remunerations dues',
    '706000': 'Prestations de services',
}

CLIENTS = {'CLI001': 'Atelier Durand', 'CLI002': 'Boulangerie Martin', 'CLI003': 'Cabinet Lefevre'}
SUPPLIERS = {'FOU001': 'Bureau Plus', 'FOU002': 'SCI Les Tilleuls', 'FOU003': 'Telecom Ouest'}


def sale(date: str, piece: str, client: str, ht: str) -> tuple:
    ht_d = Decimal(ht)
    tva = (ht_d * Decimal('0.20')).quantize(Decimal('0.01'))
    return ('VE', date, piece, f'Facture {piece} {CLIENTS[client]}', [
        ('411000', client, ht_d + tva, 0),
        ('706000', None, 0, ht_d),
        ('445710', None, 0, tva),
    ])


def purchase(date: str, piece: str, supplier: str, account: str, ht: str) -> tuple:
    ht_d = Decimal(ht)
    tva = (ht_d * Decimal('0.20')).quantize(Decimal('0.01'))
    return ('AC', date, piece, f'Facture {piece} {SUPPLIERS[supplier]}', [
        (account, None, ht_d, 0),
        ('445660', None, tva, 0),
        ('401000', supplier, 0, ht_d + tva),
    ])


def receipt(date: str, piece: str, client: str, ttc: str) -> tuple:
    amount = Decimal(ttc)
    return ('BQ', date, piece, f'Reglement {CLIENTS[client]}', [
        ('512000', None, amount, 0),
        ('411000', client, 0, amount),
    ])


def payment(date: str, piece: str, supplier: str, ttc: str) -> tuple:
    amount = Decimal(ttc)
    return ('BQ', date, piece, f'Paiement {SUPPLIERS[supplier]}', [
        ('401000', supplier, amount, 0),
        ('512000', None, 0, amount),
    ])


def salary(date: str, piece: str, amount: str) -> list[tuple]:
    amount_d = Decimal(amount)
    return [
        ('OD', date, piece, 'Salaires du mois', [('641000', None, amount_d, 0), ('421000', None, 0, amount_d)]),
        ('BQ', date, piece + 'V', 'Virement salaires', [('421000', None, amount_d, 0), ('512000', None, 0, amount_d)]),
    ]


def weekday(month: int, day: int) -> str:
    """2025-month-day as AAAAMMJJ, moved back to the Friday when it falls on a weekend."""
    d = date(2025, month, day)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime('%Y%m%d')


def build_entries() -> list[tuple]:
    entries = [
        ('AN', '20250101', 'AN2025', 'Reprise des soldes', [
            ('512000', None, Decimal('15000.00'), 0),
            ('101000', None, 0, Decimal('15000.00')),
        ]),
    ]
    for month in range(1, 13):
        mm = f'{month:02d}'
        client = list(CLIENTS)[month % 3]
        ht = f'{2400 + month * 150}.00'
        ttc = str((Decimal(ht) * Decimal('1.20')).quantize(Decimal('0.01')))
        entries.append(purchase(weekday(month, 5), f'FL{mm}', 'FOU002', '613200', '1200.00'))
        entries.append(sale(weekday(month, 10), f'F2025-{mm}', client, ht))
        entries.append(purchase(weekday(month, 12), f'FT{mm}', 'FOU003', '626000', '89.90'))
        if month % 3 == 0:
            entries.append(purchase(weekday(month, 15), f'FB{mm}', 'FOU001', '606100', '235.40'))
        entries.extend(salary(weekday(month, 28), f'SAL{mm}', '2100.00'))
        if month < 12:
            entries.append(receipt(weekday(month, 25), f'RC{mm}', client, ttc))
            entries.append(payment(weekday(month, 20), f'PL{mm}', 'FOU002', '1440.00'))
    # Stable sort by date keeps the order within a day; numbering then follows chronology.
    entries.sort(key=lambda e: e[1])
    return entries


def fmt_amount(value: Decimal | int) -> str:
    return f'{Decimal(value):.2f}'.replace('.', ',')


def to_rows(entries: list[tuple]) -> list[list[str]]:
    rows = []
    for num, (journal, date, piece, label, lines) in enumerate(entries, start=1):
        for account, aux, debit, credit in lines:
            aux_lib = CLIENTS.get(aux) or SUPPLIERS.get(aux) or '' if aux else ''
            rows.append([
                journal, JOURNALS[journal], f'{num:06d}', date, account, ACCOUNTS[account],
                aux or '', aux_lib, piece, date, label, fmt_amount(debit), fmt_amount(credit),
                '', '', date, '', '',
            ])
    return rows


def write(case: str, header: list[str], rows: list[list[str]], out_dir: Path = OUT_DIR) -> None:
    """Each case gets its own folder so every file keeps the legal name SIRENFECAAAAMMJJ.txt."""
    lines = [SEP.join(header)] + [SEP.join(row) for row in rows]
    path = out_dir / case / f'{SIREN}FEC{CLOSING}.txt'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(('\r\n'.join(lines) + '\r\n').encode('utf-8'))
    print(f'{path}: {len(rows)} lines')


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    base_rows = to_rows(build_entries())

    # 1. Valid file.
    write('valid', HEADER, base_rows)

    # 2. Wrong headers: one column renamed, two columns swapped, last column missing.
    bad_header = HEADER.copy()
    bad_header[3] = 'DateEcriture'
    bad_header[11], bad_header[12] = bad_header[12], bad_header[11]
    write('bad_headers', bad_header[:-1], [r[:-1] for r in base_rows])

    # 3. Unbalanced entry: the credit side of the first June sale is 100,00 short.
    rows = [r.copy() for r in base_rows]
    target = next(r for r in rows if r[8] == 'F2025-06' and r[4] == '706000')
    target[12] = fmt_amount(Decimal(target[12].replace(',', '.')) - 100)
    write('unbalanced', HEADER, rows)

    # 4. Numbering gap: entries after the July rent invoice are shifted by +3 (3 numbers missing).
    rows = [r.copy() for r in base_rows]
    gap_from = int(next(r for r in rows if r[8] == 'FL07')[2]) + 1
    for r in rows:
        if int(r[2]) >= gap_from:
            r[2] = f'{int(r[2]) + 3:06d}'
    write('numbering_gap', HEADER, rows)

    # 5. Bad dates, each on every line of one entry: impossible date, wrong format,
    #    date after the fiscal year end, validation date out of chronological order.
    rows = [r.copy() for r in base_rows]
    for piece, column, value in (('FL02', 3, '20250230'), ('FT04', 3, '12/04/2025'),
                                 ('F2025-09', 3, '20260110'), ('RC10', 15, '20251001')):
        for r in rows:
            if r[8] == piece:
                r[column] = value
    write('bad_dates', HEADER, rows)
    # The Actor checks this file when started with an empty input: it shows errors, warnings and signals.
    write('demo', HEADER, rows, out_dir=Path(__file__).parent.parent / 'my_actor')


if __name__ == '__main__':
    main()
