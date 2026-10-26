"""Offline observation CLI. Does not execute the experiment."""
import argparse
import json
from pathlib import Path

from plan_invoice import document
from processor.creation_observer import observe_creation


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'invoice', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    paths = [Path(getattr(args, name)).resolve() for name in ('before', 'after', 'invoice')]
    if Path(args.output).resolve() in paths:
        parser.error('Output must not overwrite input snapshots')
    try:
        report = observe_creation(*(document(path) for path in paths))
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': report['status'], 'execution_supported': False}))
        return 0
    except (ValueError, KeyError, TypeError, OSError):
        print('Observation failed: invalid or incomplete snapshots; inspect locally')
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
