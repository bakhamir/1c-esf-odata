# Working specification: 1C:Fresh incoming ESF completion

**Canonical current requirements for the prototype.** Historical UI workflow is retained below as acceptance criteria; **equivalent OData operations are not automatically known**. See `AGENTS.md` for safety, `STATUS.md` for implementation progress and `DECISIONS.md` for corrected decisions.

## Selection

- Only ТОО «Трансавиа», organization/counterparty keys and dates from `STATUS.md`.
- Select `Document_ЭСФ` records with missing `СчетФактура`; in examined data an empty string and `СчетФактура_Type = StandardODATA.Undefined` identified candidates. Recheck live before writing.
- Process one at a time; skip already-linked documents; never change organization, period or unmentioned fields.

## Per-document target behavior

1. Read and persist ESF `Ref_Key`, number, date, supplier and organization.
2. Ensure supply contract points to exact `ALA-58/2025 SD` (`ДоговорПоставки_Key`); do nothing if already correct.
3. From **F. Документы поставки → Номер**, extract exact `SUPPLY_NUMBER` as a string. Missing/multiple ambiguous numbers are blockers. **Not** the contract number from section E.
4. Reproduce `G. Товары → Автозаполнение → Перезаполнить ссылочные реквизиты` faithfully; this 1C UI command is not known to equal a simple OData PATCH.
5. For any service row lacking required nomenclature/unit, use existing appropriate catalog entries where available; create separate service nomenclature only if absent, with unit `Усл`, changing no other defaulted fields. Fill missing values in both ESF unit columns (`Ед. изм.` and `Ед. изм. остатков`), verifying their exact OData properties. Avoid duplicates.
6. Recheck contract and persist originating ESF.
7. `Отражение в учёте → Создать счёт-фактуру → OK`: create linked **received invoice**, store its created date `INVOICE_DATE`, change only its time to `10:00:00`, save.
8. From received invoice `Создать на основании → Поступление ТМЗ и услуг → Услуги (акт) → Выбрать`: create linked **receipt of services**. Set only time to `10:00:00` (preserve receipt's own date).
9. On service row set `Учитывать КПН = НУ`, `Субконто БУ1 = Расходы по перелету`, `Субконто БУ3 = Основное подразделение`. Leave other accounting parameters intact.
10. `Дополнительно`: `Вх. документ = Акт выполненных работ`, `Вх. номер = SUPPLY_NUMBER`, `Вх. дата = INVOICE_DATE`; confirm.
11. **Post and close receipt**, return to received invoice without losing relations. Check/enable `Подтверждён документами отгрузки`. **Post and close invoice**. Return to originating ESF and **post and close ESF**.
12. Refresh/read ESF, assert linked invoice now exists, confirm receipt/invoice identities and successful statuses. Only then mark completed; log all generated keys, numbers, dates, last step and any errors. Every 5 completed documents give progress.

## Non-goals and failure handling

- No EDS signing, no IS ESF submission, no arbitrary reclassification/cleanup of other documents.
- Stop on unknown catalog choice, empty or ambiguous supply number, failed posting, unexpected dialog/response, uncertain server state, or API mismatch.
- On resume, first read persisted server state and journal; **never blindly recreate** a potentially existing invoice, receipt or nomenclature.
- No automatic mass write. Every new production write capability needs a separate user approval before first use.
