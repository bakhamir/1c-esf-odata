"""Prepare a receipt continuation from saved files only; no write mode."""
import argparse
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from plan_invoice import document
from processor.receipt_planner import plan_linked_receipt


def collection(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_float=Decimal)
    wrapped = obj.get('d', obj) if isinstance(obj, dict) else None
    if not isinstance(wrapped, dict):
        raise ValueError('Invalid saved collection')
    if any(container.get(k) for container in (obj, wrapped)
           for k in ('__next', '@odata.nextLink', 'odata.nextLink')):
        raise ValueError('Partial saved collection')
    rows = wrapped.get('results', wrapped.get('value'))
    if not isinstance(rows, list) or len(rows) >= 20 or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Invalid or potentially truncated receipt lookup')
    return rows


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    names = ('metadata', 'esf', 'invoice', 'reference-invoice', 'reference-receipt', 'catalogs', 'output')
    for name in names:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--existing-receipts', help='Saved complete exact-backlink GET result')
    args = parser.parse_args(argv)
    inputs = [Path(getattr(args, name.replace('-', '_'))).resolve() for name in names if name != 'output']
    if args.existing_receipts:
        inputs.append(Path(args.existing_receipts).resolve())
    if Path(args.output).resolve() in inputs:
        parser.error('Output must not overwrite evidence')
    try:
        catalogs = json.loads(Path(args.catalogs).read_text(encoding='utf-8-sig'))
        report = plan_linked_receipt(Path(args.metadata).read_bytes(), document(args.esf), document(args.invoice),
                                     document(args.reference_invoice), document(args.reference_receipt), catalogs,
                                     collection(args.existing_receipts) if args.existing_receipts else None)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'mode': report['mode'], 'status': report['status'],
                          'create_invoice_again': False, 'candidate_rows': len(report['receipt_service_candidates']),
                          'blocker_count': len(report['blockers'])}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError):
        print('Receipt planning failed: invalid, out-of-scope or incomplete evidence')
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
