"""Pure, deterministic ESF dry-run planner. NO HTTP writes or 1C mutations."""

from __future__ import annotations

import uuid
from typing import Any

from config import BusinessRules


ZERO_GUID = "00000000-0000-0000-0000-000000000000"
NOMENCLATURE_TYPE = "StandardODATA.Catalog_Номенклатура"


def valid_guid(value: Any) -> bool:
    try:
        return bool(value) and uuid.UUID(str(value)).int != 0
    except (ValueError, AttributeError, TypeError):
        return False


def action(kind: str, **details: Any) -> dict:
    return {"action": kind, **details}


def plan_one(preflight: dict, lookup: dict, rules: BusinessRules | None = None) -> dict:
    """Plan safe decisions; unknown situations become blockers, never guesses."""
    rules = rules or BusinessRules()
    header = preflight.get("header") or {}
    items = preflight.get("items") or []
    number = header.get("Number")
    ref_key = header.get("Ref_Key")
    organization = header.get("Организация_Key")
    steps: list[dict] = []
    blockers: list[str] = []

    if preflight.get("mode") != "read_only":
        blockers.append("Unexpected preflight provenance")
    if not valid_guid(ref_key) or not valid_guid(organization) or not number or not header.get("Date"):
        blockers.append("Missing ESF identity, organization or date")
    if preflight.get("missing_header_fields"):
        blockers.append("Preflight omitted expected header fields")

    # A linked document means the ESF must not be processed again.
    linked = header.get("СчетФактура")
    linked_type = header.get("СчетФактура_Type")
    if linked not in ("", None) or linked_type != "StandardODATA.Undefined":
        return {
            "mode": "dry_run", "esf_number": number, "esf_ref_key": ref_key,
            "organization_key": organization, "status": "skip_already_linked",
            "actions": [action("skip_esf", reason="Invoice link is already present or inconsistent")],
            "blockers": [], "execution_supported": False,
        }

    candidates = lookup.get("candidates") or []
    if lookup.get("mode") != "read_only" or lookup.get("status") != "unique" or len(candidates) != 1:
        blockers.append("Contract lookup is not unique")
        contract = {}
    else:
        contract = candidates[0]
        if lookup.get("contract_number") != rules.contract_label or lookup.get("organization_key") != organization:
            blockers.append("Contract lookup scope differs from ESF")
        if contract.get("Организация_Key") != organization:
            blockers.append("Contract belongs to another organization")
        if (contract.get("Description") != rules.contract_label and
                contract.get("НомерДоговора") != rules.contract_label):
            blockers.append("Contract name/number is not an exact match")
        if not valid_guid(contract.get("Ref_Key")):
            blockers.append("Resolved contract has no valid Ref_Key")
        counterparty = header.get("Контрагент_Key")
        owner = contract.get("Owner_Key")
        if valid_guid(counterparty) and valid_guid(owner) and str(counterparty).lower() != str(owner).lower():
            blockers.append("Contract owner differs from ESF counterparty")

    existing = header.get("ДоговорПоставки_Key")
    desired = contract.get("Ref_Key")
    if valid_guid(existing):
        if desired and str(existing).lower() == str(desired).lower():
            steps.append(action("keep_contract", ref_key=existing))
        else:
            blockers.append("An existing different contract is linked; manual review required")
    elif existing in (ZERO_GUID, "", None) and desired:
        steps.append(action("set_contract", field="ДоговорПоставки_Key", value=desired))
    elif existing not in (ZERO_GUID, "", None):
        blockers.append("Unrecognized contract reference")

    # The F tab's number may correspond to different 1C fields; accept only
    # the one unambiguous nonempty option, and require later UI confirmation.
    supply = header.get("ДокументПодтверждающийПоставкуНомер")
    supply_avr = header.get("ДокументПодтверждающийПоставкуАВРНомер")
    if bool(supply) == bool(supply_avr):
        blockers.append("Supply number missing or ambiguous between two fields")
        chosen_supply = None
    else:
        chosen_supply = supply or supply_avr
        steps.append(action("capture_supply_number", source_field=(
            "ДокументПодтверждающийПоставкуНомер" if supply else
            "ДокументПодтверждающийПоставкуАВРНомер"), value=chosen_supply,
            confirmation="compare with F. Документы поставки / Номер"))

    if not items or preflight.get("item_count") != len(items):
        blockers.append("Item table missing or inconsistent")

    for index, item in enumerate(items, start=1):
        fields = item.get("fields") or {}
        line = item.get("line", index)
        required_row_fields = ("Товар", "Товар_Type", "ЕдиницаИзмерения_Key",
                               "ЕдиницаИзмеренияХраненияОстатков_Key")
        if any(field not in fields for field in required_row_fields):
            blockers.append(f"Line {line}: missing fields in preflight; refresh with current preflight version")
            continue
        linked_product = fields.get("Товар")
        product_type = fields.get("Товар_Type")
        if valid_guid(linked_product) and product_type == NOMENCLATURE_TYPE:
            steps.append(action("keep_nomenclature", line=line, ref_key=linked_product))
        elif linked_product in (None, "", ZERO_GUID) and product_type in (None, "", "StandardODATA.Undefined"):
            steps.append(action("propose_create_service_nomenclature", line=line,
                                unit_label=rules.unit_label, requires_lookup=True))
        else:
            blockers.append(f"Line {line}: unknown product reference or type")

        for field in ("ЕдиницаИзмерения_Key", "ЕдиницаИзмеренияХраненияОстатков_Key"):
            current = fields.get(field)
            if valid_guid(current):
                steps.append(action("keep_unit", line=line, field=field, ref_key=current))
            elif current in (None, "", ZERO_GUID):
                steps.append(action("propose_set_unit", line=line, field=field,
                                    unit_label=rules.unit_label, requires_lookup=True))
            else:
                blockers.append(f"Line {line}: unrecognized unit reference in {field}")

    steps.append(action("prepare_refresh_reference_fields", needs_server_semantics=True))
    steps.append(action("prepare_received_invoice", date_policy="preserve_created_document_date",
                        time=rules.target_time))
    steps.append(action("prepare_receipt", form="Услуги (акт)",
                        date_policy="preserve_created_document_date", time=rules.target_time,
                        tax_accounting=rules.tax_accounting,
                        subconto_bu1=rules.cost_subconto_bu1, subconto_bu3=rules.cost_subconto_bu3,
                        incoming_type=rules.incoming_document_type, incoming_number=chosen_supply,
                        incoming_date_policy="date_of_created_received_invoice"))
    steps.append(action("prepare_confirm_shipping_documents", value=True))
    steps.append(action("prepare_post_sequence", order=["receipt", "received_invoice", "esf"],
                        needs_server_semantics=True))
    steps.append(action("verify_esf_invoice_link_after_post"))

    return {"mode": "dry_run", "esf_number": number, "esf_ref_key": ref_key,
            "organization_key": organization,
            "status": "blocked" if blockers else "ready_for_review",
            "actions": steps, "blockers": blockers, "execution_supported": False,
            "rules": rules.to_dict(),
            "limitations": ["No API writes are implemented",
                            "1C create-on-basis/refill/post semantics are unverified",
                            "Dates of newly created documents must be read at execution time"],
            }
