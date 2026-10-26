import json
import unittest

from reference_inspector import inspect_examples
from odata_client import ODataError


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
    def inspect(self, mutate=None, envelope=None):
        class Client(FakeClient):
            def get(self, resource, params):
                data = json.loads(super().get(resource, params))
                if mutate:
                    mutate(resource, data['d']['results'])
                if envelope:
                    data = envelope(resource, data)
                return json.dumps(data).encode('utf-8')
        return inspect_examples(Client(), '2026-09-21', '2026-10-13', ORG, CP)

    def test_rejects_dates_outside_scope_and_invalid_dates(self):
        for date in ('2026-09-20T23:59:59', '2026-10-14T00:00:00', 'invalid', None,
                     '2026-10-05T00:00:00+05:00'):
            with self.subTest(date=date), self.assertRaises(ODataError):
                self.inspect(lambda resource, rows: rows[0].update(Date=date)
                             if resource == 'Document_ЭСФ' else None)

    def test_scope_endpoints_are_inclusive(self):
        for date in ('2026-09-21T00:00:00', '2026-10-13T23:59:59'):
            result = self.inspect(lambda resource, rows: rows[0].update(Date=date)
                                  if resource == 'Document_ЭСФ' else None)
            self.assertEqual(result['eligible_linked_esf'], 1)

    def test_rejects_wrong_identity_and_scope(self):
        for resource, field in (('Document_ЭСФ', 'Ref_Key'),
                                ('Document_ЭСФ', 'Организация_Key'),
                                ('Document_ЭСФ', 'Контрагент_Key'),
                                ('Document_СчетФактураПолученный', 'Ref_Key'),
                                ('Document_СчетФактураПолученный', 'Организация_Key'),
                                ('Document_СчетФактураПолученный', 'Контрагент_Key')):
            with self.subTest(resource=resource, field=field), self.assertRaises(ODataError):
                self.inspect(lambda name, rows: rows[0].update({field: 'wrong'})
                             if name == resource else None)

    def test_missing_and_null_are_distinguished(self):
        def mutate(resource, rows):
            if resource != 'Document_ЭСФ':
                rows[0]['ДокументОснование'] = None
                rows[0]['Товары'] = None
                del rows[0]['Услуги']
        example = self.inspect(mutate)['examples'][0]
        self.assertIn('ДокументОснование', example['null_invoice_fields'])
        self.assertIn('Контрагент_Key', example['missing_invoice_fields'])
        self.assertFalse(example['counterparty_verified'])
        self.assertEqual(example['invoice_sections']['Товары']['state'], 'null')
        self.assertEqual(example['invoice_sections']['Услуги']['state'], 'missing')

    def test_missing_esf_field_is_rejected(self):
        with self.assertRaises(ODataError):
            self.inspect(lambda resource, rows: rows[0].pop('Date')
                         if resource == 'Document_ЭСФ' else None)

    def test_pagination_rejected_for_both_resources_and_envelopes(self):
        for target in ('Document_ЭСФ', 'Document_СчетФактураПолученный'):
            for key in ('__next', '@odata.nextLink', 'odata.nextLink'):
                for outer in (True, False):
                    def envelope(resource, data):
                        if resource == target:
                            (data if outer else data['d'])[key] = 'opaque-continuation'
                        return data
                    with self.subTest(target=target, key=key, outer=outer), self.assertRaises(ODataError):
                        self.inspect(envelope=envelope)

    def test_malformed_and_truncated_collections_rejected(self):
        for rows in ([None], {}, [{}] * 200):
            with self.subTest(rows_type=type(rows).__name__), self.assertRaises(ODataError):
                self.inspect(envelope=lambda resource, data: {'value': rows})

    def test_malformed_or_paginated_section_rejected(self):
        for section in ('text', [None], {'results': [], '__next': 'opaque'}):
            with self.subTest(section=section), self.assertRaises(ODataError):
                self.inspect(lambda resource, rows: rows[0].update({'Услуги': section})
                             if resource != 'Document_ЭСФ' else None)

    def test_non_guid_link_is_diagnostic_without_invoice_get(self):
        for link in ('opaque-reference', '00000000-0000-0000-0000-000000000000'):
            def mutate(resource, rows):
                self.assertEqual(resource, 'Document_ЭСФ')
                rows[0]['СчетФактура'] = link
            result = self.inspect(mutate)
            self.assertIn('warning', result['examples'][0])

    def test_unsupported_link_is_anomaly(self):
        result = self.inspect(lambda resource, rows: rows[0].update({'СчетФактура_Type': 'Other'})
                              if resource == 'Document_ЭСФ' else None)
        self.assertEqual(len(result['anomalies']), 1)
        self.assertEqual(result['examples'], [])

    def test_function_rejects_invalid_limit_before_get(self):
        for limit in (0, 6, True, '1'):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                inspect_examples(None, '2026-09-21', '2026-10-13', ORG, CP, limit)

    def test_json_light_and_wrapped_sections(self):
        def mutate(resource, rows):
            if resource != 'Document_ЭСФ':
                rows[0]['Контрагент_Key'] = CP
                rows[0]['Услуги'] = {'results': rows[0]['Услуги']}
        result = self.inspect(mutate, lambda resource, data: {'value': data['d']['results']})
        self.assertTrue(result['examples'][0]['counterparty_verified'])
        self.assertFalse(result['schema_verified'])
        self.assertFalse(result['receipt_inspected'])

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
