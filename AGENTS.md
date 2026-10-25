# Codex instructions — 1C ESF OData

Read `docs/SPEC.md`, `docs/STATUS.md` and `docs/ROADMAP.md` before coding. These are the persistent handoff from the original ChatGPT discussion. Inspect the implementation and tests: documentation is not proof a feature is implemented.

## Mission and scope

Automate completion of missing linked documents for incoming electronic invoices (`ЭСФ`) in 1C:Fresh, `Бухгалтерия для Казахстана` 3.0, using standard OData. Current prototype only: ТОО «Трансавиа», ESF document dates inclusive 2026-09-21 through 2026-10-13, one specified organization and one specified contract. All other entities/periods are out of scope. Never sign or send documents to IS ESF.

## Production-data safety — mandatory

- **The 1C service is PRODUCTION; no test base exists.** Default to offline tests, fixtures and read-only GET. Never run production writes, posting, mass processing, rights/config changes, or migrations without the user's explicit authorization for the concrete operation and scope. Authorization for one PATCH does **not** authorize new POST/PATCH or batch commits.
- In existing executor, `--commit` and an exact `--confirm` phrase are required for one contract PATCH. Keep or strengthen this gate. Do not circumvent it for convenience.
- Before any authorized write: independently re-read the exact target, validate organization, counterparty, period, missing link, contract, and expected data. Afterward re-read and compare. If the response is ambiguous/timeouts, **never blindly retry POST** or repeat creation; inspect for side effects first.
- One ESF at a time; no concurrency or cross-record reuse of supply number/date. Keep exact string values, leading zeroes, date and time; only change specified fields. Fail closed on ambiguity.
- Do not assume standard OData PATCH is equivalent to 1C UI's `Создать на основании`, `Перезаполнить ссылочные реквизиты`, or `Провести и закрыть`; study actual effects before implementation.
- Never print, commit, ask to paste, or exfiltrate passwords, session cookies, tokens, accounting payloads or personally identifiable data. Use `ONEC_ODATA_USERNAME` / `ONEC_ODATA_PASSWORD` from environment. `.gitignore` excludes raw JSON/CSV reports by default.

## Development practices

- Python 3.12+; currently standard-library-only, `unittest`. Prefer extending established modules rather than introducing dependencies before discussing tradeoffs.
- Run `python -m unittest discover -s tests -q` after changes. Keep external calls mocked in tests. Commands for production MUST be preview-only by default.
- Keep changes narrow and reviewable. Document implementation decisions in `docs/DECISIONS.md` and update `docs/STATUS.md` after a proven milestone.
- Do not modify user accounting data, Git remotes, GitHub permissions or repository visibility without explicit approval.

## First task for the migrated Codex session

Orient to repository and verify tests. Review `reference_inspector.py` and request/read the **redacted** output of its existing-linked-invoice GET inspection, if not provided. Identify invoice/receipt fields and gaps needed for a **read-only schema comparison and offline POST payload planner**. Do not execute any new production writes.
