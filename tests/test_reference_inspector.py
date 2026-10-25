import json
import unittest

from reference_inspector import inspect_examples


ORG = "57495537-f978-11ee-ad65-94de80502ae1"
CP = "b711f358-7da3-11f0-8757-52540067a9c9"
INVOICE = "2af3ba81-f97b-11ee-ad65-94de80502ae1"


class FakeClient:
    def get(self, resource, params):
        if resource == "Document_ЭСФ":
            result = [{"Ref_Key": "e3ce4858-c61b-11f1-9a8a-52540009ca86",
                       "Number": "28000019906", "Date": "2026-10-05T00:00:00",
                       "Организация_Key": ORG, "Контрагент_Key": CP,
                       "СчетФактура": INVOICE,
                       "СчетФактура_Type": "StandardODATA.Document_СчетФактураПолученный"}]
        else:
            result = [{"Ref_Key": INVOICE, "Number": "SF-123", "Date": "2026-10-05T10:00:00",
                       "Организация_Key": ORG, "Posted": True,
                       "Услуги": [{"LineNumber": "1", "Номенклатура_Key": "x"}],
                       "Товары": [], "ДокументыОснования": []}]
        return json.dumps({"d": {"results": result}}, ensure_ascii=False).encode("utf-8")


class InspectorTests(unittest.TestCase):
    def test_inspect_completed_reference(self):
        result = inspect_examples(FakeClient(), "2026-09-21", "2026-10-13", ORG, CP)
        self.assertEqual(result["eligible_linked_esf"], 1)
        self.assertEqual(result["examples"][0]["invoice"]["Number"], "SF-123")
        self.assertEqual(result["examples"][0]["invoice_sections"]["Услуги"]["rows"], 1)

    def test_scope_limit(self):
        with self.assertRaises(ValueError):
            inspect_examples(FakeClient(), "2026-10-13", "2026-09-21", ORG, CP)


if __name__ == "__main__":
    unittest.main()
