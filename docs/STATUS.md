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

## Offline repository milestone (2026-10-26)

- Verified on Python 3.12.10: 49 unit tests pass; no production requests performed.
- reference_inspector report v2 validates ESF identity/date/scope, rejects malformed/truncated/paginated collections and sections, and rejects explicit invoice counterparty mismatches. Missing invoice counterparty remains explicitly unverified, not silently confirmed.
- Reports distinguish absent invoice fields from null and absent/null/present sections; unsupported links are diagnostic anomalies. Metadata and receipts remain uninspected and explicitly flagged false.
- README rewritten for actual capabilities. docs/IMPLEMENTATION_SPEC.md defines remaining gaps, staged implementation and acceptance criteria.
- Still open: fixed prototype scope shared by all entry points, live contract revalidation before PATCH, before/after protected-field comparison, metadata mapping, receipt discovery, payload planner and recovery journal. No new write capability or authorization added.

## Read-only discovery milestone (2026-10-26)

- User configured local credentials and authorized limited GET discovery. Seven GET requests completed; no writes or posting.
- Metadata and one existing linked ESF/invoice/receipt chain inspected. Organization/counterparty matched; invoice and receipt are posted and not deleted. Invoice points to receipt in header and basis table; receipt points back to invoice. No direct origin ESF key match found within the fetched invoice values.
- ESF invoice link is Edm.String plus _Type; selected link is a GUID string. Only bound Post/Unpost operations found for ESF and received invoice; no create-on-basis operation found in metadata for these types.
- Target ESF still has the correct contract and no invoice link. No full completion claimed.
- Raw reports/ files remain ignored. Structural results and remaining semantic blockers: INVOICE_LINK_DISCOVERY.md. Creation order and server side effects remain unproven; no executable POST payload approved.

## Offline initial invoice discovery planner (2026-10-26)

- Added processor/invoice_planner.py and plan_invoice.py. No transport imports in the planner, no credentials, no production requests in this milestone.
- Resolves qualified metadata types and aliases, recursive row schemas and declared constraints; rejects missing types and unsupported inheritance. Existing entity_schema API remains unchanged.
- Validates prototype scope, deletion states, ESF period, target contract/missing link and exact reference pair. Produces candidate header mappings only, not a POST payload. Unknown semantics/defaults/dates/refill/catalog mappings remain blockers.
- Compares field presence and single-row reference values without exporting those values; multiple rows are not joined by position. Leading zeroes and whitespace in supply numbers are preserved. JSON decimals load as Decimal.
- Tested against local production snapshots: plan is blocked with eight explicit blockers; no execution supported. Raw plan remains ignored under reports/. 58 unit tests pass.
- Remaining full workflow: common scope guards for existing entry points; fresh contract validation and protected-field comparison for old PATCH; verified creation/link/refill semantics; exact catalog lookup; validated initial invoice and receipt payloads; SQLite recovery journal; individually approved writes; posting/verification; only then separately approved small batches.

## Deep read-only evidence and planner v2 (2026-10-26)

- 29 production GET requests in this stage; zero POST/PATCH/PUT/DELETE/action calls. Fresh metadata resolved all three documents, row types and seven relevant catalogs. Five scoped chains (1/5/2/1/1 rows) compared. Raw snapshots stay ignored.
- Five pairs agree on organization/counterparty/currency/document totals and calendar date; four agree on the target contract. One invoice/receipt has a different contract from its ESF: excluded from mapping evidence and never modified.
- Ten rows can be joined uniquely by values without position; only nine belong to the four contract-consistent pairs. Net + VAT equals gross; content is empty and row turnover date unset in these samples. These are observations, not proof of form algorithms/defaults. Incoming invoice number matches ESF.Number, not section-F supply number.
- Target catalog references exist and are not deleted; product is a service, base unit matches. Unit label is Усл. rather than literal Усл: confirmation remains needed. Expense/department lookups each returned one exact match; accounting mappings remain unverified.
- Added pure processor/invoice_evidence.py, synthetic fixtures and 13 tests. Planner v2 accepts repeated --pair and optional --catalogs, preserves qualified row types, rejects ambiguous joins/invalid numeric inputs, checks target catalogs, emits exact decimal-text candidates (NOT wire JSON) and new mismatch diagnostics.
- Local production-snapshot run: five header candidates, one target service-row candidate, 5 pairs / 4 consistent / 9 matched rows, blocked with original 8 plus reference_contract_mismatch and unit_label_requires_confirmation. No original blocker is fully resolved; structural uncertainty narrowed but hidden command effects remain unknown.
- 71 unit tests pass. Details and blocker-by-blocker GET strategy: DEEP_INVOICE_RESEARCH.md. No new write transport or command-equivalence claim.

