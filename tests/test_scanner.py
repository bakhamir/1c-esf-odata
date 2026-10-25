import json
import unittest

from esf_scanner import date_range, scan
from odata_client import ODataError


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get(self, entity, params):
        self.calls.append((entity, params))
        start = params["$skip"]
        end = start + params["$top"]
        return json.dumps({"d": {"results": self.rows[start:end]}}, ensure_ascii=False).encode("utf-8")


def row(number, link="", kind="StandardODATA.Undefined"):
    return {"Ref_Key": "guid-" + number, "Number": number,
            "Date": "2026-10-01T00:00:00", "СчетФактура": link,
            "СчетФактура_Type": kind}


class ScannerTests(unittest.TestCase):
    def test_date_range_exclusive_end(self):
        self.assertEqual(date_range("2026-10-01", "2026-10-31"), ("2026-10-01", "2026-11-01"))

    def test_requires_bounded_scope(self):
        with self.assertRaises(ValueError):
            date_range("2022-01-01", "2026-10-31")

    def test_pending_and_anomaly_classification_with_pagination(self):
        client = FakeClient([row("1"), row("2", "invoice-ref", "StandardODATA.Document_СчетФактураПолученный"),
                             row("3", "", "OtherType")])
        report = scan(client, "2026-10-01", "2026-10-31", page_size=2)
        self.assertEqual(report["examined"], 3)
        self.assertEqual([item["number"] for item in report["pending"]], ["1"])
        self.assertEqual(len(report["anomalies"]), 1)
        self.assertIn("Date lt datetime'2026-11-01T00:00:00'", client.calls[0][1]["$filter"])
        self.assertEqual(client.calls[1][1]["$skip"], 2)

    def test_fails_on_missing_required_fields(self):
        client = FakeClient([{"Number": "1"}])
        with self.assertRaises(ODataError):
            scan(client, "2026-10-01", "2026-10-31")

    def test_explicit_counterparty_scope_is_added_to_odata_filter(self):
        counterparty = "b711f358-7da3-11f0-8757-52540067a9c9"
        client = FakeClient([{**row("1"), "Контрагент_Key": counterparty}])
        result = scan(client, "2026-09-21", "2026-10-13", counterparty_key=counterparty)
        self.assertEqual(result["pending_count"], 1)
        self.assertEqual(result["scope"]["counterparty_key"], counterparty)
        self.assertIn(f"Контрагент_Key eq guid'{counterparty}'", client.calls[0][1]["$filter"])


if __name__ == "__main__":
    unittest.main()
