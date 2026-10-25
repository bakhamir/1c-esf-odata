# Current status / handoff checkpoint (2026-10-26)

## Confirmed by the user in the original ChatGPT conversation

- Standard OData access works at `https://1cfresh.kz/a/ea38/116539/odata/standard.odata/` with configured credentials (do not store them). `$metadata` was accessible; reported 732 entity sets.
- Real OData entity names include `Document_ЭСФ`, `Document_СчетФактураПолученный`, `Document_ПоступлениеТоваровУслуг`, and `Catalog_ДоговорыКонтрагентов`. Do not infer names from the UI; inspect actual `$metadata`.
- Client, scanner, preflight, contract lookup, dry-run plan, and `execute_contract.py` have been developed; user verified that the scoped Transavia count matched the 1C interface. Earlier reports showed **49** ESFs in scope and **22** without linked invoices (historical snapshot: recount live before any action).
- First and **only user-confirmed live write**: ESF `28000019906`, Ref_Key `e3ce4858-c61b-11f1-9a8a-52540009ca86`: PATCH of **only** `ДоговорПоставки_Key` to `01ce0e08-09a5-11f1-9689-52540067a9c9` succeeded. The user visually verified the correct contract in 1C. This ESF must NOT be treated as fully processed: the linked invoice/receipt workflow is still unimplemented.
- `reference_inspector.py` was the latest addition. It uses GET to study an ESF that already has a linked received invoice. No inspector output has been provided/verified yet in this handoff.
- Prior run reportedly passed **37** `unittest` tests. Run anew before further work; do not assume current CI is green.

## Explicitly NOT yet done

- No verified API implementation of 1C reference autofill, conditional nomenclature creation, units in both columns, received invoice creation, receipt creation, accounting analytics, posting/closing, end-to-end verification or resumable batch journal.
- No blanket authorization to use write mode. The single authorized contract PATCH does not count as authorization for additional mutations.
- No test database; user operates on production.

## Verified identifiers for *current prototype only*

| Item | Value |
| --- | --- |
| Supplier | ТОО «Трансавиа» |
| Counterparty Ref_Key | `b711f358-7da3-11f0-8757-52540067a9c9` |
| Organization Ref_Key | `57495537-f978-11ee-ad65-94de80502ae1` |
| Inclusive ESF dates | `2026-09-21` to `2026-10-13` |
| Supply contract | `ALA-58/2025 SD` |
| Contract Ref_Key | `01ce0e08-09a5-11f1-9689-52540067a9c9` |

These identifiers are scope guards, **not** a justification to auto-write. Confirm every candidate against live data.

## Useful existing commands

```powershell
python -m unittest discover -s tests -q
python odata_client.py entities --match "СчетФактура"
python odata_client.py schema --entity "Document_ЭСФ"
python reference_inspector.py --from-date 2026-09-21 --to-date 2026-10-13 --organization-key "57495537-f978-11ee-ad65-94de80502ae1" --counterparty-key "b711f358-7da3-11f0-8757-52540067a9c9" --limit 1 --output "reference_invoice.json"
```

Last command reads production data (GET) but does not write. Keep `reference_invoice.json` untracked and redact before sharing.
