import json
import unittest

from contract_lookup import find_contract


ORG = "57495537-f978-11ee-ad65-94de80502ae1"


class FakeClient:
    def __init__(self, contracts):
        self.contracts = contracts
        self.last_params = None

    def get(self, entity, params):
        self.last_params = params
        return json.dumps({"d": {"results": self.contracts}}, ensure_ascii=False).encode("utf-8")


class ContractLookupTests(unittest.TestCase):
    def test_unique_contract(self):
        client = FakeClient([{"Ref_Key": "guid", "НомерДоговора": "ALA-58/2025 SD",
                              "Организация_Key": ORG, "Owner_Key": "owner",
                              "DeletionMark": False, "IsFolder": False}])
        result = find_contract(client, "ALA-58/2025 SD", ORG)
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["match_count"], 1)
        self.assertIn("НомерДоговора eq 'ALA-58/2025 SD'", client.last_params["$filter"])

    def test_ambiguous_contract(self):
        obj = {"НомерДоговора": "ALA-58/2025 SD", "Организация_Key": ORG,
               "DeletionMark": False, "IsFolder": False}
        result = find_contract(FakeClient([obj, obj]), "ALA-58/2025 SD", ORG)
        self.assertEqual(result["status"], "ambiguous")

    def test_rejects_invalid_org(self):
        with self.assertRaises(ValueError):
            find_contract(FakeClient([]), "ALA-58/2025 SD", "not-a-guid")


if __name__ == "__main__":
    unittest.main()
