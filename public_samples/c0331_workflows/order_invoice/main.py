"""Public synthetic purchase order -> detailed invoice CSV; standard-library only."""
import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    resource = Path(__file__).resolve().parent / 'data' / 'orders.csv'
    with resource.open(encoding='utf-8-sig', newline='') as fp:
        entries = list(csv.DictReader(fp))
    out = []
    sum_amount = Decimal('0.00')
    for r in entries:
        if not r['sku'].strip() or not r['client'].strip():
            raise ValueError('MISSING_ORDER_FIELD')
        qty = int(r['quantity'])
        price = Decimal(r['unit_price'])
        if qty <= 0 or price < 0:
            raise ValueError('INVALID_QUANTITY_OR_PRICE')
        total = price * qty
        sum_amount += total
        out.append({'client': r['client'], 'sku': r['sku'], 'amount': f'{total:.2f}'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as fp:
        w = csv.DictWriter(fp, fieldnames=['client', 'sku', 'amount'], lineterminator='\n')
        w.writeheader()
        w.writerows(out)
    print(json.dumps({'kind': 'invoice', 'rows': len(out), 'amount': f'{sum_amount:.2f}'}, sort_keys=True))

if __name__ == '__main__':
    main()
