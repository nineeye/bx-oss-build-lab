"""Public synthetic inventory reorder report, with bundled JSON rule configuration."""
import argparse
import csv
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    base = Path(__file__).resolve().parent
    rules = json.loads((base / 'data' / 'settings.json').read_text(encoding='utf-8'))
    threshold = rules['reorder_below']
    results = []
    with (base / 'data' / 'stock.csv').open(encoding='utf-8-sig', newline='') as fp:
        for r in csv.DictReader(fp):
            qty = int(r['stock'])
            if qty < 0:
                raise ValueError('NEGATIVE_STOCK')
            if qty < threshold:
                results.append({'sku': r['sku'], 'stock': qty, 'order': threshold - qty})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n', encoding='utf-8')
    print(json.dumps({'kind': 'reorder', 'rows': len(results), 'reorder_total': sum(x['order'] for x in results)}, sort_keys=True))

if __name__ == '__main__':
    main()
