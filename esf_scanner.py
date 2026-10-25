"""Read-only discovery of ESFs missing a linked received invoice.

Requires an explicit date range. Never mutates 1C data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

from odata_client import (
    DEFAULT_APPLICATION_URL,
    ODataError,
    ReadOnlyOData,
    parse_collection,
)


ENTITY = "Document_ЭСФ"
FIELDS = "Ref_Key,Number,Date,Организация_Key,Контрагент_Key,СчетФактура,СчетФактура_Type"


def date_range(start: str, end: str) -> tuple[str, str]:
    first = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    if first > last:
        raise ValueError("--from-date must be on or before --to-date")
    if (last - first).days > 366:
        raise ValueError("Date range must not exceed 366 days; narrow the scope")
    exclusive_end = last + dt.timedelta(days=1)
    return first.isoformat(), exclusive_end.isoformat()


def scan(client: ReadOnlyOData, from_date: str, to_date: str,
         organization_key: str | None = None, page_size: int = 100,
         max_pages: int = 100, counterparty_key: str | None = None) -> dict:
    first, end_exclusive = date_range(from_date, to_date)
    conditions = [
        f"Date ge datetime'{first}T00:00:00'",
        f"Date lt datetime'{end_exclusive}T00:00:00'",
        "DeletionMark eq false",
    ]
    if organization_key:
        organization_key = str(uuid.UUID(organization_key))
        conditions.append(f"Организация_Key eq guid'{organization_key}'")
    if counterparty_key:
        counterparty_key = str(uuid.UUID(counterparty_key))
        conditions.append(f"Контрагент_Key eq guid'{counterparty_key}'")

    pending, anomalies = [], []
    examined = 0
    for page in range(max_pages):
        params = {
            "$format": "json", "$select": FIELDS, "$filter": " and ".join(conditions),
            "$orderby": "Date asc,Ref_Key asc", "$top": page_size,
            "$skip": page * page_size,
        }
        payload = client.get(ENTITY, params)
        obj = json.loads(payload)
        envelope = obj.get("d", obj) if isinstance(obj, dict) else {}
        if isinstance(envelope, dict) and (envelope.get("__next") or envelope.get("@odata.nextLink")):
            raise ODataError("Server-side continuation detected; scanner does not support it yet")
        rows = parse_collection(payload)
        examined += len(rows)
        for row in rows:
            if any(name not in row for name in ("Ref_Key", "Number", "Date", "СчетФактура", "СчетФактура_Type")):
                raise ODataError("Missing required fields in ESF response; refusing incomplete scan")
            if organization_key and str(row.get("Организация_Key", "")).lower() != organization_key:
                raise ODataError("ESF organization differs from requested scope")
            if counterparty_key and str(row.get("Контрагент_Key", "")).lower() != counterparty_key:
                raise ODataError("ESF counterparty differs from requested scope")
            link, link_type = row["СчетФактура"], row["СчетФактура_Type"]
            record = {"ref_key": row["Ref_Key"], "number": row["Number"], "date": row["Date"]}
            if link in ("", None) and link_type == "StandardODATA.Undefined":
                pending.append(record)
            elif link in ("", None) or link_type == "StandardODATA.Undefined":
                anomalies.append({**record, "reason": "Inconsistent link and type; needs manual review"})
        if len(rows) < page_size:
            break
    else:
        raise ODataError("Reached --max-pages; incomplete scan not reported as final")

    return {
        "mode": "read_only", "entity": ENTITY,
        "scope": {"from_date": from_date, "to_date": to_date,
                  "organization_key": organization_key, "counterparty_key": counterparty_key},
        "examined": examined, "pending_count": len(pending), "pending": pending,
        "anomalies": anomalies,
        "warning": "This scan uses explicit API filters; it does not inherit the current 1C UI filters.",
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only scanner for ESFs with no linked invoice")
    parser.add_argument("--from-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--organization-key", help="Restrict to the specified organization GUID")
    parser.add_argument("--counterparty-key", help="Restrict to the specified supplier/counterparty GUID")
    parser.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--output", help="UTF-8 output JSON file")
    args = parser.parse_args(argv)
    if not 1 <= args.page_size <= 200 or not 1 <= args.max_pages <= 100:
        parser.error("page-size must be 1..200 and max-pages 1..100")
    try:
        client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""),
                               os.getenv("ONEC_ODATA_PASSWORD", ""))
        result = scan(client, args.from_date, args.to_date, args.organization_key,
                      args.page_size, args.max_pages, args.counterparty_key)
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
