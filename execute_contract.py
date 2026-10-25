"""One-document contract-only executor with safe preview and explicit commit gate."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid

from config import BusinessRules
from esf_preflight import preflight
from main import read_json
from odata_client import DEFAULT_APPLICATION_URL, ODataError, ReadOnlyOData
from processor.executor import patch_contract
from processor.planner import plan_one


def prepare(client: ReadOnlyOData, pending: dict, contracts: dict, ref_key: str, number: str) -> dict:
    ref_key = str(uuid.UUID(ref_key))
    scope = pending.get("scope") or {}
    entries = [p for p in pending.get("pending", []) if p.get("ref_key") == ref_key and p.get("number") == number]
    if pending.get("mode") != "read_only" or len(entries) != 1:
        raise ValueError("Exactly one matching ESF must be in the reviewed pending queue")
    org = str(uuid.UUID(scope.get("organization_key", "")))
    counterparty = str(uuid.UUID(scope.get("counterparty_key", "")))
    dates = (dt.date.fromisoformat(scope["from_date"]), dt.date.fromisoformat(scope["to_date"]))
    if contracts.get("status") != "unique" or len(contracts.get("candidates", [])) != 1:
        raise ValueError("Expected one unambiguous contract")
    contract = contracts["candidates"][0]
    if contracts.get("organization_key") != org or str(contract.get("Owner_Key", "")).lower() != counterparty:
        raise ValueError("Contract is not scoped to selected organization and counterparty")
    document = preflight(client, ref_key, expected_number=number)
    header = document["header"]
    if header["Организация_Key"] != org or str(header.get("Контрагент_Key", "")).lower() != counterparty:
        raise ValueError("Live ESF organization or counterparty changed")
    doc_date = dt.date.fromisoformat(header["Date"][:10])
    if not dates[0] <= doc_date <= dates[1] or header["Date"] != entries[0]["date"]:
        raise ValueError("Live ESF date is outside the approved scope or differs from pending report")
    plan = plan_one(document, contracts, BusinessRules())
    if plan["status"] != "ready_for_review":
        raise ValueError(f"ESF plan not ready: {plan['status']} {plan.get('blockers')}")
    updates = [a for a in plan["actions"] if a["action"] == "set_contract"]
    if len(updates) != 1 or updates[0]["field"] != "ДоговорПоставки_Key":
        raise ValueError("Expected exactly one unfilled contract field; refusing modification")
    return {"number": number, "ref_key": ref_key, "contract_ref_key": updates[0]["value"],
            "scope": scope, "patch_body": {"ДоговорПоставки_Key": updates[0]["value"]},
            "other_fields_modified": False}


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview or execute ONE contract-only ESF PATCH")
    parser.add_argument("--pending", required=True)
    parser.add_argument("--contracts", required=True)
    parser.add_argument("--ref-key", required=True)
    parser.add_argument("--number", required=True)
    parser.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    parser.add_argument("--commit", action="store_true", help="Allow ONE PATCH after all guards pass")
    parser.add_argument("--confirm", help="Must exactly equal: PATCH <number> when --commit is used")
    args = parser.parse_args(argv)
    if args.commit and args.confirm != f"PATCH {args.number}":
        parser.error("Commit requires --confirm 'PATCH <exact number>'")
    try:
        client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""),
                               os.getenv("ONEC_ODATA_PASSWORD", ""))
        prepared = prepare(client, read_json(args.pending), read_json(args.contracts),
                           args.ref_key, args.number)
        if not args.commit:
            print(json.dumps({"mode": "preview_only", **prepared,
                              "note": "No PATCH was sent. Explicit approval is required for the first live write."},
                             ensure_ascii=False, indent=2))
            return 0
        status = patch_contract(client, prepared["ref_key"], prepared["contract_ref_key"])
        # If verification fails, never issue another PATCH automatically.
        verified = preflight(client, prepared["ref_key"], args.number)
        actual = verified["header"]["ДоговорПоставки_Key"]
        if str(actual).lower() != prepared["contract_ref_key"].lower():
            raise ODataError("PATCH returned success but contract value did not verify; stop")
        print(json.dumps({"mode": "committed_and_verified", "number": args.number,
                          "ref_key": prepared["ref_key"], "patch_status": status,
                          "contract_ref_key": actual}, ensure_ascii=False, indent=2))
        return 0
    except (ODataError, ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
