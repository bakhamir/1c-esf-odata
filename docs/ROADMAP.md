# Roadmap for Codex (incremental, guarded)

## Next: read-only discovery

1. Inspect modules/tests; run unit suite and report pass/fail. Do not access production unless the user authorizes that action.
2. Use `reference_inspector.py` output (one already-linked ESF) to identify required fields/relationships for received invoice and receipt. Compare field types from `$metadata` and existing document samples. Redact reports.
3. Identify whether 1C's UI operations (`Перезаполнить ссылочные реквизиты`, `Создать на основании`, `Провести и закрыть`) have equivalent published standard OData behavior. Do not guess hidden side effects.

## Then: offline planning with tests

4. Implement read-only lookup of exact reference keys for `Усл`, expense item, department, incoming document type; fail closed on duplicate/missing values.
5. Implement a deterministic, fully validated payload planner with saved fixtures for invoice/receipt and per-row missing nomenclature/units. No POST, PATCH, or document posting in this phase.
6. Add local SQLite journal (one ESF, current state, supply number, invoice date, linked refs, last successful step, error). Design idempotency/recovery around server reads.

## Only after explicit user approval

7. Preview **one** exact ESF's intended changes. Enable narrowly scoped, individually confirmed writes for one stage at a time, reading before and after. Avoid blind retries.
8. Study generated accounting documents and entries against a user-approved example. Do not mark a document finished simply because HTTP returned 2xx.
9. If end-to-end validation is proven, discuss guarded batch mode, initially tiny batches with logging/progress every five completed ESFs.

Never submit or sign IS ESF invoices, change period/org scope, use direct SQL, or modify 1C publication/permission settings as a shortcut.
