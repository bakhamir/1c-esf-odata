"""Read-only inspection of already linked ESF -> received invoice examples."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

from odata_client import DEFAULT_APPLICATION_URL, ODataError, ReadOnlyOData, parse_collection


ESF = "Document_ЭСФ"
INVOICE = "Document_СчетФактураПолученный"
INVOICE_FIELDS = ("Ref_Key", "Number", "Date", "Posted", "ДокументОснование",
                  "ДокументОснование_Type", "ПодтвержденДокументамиОтгрузки",
                  "ДоговорКонтрагента_Key", "Организация_Key", "НомерВходящегоДокумента",
                  "ДатаВходящегоДокумента")


def inspect_examples(client: ReadOnlyOData, from_date: str, to_date: str,
                     organization_key: str, counterparty_key: str, limit: int = 1) -> dict:
    first, last = dt.date.fromisoformat(from_date), dt.date.fromisoformat(to_date)
    if first > last or (last - first).days > 366:
        raise ValueError("Invalid date scope")
    org, cp = str(uuid.UUID(organization_key)), str(uuid.UUID(counterparty_key))
    end = (last + dt.timedelta(days=1)).isoformat()
    params = {"$format": "json", "$top": 200,
              "$select": "Ref_Key,Number,Date,Организация_Key,Контрагент_Key,СчетФактура,СчетФактура_Type",
              "$filter": " and ".join((f"Date ge datetime'{first}T00:00:00'",
                                      f"Date lt datetime'{end}T00:00:00'",
                                      f"Организация_Key eq guid'{org}'",
                                      f"Контрагент_Key eq guid'{cp}'", "DeletionMark eq false"))}
    payload = client.get(ESF, params)
    envelope = json.loads(payload)
    if len(parse_collection(payload)) >= 200 or (isinstance(envelope, dict) and
            ((envelope.get("d") or {}).get("__next") if isinstance(envelope.get("d"), dict) else
             envelope.get("@odata.nextLink"))):
        raise ODataError("ESF response potentially paginated; narrow the time range")
    examples = []
    eligible_count = 0
    for row in parse_collection(payload):
        if str(row.get("Организация_Key", "")).lower() != org or str(row.get("Контрагент_Key", "")).lower() != cp:
            raise ODataError("Server returned ESF outside scope")
        reference = row.get("СчетФактура")
        if not reference or row.get("СчетФактура_Type") != "StandardODATA.Document_СчетФактураПолученный":
            continue
        eligible_count += 1
        if len(examples) >= limit:
            continue
        try:
            invoice_key = str(uuid.UUID(reference))
        except (ValueError, TypeError):
            examples.append({"esf_number": row.get("Number"), "unresolved_link": reference,
                             "warning": "Linked invoice is not a direct GUID; manual mapping required"})
            continue
        invoices = parse_collection(client.get(INVOICE, {"$format": "json", "$top": 2,
                                    "$filter": f"Ref_Key eq guid'{invoice_key}'"}))
        if len(invoices) != 1:
            examples.append({"esf_number": row.get("Number"), "invoice_ref_key": invoice_key,
                             "warning": f"Expected one received invoice; found {len(invoices)}"})
            continue
        inv = invoices[0]
        if str(inv.get("Ref_Key", "")).lower() != invoice_key or str(inv.get("Организация_Key", "")).lower() != org:
            raise ODataError("Received invoice reference or organization mismatch")
        sections = {}
        for name in ("Товары", "Услуги", "ДокументыОснования"):
            value = inv.get(name)
            if isinstance(value, dict) and isinstance(value.get("results"), list):
                value = value["results"]
            sections[name] = {"rows": len(value) if isinstance(value, list) else None,
                              "field_names": sorted({k for record in value for k in record})
                              if isinstance(value, list) else []}
        examples.append({"esf_number": row["Number"], "esf_ref_key": row["Ref_Key"],
                         "esf_date": row["Date"], "invoice": {k: inv.get(k) for k in INVOICE_FIELDS},
                         "invoice_sections": sections})
    return {"mode": "read_only", "scope": {"from_date": from_date, "to_date": to_date,
            "organization_key": org, "counterparty_key": cp},
            "eligible_linked_esf": eligible_count, "examples": examples,
            "note": "Examples are for analyzing server-side creation fields; do not copy IDs or dates into new documents."}


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only reference pairs ESF -> received invoice")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--organization-key", required=True)
    parser.add_argument("--counterparty-key", required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--output", required=True)
    parser.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 5:
        parser.error("--limit must be from 1 to 5")
    try:
        client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""),
                               os.getenv("ONEC_ODATA_PASSWORD", ""))
        result = inspect_examples(client, args.from_date, args.to_date,
                                  args.organization_key, args.counterparty_key, args.limit)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": args.output, "linked_esf": result["eligible_linked_esf"],
                          "examples": len(result["examples"]), "mode": "read_only"}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, ODataError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
