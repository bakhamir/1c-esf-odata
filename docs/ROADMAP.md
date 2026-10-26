# Roadmap for Codex — checkpoint 2026-10-26

## Proven milestones

- GET client, scanner, preflight, contract lookup, dry-run intentions and opt-in single-field contract PATCH exist. Only one historical PATCH was confirmed; no new mutations authorized.
- Inspector v2 and offline initial invoice planner v2 exist. Fresh metadata and five real scoped ESF/invoice/receipt chains inspected read-only. Unit suite: 71 tests, no live tests.
- Candidate plan: five header fields and one target service row; it remains blocked. Original eight unknowns are not fully eliminated. One contract-inconsistent reference and unit-label punctuation add explicit diagnostics. See DEEP_INVOICE_RESEARCH.md and STATUS.md.

## Next safe work, no production mutation

1. Obtain accessible documentation/help or read-only source analysis of the **current configuration's** creation/refill algorithm. Metadata shows only Post/Unpost for the three documents; it does not reveal form handlers. Do not infer that POST links ESF automatically.
2. Confirm UI-to-field mappings for section F and existing unit Усл. versus required Усл. Use redacted UI evidence or configuration documentation; no new catalog item or correction merely to match spelling.
3. Extend exact-key catalog validation to the remaining accounting fields. Cost and department each have one exact lookup result; verify the actual subconto types. УчитыватьКПН is Boolean, ВидУчетаНУ_Key is GUID, ВидВходящегоДокумента is string. Do not write the UI text НУ into a Boolean.
4. Build a complete initial invoice field allowlist only for verified semantics; retain unknown Date, defaults, content, row date and link side effects as dependencies/blockers. Validate tax formulas/rounding with mixed/zero VAT and multirow synthetic cases before promoting observed mappings to rules. Preserve original decimal precision.
5. Implement equivalent receipt planning with preserved document dates, required analytics, incoming number/date/type and all untouched accounting fields. Existing final-state reciprocal references are not a valid initial payload.
6. Add shared immutable prototype guards to older entry points; independently re-read exact contract and compare protected ESF fields before/after any future approved PATCH. This gap is not fixed by the new planner's local guards.
7. Implement local SQLite stage journal and single-process lock. Persist intent before request, inspect server after uncertain outcomes, no blind POST retries. Test interruption and duplicate prevention offline.

## Requires future explicit authorization

8. If source/docs cannot establish command effects, prepare a reviewable **one-document, one-stage** experiment with exact scope, preview, recovery and before/after GET. Current permission is GET only; do not run this experiment now. Existing final-state examples cannot prove which write established links or changed registers.
9. Only after complete validated payload and user approval introduce one stage of writes at a time. Keep --commit plus exact --confirm. Verify generated IDs, relations, status and accounting results; HTTP success is insufficient.
10. Posting sequence per SPEC: receipt, received invoice, originating ESF; final verification of all links. Discuss small batches only after a proven single-document cycle and separate permission, with progress every five completed ESFs.

## Always

Only prototype supplier/org/contract and ESF dates 2026-09-21..2026-10-13. No IS ESF signing/sending, direct SQL, rights/publication/config changes. No secrets/raw accounting fixtures in Git. Small tested commits, update STATUS/DECISIONS after each milestone; standard-library-only unless alternatives are discussed.

## Proposed next experiment — not authorized

Final bounded GET found no initial unposted reference among known linked invoices. Target 28000019906 is already posted. See ONE_INVOICE_EXPERIMENT.md: user-executed native creation/save of one unposted SF with possible native link update, fresh before/after GET, no posting or receipt creation. Await explicit confirmation before the UI command. New offline observer and unit tests are ready (75 tests total); this is not a POST executor and does not eliminate creation-semantic blockers.
