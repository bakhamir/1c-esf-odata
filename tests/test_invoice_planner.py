import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plan_invoice import document, run
from processor.invoice_planner import CONTRACT, ESF, INVOICE, ORG, SUPPLIER, plan_initial_invoice, schema_map


def fixtures():
    xml = f'''<Schema Namespace="StandardODATA" Alias="S">
      <EntityType Name="{ESF}"><Property Name="Товары" Type="Collection(S.Row)"/></EntityType>
      <EntityType Name="{INVOICE}">
        <Property Name="Организация_Key" Type="Edm.Guid"/>
        <Property Name="Контрагент_Key" Type="Edm.Guid"/>
        <Property Name="ДоговорКонтрагента_Key" Type="Edm.Guid"/>
        <Property Name="Услуги" Type="Collection(S.Row)"/>
      </EntityType>
      <ComplexType Name="Row"><Property Name="Сумма" Type="Edm.Decimal" Precision="15" Scale="2" Nullable="false"/></ComplexType>
      <EntityContainer><EntitySet Name="{ESF}" EntityType="S.{ESF}"/>
      <EntitySet Name="{INVOICE}" EntityType="S.{INVOICE}"/></EntityContainer>
    </Schema>'''.encode('utf-8')
    common = {'Организация_Key': ORG, 'Контрагент_Key': SUPPLIER, 'DeletionMark': False}
    target = {**common, 'Ref_Key': '11111111-1111-1111-1111-111111111111',
              'Date': '2026-10-01T12:34:56', 'СчетФактура': '',
              'СчетФактура_Type': 'StandardODATA.Undefined', 'ДоговорПоставки_Key': CONTRACT,
              'ДокументПодтверждающийПоставкуНомер': ' 0001/A ',
              'ДокументПодтверждающийПоставкуАВРНомер': '', 'Товары': [{'Товар': 'synthetic'}]}
    sample = {**common, 'Ref_Key': '22222222-2222-2222-2222-222222222222',
              'Number': 'DO-NOT-COPY', 'Date': '2026-12-01T19:00:00',
              'Услуги': [{'Сумма': 42}], 'ДокументОснование': 'DO-NOT-COPY-BASIS'}
    source = {**copy.deepcopy(target), 'Ref_Key': '33333333-3333-3333-3333-333333333333',
              'СчетФактура': sample['Ref_Key'], 'СчетФактура_Type': 'StandardODATA.' + INVOICE}
    return xml, target, source, sample


class InvoicePlannerTests(unittest.TestCase):
    def test_blocked_plan_preserves_supply_without_copying_sample(self):
        args = fixtures()
        original = copy.deepcopy(args)
        result = plan_initial_invoice(*args)
        self.assertEqual(args, original)
        self.assertEqual(result['supply_number'], ' 0001/A ')
        self.assertFalse(result['execution_supported'])
        self.assertFalse(result['payload_complete'])
        self.assertEqual(result['status'], 'blocked')
        self.assertNotIn('DO-NOT-COPY', json.dumps(result))
        self.assertNotIn('payload', result)
        self.assertEqual(result, plan_initial_invoice(*args))

    def test_resolves_row_constraints_and_aliases(self):
        schema = schema_map(fixtures()[0], INVOICE)
        row = schema['types']['StandardODATA.Row'][0]
        self.assertEqual((row['Precision'], row['Scale'], row['Nullable']), ('15', '2', 'false'))

    def test_row_observations_do_not_assume_multirow_order(self):
        args = list(fixtures())
        args[2]['Товары'][0]['Количество'] = 2
        args[3]['Услуги'][0]['Количество'] = 2
        result = plan_initial_invoice(*args)
        quantity = next(r for r in result['row_mapping_observations'] if r['invoice_field'] == 'Количество')
        self.assertTrue(quantity['equal_in_single_reference_pair'])
        args[2]['Товары'].append({'Количество': 2})
        self.assertEqual(plan_initial_invoice(*args)['row_mapping_observations'], [])

    def test_rejects_bad_scope_dates_links_and_deleted_documents(self):
        for index, key, value in (
            (1, 'Date', '2026-10-14T00:00:00'), (2, 'Date', '2026-09-20T00:00:00'),
            (1, 'Date', '2026-10-01T00:00:00+05:00'),
            (1, 'Организация_Key', SUPPLIER), (3, 'Контрагент_Key', ORG),
            (2, 'СчетФактура_Type', 'Other'), (2, 'СчетФактура', ORG),
            (1, 'СчетФактура', ORG), (1, 'ДоговорПоставки_Key', ORG),
            (3, 'DeletionMark', True), (1, 'DeletionMark', None)):
            args = list(fixtures()); args[index][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                plan_initial_invoice(*args)

    def test_ambiguous_and_nonstring_supply_block(self):
        for value in ('second', 123, None):
            args = list(fixtures())
            if value is None:
                args[1]['ДокументПодтверждающийПоставкуНомер'] = ''
            else:
                args[1]['ДокументПодтверждающийПоставкуАВРНомер'] = value
            self.assertIn('supply_number_missing_or_ambiguous', plan_initial_invoice(*args)['blockers'])

    def test_schema_mismatch_blocks_candidate(self):
        args = list(fixtures()); args[0] = args[0].replace(b'Edm.Guid', b'Edm.String')
        result = plan_initial_invoice(*args)
        self.assertEqual(result['candidate_header_fields'], [])

    def test_missing_complex_type_fails_closed(self):
        xml = fixtures()[0].replace(b'Name="Row"', b'Name="Other"')
        with self.assertRaises(ValueError):
            schema_map(xml, INVOICE)

    def test_cli_is_offline_and_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory); xml, *docs = fixtures()
            (p/'metadata.xml').write_bytes(xml)
            for name, doc in zip(('target', 'source', 'invoice'), docs):
                (p/(name+'.json')).write_text(json.dumps({'value': [doc]}), encoding='utf-8')
            args = ['--metadata', str(p/'metadata.xml')]
            for name in ('target', 'source', 'invoice'):
                args += ['--'+name, str(p/(name+'.json'))]
            args += ['--output', str(p/'plan.json')]
            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network')):
                self.assertEqual(run(args), 0)
            self.assertEqual(json.loads((p/'plan.json').read_text(encoding='utf-8'))['status'], 'blocked')
            with self.assertRaises(SystemExit):
                run(args[:-1] + [str(p/'metadata.xml')])

    def test_partial_collection_is_rejected_without_losing_decimal_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'data.json'
            p.write_text('{"value":[{"amount":0.1234567890123456789}]}', encoding='utf-8')
            self.assertEqual(str(document(p)['amount']), '0.1234567890123456789')
            p.write_text('{"value":[{}],"odata.nextLink":"opaque"}', encoding='utf-8')
            with self.assertRaises(ValueError):
                document(p)


if __name__ == '__main__':
    unittest.main()
