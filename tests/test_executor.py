import json
import unittest
from unittest.mock import patch

from execute_contract import prepare, run
from odata_client import ReadOnlyOData
from processor.executor import patch_contract


ORG = "57495537-f978-11ee-ad65-94de80502ae1"
OWNER = "b711f358-7da3-11f0-8757-52540067a9c9"
REF = "e3ce4858-c61b-11f1-9a8a-52540009ca86"
CONTRACT = "01ce0e08-09a5-11f1-9689-52540067a9c9"


class FakeReadClient:
    def get(self, entity, params):
        row = {"Ref_Key": REF, "Number": "28000019906", "Date": "2026-10-05T00:00:00",
               "Организация_Key": ORG, "Контрагент_Key": OWNER,
               "ДоговорПоставки_Key": "00000000-0000-0000-0000-000000000000",
               "ДоговорПоставкиНомер": "ALA-58/2025 SD",
               "ДокументПодтверждающийПоставкуНомер": "AAK01032272",
               "ДокументПодтверждающийПоставкуАВРНомер": "",
               "СчетФактура": "", "СчетФактура_Type": "StandardODATA.Undefined",
               "Posted": False,
               "Товары": [{"Товар": "659f9990-bef2-11f0-869d-52540067a9c9",
                           "Товар_Type": "StandardODATA.Catalog_Номенклатура",
                           "ЕдиницаИзмерения_Key": "b93262f6-fd87-11ee-8871-94de80502ae1",
                           "ЕдиницаИзмеренияХраненияОстатков_Key": "b93262f6-fd87-11ee-8871-94de80502ae1"}]}
        return json.dumps({"d": {"results": [row]}}, ensure_ascii=False).encode("utf-8")


def inputs():
    pending = {"mode": "read_only", "scope": {
        "from_date": "2026-09-21", "to_date": "2026-10-13",
        "organization_key": ORG, "counterparty_key": OWNER},
        "pending": [{"ref_key": REF, "number": "28000019906", "date": "2026-10-05T00:00:00"}]}
    contracts = {"mode": "read_only", "status": "unique", "organization_key": ORG,
                 "contract_number": "ALA-58/2025 SD", "candidates": [{
                     "Ref_Key": CONTRACT, "Owner_Key": OWNER, "Организация_Key": ORG,
                     "Description": "ALA-58/2025 SD", "НомерДоговора": ""}]}
    return pending, contracts


class FakePatchResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class ExecutorTests(unittest.TestCase):
    def test_prepare_one_contract_patch(self):
        payload = prepare(FakeReadClient(), *inputs(), REF, "28000019906")
        self.assertEqual(payload["patch_body"], {"ДоговорПоставки_Key": CONTRACT})
        self.assertFalse(payload["other_fields_modified"])

    def test_prepare_rejects_counterparty_scope_mismatch(self):
        pending, contracts = inputs()
        pending["scope"]["counterparty_key"] = "a711f358-7da3-11f0-8757-52540067a9c9"
        with self.assertRaises(ValueError):
            prepare(FakeReadClient(), pending, contracts, REF, "28000019906")

    def test_commit_requires_exact_confirmation(self):
        with self.assertRaises(SystemExit):
            run(["--pending", "x", "--contracts", "y", "--ref-key", REF,
                 "--number", "28000019906", "--commit", "--confirm", "PATCH wrong"])

    def test_patch_transport_sends_exactly_one_field(self):
        client = ReadOnlyOData("https://1cfresh.kz/a/ea38/116539/ru/", "api", "secret")
        with patch("processor.executor.urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = FakePatchResponse()
            self.assertEqual(patch_contract(client, REF, CONTRACT), 200)
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), "PATCH")
            self.assertEqual(json.loads(request.data), {"ДоговорПоставки_Key": CONTRACT})
            self.assertIn("Document_%D0%AD%D0%A1%D0%A4(guid'", request.full_url)


if __name__ == "__main__":
    unittest.main()
