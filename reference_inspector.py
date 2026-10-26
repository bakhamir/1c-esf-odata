"""Read-only inspection of already linked ESF -> received invoice examples."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import uuid
from pathlib import Path

from odata_client import DEFAULT_APPLICATION_URL, ODataError, ReadOnlyOData


ESF = "Document_ЭСФ"
INVOICE = "Document_СчетФактураПолученный"
INVOICE_FIELDS = ("Ref_Key", "Number", "Date", "Posted", "ДокументОснование",
                  "ДокументОснование_Type", "ПодтвержденДокументамиОтгрузки",
                  "ДоговорКонтрагента_Key", "Организация_Key", "НомерВходящегоДокумента",
                  "ДатаВходящегоДокумента", "Контрагент_Key")


def checked_rows(payload: bytes, maximum: int, label: str) -> list[dict]:
    """Reject partial or malformed collections rather than report a false sample."""
    envelope = json.loads(payload)
    wrapped = envelope.get("d", envelope) if isinstance(envelope, dict) else None
    if not isinstance(wrapped, dict):
        raise ODataError(f"{label}: malformed collection")
    if any(container.get(key) for container in (envelope, wrapped)
           for key in ("__next", "@odata.nextLink", "odata.nextLink")):
        raise ODataError(f"{label}: paginated response; narrow the scope")
    rows = wrapped.get("results", wrapped.get("value"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ODataError(f"{label}: malformed collection rows")
    if len(rows) >= maximum:
        raise ODataError(f"{label}: response may be truncated; narrow the scope")
    return rows


def nonzero_guid(value) -> str:
    try:
        parsed = uuid.UUID(str(value))
        if parsed.int:
            return str(parsed)
    except (ValueError, TypeError, AttributeError):
        pass
    raise ODataError("Invalid or zero reference key")


def inspect_examples(client: ReadOnlyOData, from_date: str, to_date: str,
                     organization_key: str, counterparty_key: str, limit: int = 1) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("limit must be from 1 to 5")
    first, last = dt.date.fromisoformat(from_date), dt.date.fromisoformat(to_date)
    if first > last or (last - first).days > 366:
        raise ValueError("Invalid date scope")
    org, cp = nonzero_guid(organization_key), nonzero_guid(counterparty_key)
    end = (last + dt.timedelta(days=1)).isoformat()
    params = {"$format": "json", "$top": 200,
              "$select": "Ref_Key,Number,Date,Организация_Key,Контрагент_Key,СчетФактура,СчетФактура_Type",
              "$filter": " and ".join((f"Date ge datetime'{first}T00:00:00'",
                                      f"Date lt datetime'{end}T00:00:00'",
                                      f"Организация_Key eq guid'{org}'",
                                      f"Контрагент_Key eq guid'{cp}'", "DeletionMark eq false"))}
    payload = client.get(ESF, params)
    rows = checked_rows(payload, 200, "ESF")
    examples = []
    eligible_count = 0
    anomalies = []
    for row_index, row in enumerate(rows, start=1):
        required = ("Ref_Key", "Number", "Date", "Организация_Key", "Контрагент_Key",
                    "СчетФактура", "СчетФактура_Type")
        if any(name not in row for name in required):
            raise ODataError("ESF missing required fields")
        nonzero_guid(row["Ref_Key"])
        if not isinstance(row["Number"], str) or not row["Number"]:
            raise ODataError("ESF number must be a nonempty string")
        try:
            stamp = dt.datetime.fromisoformat(row["Date"])
        except (ValueError, TypeError):
            raise ODataError("Invalid ESF date") from None
        if stamp.tzinfo is not None or not first <= stamp.date() <= last:
            raise ODataError("ESF date outside scope or timezone ambiguous")
        if str(row.get("Организация_Key", "")).lower() != org or str(row.get("Контрагент_Key", "")).lower() != cp:
            raise ODataError("Server returned ESF outside scope")
        reference = row.get("СчетФактура")
        if not reference or row.get("СчетФактура_Type") != "StandardODATA.Document_СчетФактураПолученный":
            if reference not in (None, "") or row["СчетФактура_Type"] != "StandardODATA.Undefined":
                anomalies.append({"row_index": row_index,
                                  "code": "unsupported_or_inconsistent_invoice_link"})
            continue
        eligible_count += 1
        if len(examples) >= limit:
            continue
        try:
            invoice_key = nonzero_guid(reference)
        except ODataError:
            examples.append({"esf_number": row.get("Number"), "unresolved_link": reference,
                             "warning": "Linked invoice is not a direct GUID; manual mapping required"})
            continue
        invoices = checked_rows(client.get(INVOICE, {"$format": "json", "$top": 2,
                                    "$filter": f"Ref_Key eq guid'{invoice_key}'"}), 2, "Received invoice")
        if len(invoices) != 1:
            examples.append({"esf_number": row.get("Number"), "invoice_ref_key": invoice_key,
                             "warning": f"Expected one received invoice; found {len(invoices)}"})
            continue
        inv = invoices[0]
        if str(inv.get("Ref_Key", "")).lower() != invoice_key or str(inv.get("Организация_Key", "")).lower() != org:
            raise ODataError("Received invoice reference or organization mismatch")
        if "Контрагент_Key" in inv and str(inv["Контрагент_Key"]).lower() != cp:
            raise ODataError("Received invoice counterparty mismatch")
        sections = {}
        for name in ("Товары", "Услуги", "ДокументыОснования"):
            value = inv.get(name)
            if isinstance(value, dict) and isinstance(value.get("results"), list):
                value = value["results"]
            state = "missing" if name not in inv else "null" if value is None else "present"
            if state == "present" and (not isinstance(value, list) or
                                       any(not isinstance(record, dict) for record in value)):
                raise ODataError("Malformed invoice section")
            if isinstance(inv.get(name), dict) and any(inv[name].get(key) for key in
                    ("__next", "@odata.nextLink", "odata.nextLink")):
                raise ODataError("Paginated invoice section")
            sections[name] = {"state": state, "rows": len(value) if isinstance(value, list) else None,
                              "field_names": sorted({k for record in value for k in record})
                              if isinstance(value, list) else []}
        examples.append({"esf_number": row["Number"], "esf_ref_key": row["Ref_Key"],
                         "esf_date": row["Date"], "invoice": {k: inv.get(k) for k in INVOICE_FIELDS},
                         "invoice_sections": sections,
                         "missing_invoice_fields": [k for k in INVOICE_FIELDS if k not in inv],
                         "null_invoice_fields": [k for k in INVOICE_FIELDS if k in inv and inv[k] is None],
                         "counterparty_verified": "Контрагент_Key" in inv})
    return {"mode": "read_only", "scope": {"from_date": from_date, "to_date": to_date,
            "organization_key": org, "counterparty_key": cp},
            "report_version": 2, "anomalies": anomalies,
            "schema_verified": False, "receipt_inspected": False,
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
