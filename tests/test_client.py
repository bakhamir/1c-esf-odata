import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from odata_client import ReadOnlyOData, NoRedirect, ODataError, entity_schema, entity_sets, parse_collection, run, service_url


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return b'{"d":{"results":[{"Ref_Key":"abc","Number":"123"}]}}'


class ClientTests(unittest.TestCase):
    def test_service_url_removes_ui_language(self):
        self.assertEqual(service_url("https://1cfresh.kz/a/ea38/116539/ru/"),
                         "https://1cfresh.kz/a/ea38/116539/odata/standard.odata/")

    def test_rejects_insecure_url(self):
        with self.assertRaises(ValueError):
            service_url("http://1cfresh.kz/a/ea38/116539/ru/")

    def test_metadata_entities(self):
        xml = b'<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx"><EntitySet Name="Document_Test"/><EntitySet Name="Catalog_Test"/></edmx:Edmx>'
        self.assertEqual(entity_sets(xml), ["Catalog_Test", "Document_Test"])

    def test_schema_reports_property_types(self):
        xml = '''<Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
            <EntityType Name="Document_ЭСФ"><Key><PropertyRef Name="Ref_Key"/></Key>
              <Property Name="Ref_Key" Type="Edm.Guid"/>
              <Property Name="СчетФактура" Type="Edm.String"/>
            </EntityType>
            <EntityContainer Name="Container"><EntitySet Name="Document_ЭСФ" EntityType="Test.Document_ЭСФ"/></EntityContainer>
        </Schema>'''.encode("utf-8")
        schema = entity_schema(xml, "Document_ЭСФ")
        self.assertEqual(schema["fields"][1], {"name": "СчетФактура", "type": "Edm.String", "kind": "Property"})

    def test_parse_odata_v3(self):
        self.assertEqual(parse_collection(b'{"d":{"results":[{"Number":"1"}]}}'), [{"Number": "1"}])

    def test_only_get_and_no_cross_origin_redirect(self):
        client = ReadOnlyOData("https://1cfresh.kz/a/ea38/116539/ru/", "api", "secret")
        with patch.object(client.opener, "open", return_value=FakeResponse()) as mocked:
            result = parse_collection(client.get("Document_Test", {"$filter": "Number eq '123'"}))
            req = mocked.call_args.args[0]
            self.assertEqual(req.get_method(), "GET")
            self.assertIn("%24filter=Number%20eq%20%27123%27", req.full_url)
            self.assertEqual(result[0]["Number"], "123")

    def test_redirect_is_refused(self):
        with self.assertRaises(ODataError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.test")

    def test_cyrillic_1c_entity_name_is_accepted_and_encoded(self):
        client = ReadOnlyOData("https://1cfresh.kz/a/ea38/116539/ru/", "api", "secret")
        with patch.object(client.opener, "open", return_value=FakeResponse()) as mocked:
            client.get("Document_ЭСФ", {"$top": 1})
            req = mocked.call_args.args[0]
            self.assertIn("Document_%D0%AD%D0%A1%D0%A4", req.full_url)
            self.assertEqual(req.get_method(), "GET")

    def test_rejects_unsafe_resource(self):
        client = ReadOnlyOData("https://1cfresh.kz/a/ea38/116539/ru/", "api", "secret")
        with self.assertRaises(ValueError):
            client.get("https://elsewhere.test")

    def test_schema_output_is_utf8_and_preserves_cyrillic(self):
        xml = '''<Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
          <EntityType Name="Document_ЭСФ"><Property Name="СчетФактура" Type="Edm.String"/></EntityType>
          <EntityContainer><EntitySet Name="Document_ЭСФ" EntityType="Test.Document_ЭСФ"/></EntityContainer>
        </Schema>'''.encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "schema.json")
            with patch.dict("os.environ", {"ONEC_ODATA_USERNAME": "api", "ONEC_ODATA_PASSWORD": "secret"}), \
                 patch.object(ReadOnlyOData, "get", return_value=xml):
                self.assertEqual(run(["schema", "--entity", "Document_ЭСФ", "--output", dest]), 0)
            result = json.loads(Path(dest).read_text(encoding="utf-8"))
            self.assertEqual(result["fields"][0]["name"], "СчетФактура")


if __name__ == "__main__":
    unittest.main()