## Final GET boundary and native-creation observation preparation (2026-10-26)

- Five additional GET only. Target 28000019906 is already posted, contract/scope correct, no invoice link, one item row. No active/inactive invoice with matching incoming number was found in scoped organization/counterparty; this does not exclude differently numbered duplicates.
- Exact unit alternatives: zero Усл, one Усл. with full label Одна услуга, matching target references. No new unit or normalization performed. No unposted invoice among the 27 known linked references; no initial-state sample available from this bounded search.
- Fresh metadata still exposes only Post/Unpost for ESF/invoice. Public platform Filling documentation does not reveal current application-specific handlers; current configuration source unavailable through published schema. No claim that all conceivable GET research is exhausted.
- Added offline snapshot observer and four synthetic tests: selected-field diff, existing source Posted state, unposted created invoice, exact scope/link and stop-on-change diagnostics. No write or native UI command executed. 75 unit tests pass.
- ONE_INVOICE_EXPERIMENT.md describes a proposed user-executed native creation/save of one unposted invoice, possible native ESF link update, before/after GET and no blind retry/automatic rollback. Separate confirmation required; no executable OData POST/PATCH preview approved.

## User-created initial invoice verified by GET

- User reported completing the native creation/save for ESF 28000019906. Two exact GET requests verify its new received-invoice link and the linked invoice. No agent write.
- Snapshot observer reports observed_linked_unposted_invoice, no issues. Selected ESF fields changed only DataVersion and invoice link/type; previous Posted=true, contract, date, rows and totals preserved.
- Created SF is unposted/not deleted, correct org/supplier/contract, time 10:00:00, one service, no goods/bases, shipping confirmation false. Net/VAT/gross, product, quantity, price, currency and total match expected values; content empty and service turnover date unset. Incoming number equals ESF.Number.
- Initial unposted reference now exists. Do not create another invoice for this ESF. OData create/link side-effect equivalence remains unproven. Raw before/after/invoice/observation files remain ignored in reports/.

## Existing-invoice continuation and receipt planner (2026-10-26)

- 8 GET only: current scoped ESF/invoice, exact-backlink receipt search, two known reference receipts, exact tax-kind/cost/department lookups. Source SF remains unposted; no direct-backlink receipt candidate. Zero matches does not exclude other link representations.
- Added processor/receipt_planner.py and plan_receipt.py, synthetic fixtures and 11 tests. Validates linked SF against originating ESF, avoids repeated SF creation, rejects existing bases/receipt matches, checks schema/lookup types and Decimal values, prepares 12 header candidates and 1 target service row.
- Incoming receipt date uses existing SF calendar date, supply string preserved exactly; receipt own date remains unknown with time 10:00:00 dependency. Required tax/cost/department values use validated existing catalogs; historical account defaults never copied.
- Two reference receipts verify CPT Boolean + separate NU GUID and services enum/subconto types. Both incoming dates differ from SPEC; one expense differs. Deviations recorded, historical records untouched.
- Local snapshot run: blocked with 7 receipt-stage reasons; no executable payload/transport. Current SF date/initial state are known for continuation, not generalized into universal defaults for future SF POST.
- 86 unit tests pass; docs/RECEIPT_CONTINUATION.md contains results and proposed single native unposted-receipt experiment, awaiting separate confirmation. No new writes authorized or performed.
