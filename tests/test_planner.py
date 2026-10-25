import copy
import json
import tempfile
import unittest
from pathlib import Path

from main import plan_batch, run
from esf_preflight import HEADER_FIELDS
from processor.planner import NOMENCLATURE_TYPE, ZERO_GUID, plan_one


ORG = "57495537-f978-11ee-ad65-94de80502ae1"
ESF = "85a4b616-ceb5-11f1-9f6c-52540009ca86"
CONTRACT = "01ce0e08-09a5-11f1-9689-52540067a9c9"
PRODUCT = "659f9990-bef2-11f0-869d-52540067a9c9"
UNIT = "b93262f6-fd87-11ee-8871-94de80502ae1"
COUNTERPARTY = "b711f358-7da3-11f0-8757-52540067a9c9"


def fixtures():
    preflight = {
        "mode": "read_only", "missing_header_fields": [], "item_count": 1,
        "header": {"Ref_Key": ESF, "Number": "28000021582", "Date": "2026-10-23T00:00:00",
                   "Организация_Key": ORG, "Контрагент_Key": COUNTERPARTY, "СчетФактура": "",
                   "СчетФактура_Type": "StandardODATA.Undefined",
                   "ДоговорПоставки_Key": ZERO_GUID,
                   "ДокументПодтверждающийПоставкуНомер": "AAK01034759",
                   "ДокументПодтверждающийПоставкуАВРНомер": ""},
        "items": [{"line": 1, "fields": {"Товар": PRODUCT, "Товар_Type": NOMENCLATURE_TYPE,
                  "ЕдиницаИзмерения_Key": UNIT, "ЕдиницаИзмеренияХраненияОстатков_Key": UNIT}}],
    }
    lookup = {"mode": "read_only", "status": "unique", "contract_number": "ALA-58/2025 SD",
              "organization_key": ORG,
              "candidates": [{"Ref_Key": CONTRACT, "Организация_Key": ORG,
                              "Description": "ALA-58/2025 SD", "НомерДоговора": "", "Owner_Key": COUNTERPARTY}]}
    return preflight, lookup


class PlannerTests(unittest.TestCase):
    def test_realistic_esf_skips_existing_product_and_units(self):
        preflight, lookup = fixtures()
        result = plan_one(preflight, lookup)
        self.assertEqual(result["status"], "ready_for_review")
        steps = result["actions"]
        self.assertTrue(any(a["action"] == "set_contract" and a["value"] == CONTRACT for a in steps))
        self.assertEqual(len([a for a in steps if a["action"] == "keep_unit"]), 2)
        self.assertTrue(any(a["action"] == "keep_nomenclature" for a in steps))
        self.assertFalse(any(a["action"] == "propose_create_service_nomenclature" for a in steps))
        self.assertFalse(result["execution_supported"])

    def test_missing_product_and_units_are_proposed_only(self):
        preflight, lookup = fixtures()
        line = preflight["items"][0]["fields"]
        line.update({"Товар": "", "Товар_Type": "StandardODATA.Undefined",
                     "ЕдиницаИзмерения_Key": ZERO_GUID,
                     "ЕдиницаИзмеренияХраненияОстатков_Key": ZERO_GUID})
        actions = plan_one(preflight, lookup)["actions"]
        self.assertEqual(len([a for a in actions if a["action"] == "propose_set_unit"]), 2)
        self.assertEqual(len([a for a in actions if a["action"] == "propose_create_service_nomenclature"]), 1)

    def test_ambiguous_contract_blocks(self):
        preflight, lookup = fixtures()
        lookup["status"] = "ambiguous"
        lookup["candidates"].append(copy.deepcopy(lookup["candidates"][0]))
        result = plan_one(preflight, lookup)
        self.assertEqual(result["status"], "blocked")

    def test_contract_owner_mismatch_blocks(self):
        preflight, lookup = fixtures()
        preflight["header"]["Контрагент_Key"] = "b711f358-7da3-11f0-8757-52540067a9c9"
        lookup["candidates"][0]["Owner_Key"] = "a711f358-7da3-11f0-8757-52540067a9c9"
        result = plan_one(preflight, lookup)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("owner" in msg for msg in result["blockers"]))

    def test_already_linked_is_skipped(self):
        preflight, lookup = fixtures()
        preflight["header"]["СчетФактура"] = PRODUCT
        preflight["header"]["СчетФактура_Type"] = "StandardODATA.Document_СчетФактураПолученный"
        self.assertEqual(plan_one(preflight, lookup)["status"], "skip_already_linked")

    def test_missing_row_fields_block_instead_of_creating(self):
        preflight, lookup = fixtures()
        del preflight["items"][0]["fields"]["Товар"]
        result = plan_one(preflight, lookup)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(any(a["action"] == "propose_create_service_nomenclature" for a in result["actions"]))

    def test_offline_cli_writes_utf8_report(self):
        preflight, lookup = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / "preflight.json").write_text(json.dumps(preflight, ensure_ascii=False), encoding="utf-8")
            (p / "contracts.json").write_text(json.dumps(lookup, ensure_ascii=False), encoding="utf-8")
            rc = run(["plan-one", "--preflight", str(p / "preflight.json"),
                      "--contracts", str(p / "contracts.json"), "--output", str(p / "out.json")])
            self.assertEqual(rc, 0)
            data = json.loads((p / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(data["summary"], {"ready_for_review": 1})

    def test_batch_requires_organization_scope(self):
        _, lookup = fixtures()
        pending = {"mode": "read_only", "entity": "Document_ЭСФ",
                   "scope": {"organization_key": None}, "pending": [{"ref_key": ESF, "number": "28000021582"}]}
        with self.assertRaises(ValueError):
            plan_batch(pending, lookup, None, 1)

    def test_live_read_only_batch_plans_one(self):
        preflight_data, lookup = fixtures()
        document = {**{name: "" for name in HEADER_FIELDS}, **preflight_data["header"],
                    "Товары": [preflight_data["items"][0]["fields"]]}

        class FakeClient:
            def get(self, entity, params):
                self.params = params
                return json.dumps({"d": {"results": [document]}}, ensure_ascii=False).encode("utf-8")

        pending = {"mode": "read_only", "entity": "Document_ЭСФ",
                   "scope": {"organization_key": ORG, "counterparty_key": COUNTERPARTY,
                             "from_date": "2026-10-01", "to_date": "2026-10-31"},
                   "pending": [{"ref_key": ESF, "number": "28000021582"}]}
        client = FakeClient()
        result = plan_batch(pending, lookup, client, 1)
        self.assertEqual(result["summary"], {"ready_for_review": 1})
        self.assertIn("Ref_Key eq guid'", client.params["$filter"])

    def test_batch_refuses_unexpected_period(self):
        _, lookup = fixtures()
        pending = {"mode": "read_only", "entity": "Document_ЭСФ",
                   "scope": {"organization_key": ORG, "counterparty_key": COUNTERPARTY,
                             "from_date": "2026-10-01", "to_date": "2026-10-31"},
                   "pending": [{"ref_key": ESF, "number": "28000021582"}]}
        with self.assertRaisesRegex(ValueError, "date range"):
            plan_batch(pending, lookup, None, 1, "2026-09-21", "2026-10-13")


if __name__ == "__main__":
    unittest.main()
