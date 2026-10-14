"""Public synthetic Korean customer notices from bundled safe UTF-8 template."""
import argparse
import csv
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    base = Path(__file__).resolve().parent
    template = (base / 'data' / 'notice.txt').read_text(encoding='utf-8')
    with (base / 'data' / 'customers.csv').open(encoding='utf-8-sig', newline='') as fp:
        customers = list(csv.DictReader(fp))
    docs = []
    for row in customers:
        code = row['code']
        if not code.isascii() or not code.isalnum():
            raise ValueError('UNSAFE_DOCUMENT_ID')
        body = template.replace('{name}', row['name']).replace('{date}', row['date'])
        docs.append((code+'.txt', body))
    args.output.mkdir(parents=True, exist_ok=True)
    for name,body in docs:
        (args.output/name).write_text(body, encoding='utf-8')
    print(json.dumps({'kind': 'document', 'rows': len(docs), 'names': sorted(n for n,_ in docs)}, sort_keys=True))

if __name__ == '__main__':
    main()
