"""Find exact contract references using read-only OData queries."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from odata_client import DEFAULT_APPLICATION_URL, ODataError, ReadOnlyOData, parse_collection


ENTITY = "Catalog_ДоговорыКонтрагентов"
FIELDS = "Ref_Key,Description,НомерДоговора,Организация_Key,Owner_Key,DeletionMark,IsFolder"


def find_contract(client: ReadOnlyOData, number: str, organization_key: str,
                  owner_key: str | None = None) -> dict:
    if not number.strip():
        raise ValueError("Contract number must not be empty")
    org = str(uuid.UUID(organization_key))
    owner = str(uuid.UUID(owner_key)) if owner_key else None
    safe_number = number.replace("'", "''")
    conditions = [f"Организация_Key eq guid'{org}'", "DeletionMark eq false", "IsFolder eq false",
                  f"(НомерДоговора eq '{safe_number}' or Description eq '{safe_number}')"]
    if owner:
        conditions.append(f"Owner_Key eq guid'{owner}'")
    payload = client.get(ENTITY, {"$format": "json", "$top": 20, "$select": FIELDS,
                                  "$filter": " and ".join(conditions)})
    result = json.loads(payload)
    wrapped = result.get("d", result) if isinstance(result, dict) else {}
    if isinstance(wrapped, dict) and wrapped.get("__next"):
        raise ODataError("Contract results are paginated; refusing ambiguous lookup")
    rows = parse_collection(payload)
    if len(rows) >= 20:
        raise ODataError("Too many contract matches; narrow by owner GUID")
    candidates = [r for r in rows if
                  (r.get("НомерДоговора") == number or r.get("Description") == number)
                  and str(r.get("Организация_Key", "")).lower() == org
                  and not r.get("DeletionMark") and not r.get("IsFolder")]
    if owner:
        candidates = [r for r in candidates if str(r.get("Owner_Key", "")).lower() == owner]
    return {"mode": "read_only", "contract_number": number, "organization_key": org,
            "owner_key": owner, "match_count": len(candidates),
            "status": "unique" if len(candidates) == 1 else "not_found" if not candidates else "ambiguous",
            "candidates": candidates,
            "note": "A unique result is still to be matched with the 1C UI before write operations."}


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only lookup of 1C contract by number and organization")
    parser.add_argument("--number", required=True)
    parser.add_argument("--organization-key", required=True)
    parser.add_argument("--owner-key", help="Optional exact counterparty/owner GUID")
    parser.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    parser.add_argument("--output", help="Save UTF-8 JSON")
    args = parser.parse_args(argv)
    try:
        client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""),
                               os.getenv("ONEC_ODATA_PASSWORD", ""))
        result = find_contract(client, args.number, args.organization_key, args.owner_key)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
            print(f"Saved UTF-8 report: {args.output}")
        else:
            print(rendered)
        return 0
    except (ODataError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
