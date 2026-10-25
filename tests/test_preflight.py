import json
import unittest

from esf_preflight import preflight
from odata_client import ODataError


KEY = "e5e6b4b8-c61b-11f1-9a8a-52540009ca86"


class FakeClient:
    def __init__(self, obj):
        self.obj = obj
        self.calls = []

    def get(self, entity, params):
        self.calls.append((entity, params))
        return json.dumps({"d": {"results": [self.obj]}}, ensure_ascii=False).encode("utf-8")


class PreflightTests(unittest.TestCase):
    def test_single_esf_with_item_details(self):
        obj = {"Ref_Key": KEY, "Number": "000001", "СчетФактура": "",
               "СчетФактура_Type": "StandardODATA.Undefined",
               "Товары": [{"НаименованиеТовара": "Сервисный сбор", "ЕдиницаИзмерения": ""}]}
        client = FakeClient(obj)
        report = preflight(client, KEY, "000001")
        self.assertTrue(report["is_candidate"])
        self.assertEqual(report["item_count"], 1)
        self.assertEqual(report["items"][0]["fields"]["НаименованиеТовара"], "Сервисный сбор")
        self.assertIn("Ref_Key eq guid'", client.calls[0][1]["$filter"])

    def test_mismatch_number_rejected(self):
        client = FakeClient({"Ref_Key": KEY, "Number": "different", "Товары": []})
        with self.assertRaises(ODataError):
            preflight(client, KEY, "expected")

    def test_missing_goods_rejected(self):
        client = FakeClient({"Ref_Key": KEY, "Number": "1"})
        with self.assertRaises(ODataError):
            preflight(client, KEY)


if __name__ == "__main__":
    unittest.main()
