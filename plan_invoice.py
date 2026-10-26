"""Offline CLI; imports no network client and never reads credentials."""
import argparse
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from processor.invoice_planner import plan_initial_invoice


def document(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_float=Decimal)
    if not isinstance(obj, dict):
        raise ValueError('Expected object or OData collection')
    wrapped = obj.get('d', obj)
    if not isinstance(wrapped, dict):
        raise ValueError('Invalid envelope')
    if any(container.get(k) for container in (obj, wrapped)
           for k in ('__next', '@odata.nextLink', 'odata.nextLink')):
        raise ValueError('Partial document response')
    rows = wrapped.get('results', wrapped.get('value'))
    if rows is not None:
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError('Expected exactly one document')
        return rows[0]
    return wrapped


def run(argv=None):
    parser = argparse.ArgumentParser(description='Offline initial invoice discovery plan')
    for name in ('metadata', 'target', 'source', 'invoice', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    paths = [Path(getattr(args, name)).resolve() for name in ('metadata', 'target', 'source', 'invoice')]
    if Path(args.output).resolve() in paths:
        parser.error('Output must not overwrite input evidence')
    try:
        result = plan_initial_invoice(paths[0].read_bytes(), *(document(p) for p in paths[1:]))
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'mode': result['mode'], 'status': result['status'],
                          'blocker_count': len(result['blockers']), 'execution_supported': False}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
        # Input values and parser errors can contain private data. Emit only a category.
        print('Offline planning failed: ' + type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
