"""Read-only preflight report for one ESF before any document creation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from odata_client import DEFAULT_APPLICATION_URL, ODataError, ReadOnlyOData, parse_collection


ENTITY = "Document_ЭСФ"
HEADER_FIELDS = (
    "Ref_Key", "Number", "Date", "Posted", "Контрагент_Key", "Организация_Key", "СчетФактура",
    "СчетФактура_Type", "ДоговорПоставки_Key", "ДоговорПоставкиНомер",
    "ДокументПодтверждающийПоставкуНомер",
    "ДокументПодтверждающийПоставкуАВРНомер",
)


def preflight(client: ReadOnlyOData, ref_key: str, expected_number: str | None = None) -> dict:
    ref_key = str(uuid.UUID(ref_key))
    payload = client.get(ENTITY, {
        "$format": "json", "$top": 2,
        "$filter": f"Ref_Key eq guid'{ref_key}'",
    })
    rows = parse_collection(payload)
    if len(rows) != 1:
        raise ODataError(f"Expected one ESF by Ref_Key; got {len(rows)}")
    row = rows[0]
    if str(row.get("Ref_Key", "")).lower() != ref_key:
        raise ODataError("Returned Ref_Key does not match requested ESF")
    if expected_number is not None and row.get("Number") != expected_number:
        raise ODataError("Returned ESF number does not match --expected-number")

    table = row.get("Товары")
    if isinstance(table, dict) and isinstance(table.get("results"), list):
        table = table["results"]
    if not isinstance(table, list):
        raise ODataError("ESF field 'Товары' is missing or not an array; inspect raw OData response")

    line_items = []
    for idx, item in enumerate(table, start=1):
        if not isinstance(item, dict):
            raise ODataError("Unexpected item type in ESF's Товары collection")
        interesting = {k: v for k, v in item.items()
                       if k in ("Товар", "Товар_Type") or any(t in k.casefold() for t in
                              ("наимен", "номенклат", "единиц", "едизм", "услуг", "сервис", "кодтовар"))}
        line_items.append({"line": idx, "fields": interesting, "available_field_names": sorted(item)})

    header = {name: row.get(name) for name in HEADER_FIELDS}
    missing = [name for name in HEADER_FIELDS if name not in row]
    return {
        "mode": "read_only", "entity": ENTITY, "header": header,
        "missing_header_fields": missing, "item_count": len(line_items), "items": line_items,
        "is_candidate": row.get("СчетФактура") in (None, "") and row.get("СчетФактура_Type") == "StandardODATA.Undefined",
        "supply_number_status": "unverified: compare with F. Документы поставки / Номер in the UI",
        "contract_status": "unverified: ДоговорПоставки_Key must resolve to ALA-58/2025 SD",
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight of one specific ESF")
    parser.add_argument("--ref-key", required=True, help="Exact GUID from pending_esf.json")
    parser.add_argument("--expected-number", help="Require matching document Number")
    parser.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    parser.add_argument("--output", help="Save UTF-8 JSON report")
    args = parser.parse_args(argv)
    try:
        client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""),
                               os.getenv("ONEC_ODATA_PASSWORD", ""))
        result = preflight(client, args.ref_key, args.expected_number)
        text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
            print(f"Saved UTF-8 preflight report: {args.output}")
        else:
            print(text)
        return 0
    except (ValueError, ODataError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
