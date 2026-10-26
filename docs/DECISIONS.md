# Decisions and corrections to earlier prompts

1. The **incoming supply number** is from section **F. Документы поставки → Номер**, NOT section E. Договор (контракт). Preserve leading zeros, separators and letters per ESF.
2. Both unit columns (`Ед. изм.` and `Ед. изм. остатков`) should be `Усл` when their respective value is missing; do not arbitrarily alter already correct values.
3. **Latest requirement overrides early task drafts:** create new nomenclature only when the relevant nomenclature/unit is **missing**. Reuse already correct entries; do not create duplicates. The supplier's row text need not literally be `Сервисный сбор`; examine actual records. Do not guess ambiguous catalog matches.
4. The receipt is created from the received invoice, selecting **`Услуги (акт)`**, then the final action for the completed receipt is **`Провести и закрыть`** and return to received invoice. An earlier ambiguous formulation asking which save command to use has been resolved.
5. Set **only the time** `10:00:00` on received invoice and receipt; preserve each document's date. The incoming document date comes from the **received invoice**, not today's date.
6. Contract must remain exactly `ALA-58/2025 SD`; after save check it did not reset.
7. `Учитывать КПН`: `НУ`; `Субконто БУ1`: `Расходы по перелету`; `Субконто БУ3`: `Основное подразделение`; incoming doc type: `Акт выполненных работ`.
8. One ESF is completed only after receipt, received invoice, and originating ESF have been correctly posted/closed and the originating ESF's linked-invoice field verifies as populated. Stop on errors.
9. Prototype scope is exclusively ТОО «Трансавиа» and 2026-09-21..2026-10-13. Future system should allow per-supplier configurable rules, but must not broaden current production run.
10. User moved from expensive browser-agent operation to deterministic Python OData calls to reduce token/click costs. Do not introduce an LLM into the normal batch execution path.
11. Prior technical spec and old README describe phase 1 as GET-only. That is **historical**: one tightly scoped production contract PATCH was subsequently developed and successfully performed. All other writes remain unimplemented/unapproved.

12. Inspector diagnostics v2 (2026-10-26): preserve existing invoice values for local analysis but add missing/null lists and section presence states. An absent invoice counterparty is explicitly unverified because its real schema is not established; a present mismatching value stops inspection. Do not claim schema or receipt verification. Reject continuation at collection and section levels, malformed rows, zero reference keys and ESF dates outside scope. No production requests were needed for this implementation.
13. Global continuation design is in IMPLEMENTATION_SPEC.md. Fixed scope enforcement and strengthening the existing contract executor are separate next changes; this inspector milestone does not imply those gaps are resolved or authorize any production mutation.

14. Initial invoice planner (2026-10-26) is a discovery plan, not an executable payload. It proposes only organization/counterparty/contract header mappings sourced from the target, labels them unconfirmed, and never copies final sample bases, dates, document numbers or IDs. Single-row comparisons are observations, not mapping approval. Creation semantics, ESF link side effects, initial defaults, created date, reference refill, catalog resolution, section-F field mapping and service-row mapping remain explicit blockers. No flag can override those blockers into executable mode.
