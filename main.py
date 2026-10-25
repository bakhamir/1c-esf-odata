"""CLI for the complete dry-run ESF processor. There are no write operations."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from collections import Counter
from pathlib import Path

from config import BusinessRules
from esf_preflight import preflight
from odata_client import DEFAULT_APPLICATION_URL, ODataError, ReadOnlyOData
from processor.planner import plan_one


def read_json(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def report(plans: list[dict], source: str) -> dict:
    counts = Counter(p["status"] for p in plans)
    return {"mode": "dry_run", "source": source, "documents": len(plans),
            "summary": dict(sorted(counts.items())), "plans": plans,
            "warning": "Planning only. No data has been modified in 1C."}


def plan_batch(pending: dict, contracts: dict, client: ReadOnlyOData, limit: int,
               expected_from: str | None = None, expected_to: str | None = None) -> dict:
    if pending.get("mode") != "read_only" or pending.get("entity") != "Document_ЭСФ":
        raise ValueError("Unrecognized pending ESF report")
    scope = pending.get("scope") or {}
    begin, end = scope.get("from_date"), scope.get("to_date")
    if not begin or not end:
        raise ValueError("Pending report needs an explicit period")
    first, last = dt.date.fromisoformat(begin), dt.date.fromisoformat(end)
    if first > last:
        raise ValueError("Invalid pending date range")
    if (expected_from is not None and begin != expected_from) or (expected_to is not None and end != expected_to):
        raise ValueError("Pending scope does not match the requested date range")
    organization = scope.get("organization_key")
    if not organization or not str(organization):
        raise ValueError("Pending report must be restricted to an explicit organization")
    organization = str(uuid.UUID(organization))
    if organization != contracts.get("organization_key"):
        raise ValueError("Contract lookup organization differs from pending report")
    counterparty = scope.get("counterparty_key")
    if not counterparty:
        raise ValueError("Prototype requires --counterparty-key in pending report; rescan supplier-specific period")
    counterparty = str(uuid.UUID(counterparty))
    candidates = contracts.get("candidates") or []
    if len(candidates) != 1 or str(candidates[0].get("Owner_Key", "")).lower() != counterparty:
        raise ValueError("Contract owner must match the pending supplier scope")
    entries = pending.get("pending")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Pending report contains no documents")
    if limit > len(entries):
        raise ValueError("--limit exceeds the available pending report entries")
    plans = []
    for entry in entries[:limit]:
        ref_key = entry.get("ref_key")
        number = entry.get("number")
        try:
            if not ref_key or not number:
                raise ValueError("Missing Ref_Key or Number in pending report")
            document = preflight(client, ref_key, expected_number=number)
            if document["header"].get("Организация_Key") != organization:
                raise ValueError("ESF organization differs from pending scope")
            current_date = dt.date.fromisoformat(str(document["header"].get("Date", ""))[:10])
            if not first <= current_date <= last:
                raise ValueError("ESF date differs from pending scope")
            if str(document["header"].get("Контрагент_Key", "")).lower() != counterparty:
                raise ValueError("ESF counterparty differs from pending supplier scope")
            plans.append(plan_one(document, contracts, BusinessRules()))
        except (ODataError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            plans.append({"mode": "dry_run", "esf_number": number, "esf_ref_key": ref_key,
                          "status": "read_error", "actions": [], "blockers": [str(exc)],
                          "execution_supported": False})
    return report(plans, "live_read_only_batch")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ESF processor: strictly dry-run, with no HTTP writes")
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("plan-one", help="Plan from existing local preflight and contract files")
    one.add_argument("--preflight", required=True)
    one.add_argument("--contracts", required=True)
    one.add_argument("--output", required=True)
    batch = commands.add_parser("plan-batch", help="Recheck selected ESFs live through GET and plan them")
    batch.add_argument("--pending", required=True)
    batch.add_argument("--contracts", required=True)
    batch.add_argument("--expected-from-date", required=True, help="Require matching YYYY-MM-DD in queue")
    batch.add_argument("--expected-to-date", required=True, help="Require matching inclusive YYYY-MM-DD in queue")
    batch.add_argument("--limit", required=True, type=int, help="Maximum entries to plan, 1..200")
    batch.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    batch.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        contracts = read_json(args.contracts)
        if args.command == "plan-one":
            preflight_data = read_json(args.preflight)
            result = report([plan_one(preflight_data, contracts)], "local_json")
        else:
            if not 1 <= args.limit <= 200:
                parser.error("--limit must be from 1 to 200")
            pending = read_json(args.pending)
            client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""),
                                   os.getenv("ONEC_ODATA_PASSWORD", ""))
            result = plan_batch(pending, contracts, client, args.limit,
                                args.expected_from_date, args.expected_to_date)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": args.output, "documents": result["documents"],
                          "summary": result["summary"], "mode": "dry_run"}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, ODataError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
