import copy
import json
import tempfile
import unittest
from pathlib import Path
from fixtures.receipt_evidence import evidence
from processor.receipt_planner import plan_linked_receipt
from plan_receipt import collection


class ReceiptPlannerTests(unittest.TestCase):
    def plan(self, args=None, existing=None):
        return plan_linked_receipt(*(args or evidence()), existing_receipts=existing)

    def test_continues_existing_invoice_without_recreating(self):
        args = evidence(); original = copy.deepcopy(args)
        result = self.plan(args, [])
        self.assertFalse(result['create_invoice_again'])
        self.assertFalse(result['execution_supported'])
        self.assertEqual(args, original)
        self.assertTrue(result['source_invoice_date_known'])
        self.assertEqual(result['receipt_header_candidates']['НомерВходящегоДокумента'], ' 0001/ACT ')
        self.assertEqual(result['receipt_header_candidates']['ДатаВходящегоДокумента'], '2026-10-03T00:00:00')
        self.assertNotIn('Date', result['receipt_header_candidates'])
        self.assertEqual(result['receipt_date_policy']['calendar_date'], 'preserve_created_receipt_own_date')
        self.assertIn('reference_incoming_date_differs_from_spec', result['reference_deviations'])
        self.assertNotIn('DO-NOT-COPY-ACCOUNT', json.dumps(result))

    def test_cpt_uses_boolean_and_separate_catalog_reference(self):
        result = self.plan(existing=[])
        header = result['receipt_header_candidates']
        self.assertIs(header['УчитыватьКПН'], True)
        self.assertIn('ВидУчетаНУ_Key', header)
        self.assertEqual(result['receipt_service_candidates'][0]['fields']['Содержание'], '')

    def test_existing_basis_or_receipt_rejects_new_creation(self):
        for mode in ('header', 'table', 'search'):
            args = evidence(); rows=[]
            if mode=='header': args[2]['ДокументОснование']='existing'
            elif mode=='table': args[2]['ДокументыОснования']=[{}]
            else:
                rows=[{'Организация_Key':args[2]['Организация_Key'],'Контрагент_Key':args[2]['Контрагент_Key'],
                       'ДокументОснование':args[2]['Ref_Key'],'ДокументОснование_Type':'StandardODATA.Document_СчетФактураПолученный'}]
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.plan(args, rows)

    def test_lookup_missing_is_blocker(self):
        self.assertIn('existing_receipt_lookup_missing', self.plan()['blockers'])

    def test_wrong_scope_link_posted_and_period_rejected(self):
        for index,field,value in ((1,'Date','2026-10-14T00:00:00'),(2,'Posted',True),
                                  (1,'СчетФактура','bad'),(2,'ДоговорКонтрагента_Key','bad')):
            args=evidence(); args[index][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): self.plan(args, [])

    def test_duplicate_or_wrong_owner_catalog_rejected(self):
        for mode in ('duplicate','owner'):
            args=evidence()
            if mode=='duplicate': args[5]['Catalog_ВидыУчетаНУ'] *= 2
            else: args[5]['Catalog_ПодразделенияОрганизаций'][0]['Owner_Key']='wrong'
            with self.assertRaises(ValueError): self.plan(args, [])

    def test_numeric_and_metadata_mismatch_fail_closed(self):
        for mode in ('float','schema'):
            args=evidence()
            if mode=='float': args[2]['Услуги'][0]['Сумма']=1.1
            else: args[0]=args[0].replace(b'Edm.Boolean',b'Edm.String')
            with self.assertRaises(ValueError): self.plan(args, [])

    def test_supply_ambiguity_rejected(self):
        args=evidence(); args[1]['ДокументПодтверждающийПоставкуАВРНомер']='second'
        with self.assertRaises(ValueError): self.plan(args, [])

    def test_linked_invoice_amount_changes_block_continuation(self):
        for mode in ('total', 'row'):
            args=evidence()
            if mode == 'total': args[2]['СуммаДокумента'] += 1
            else: args[2]['Услуги'][0]['Сумма'] += 1
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.plan(args, [])

    def test_reference_different_cost_does_not_override_required_lookup(self):
        args=evidence(); args[4]['Услуги'][0]['СубконтоЗатратБУ1']='different'
        result=self.plan(args, [])
        self.assertIn('reference_cost_subconto_differs_from_spec',result['reference_deviations'])
        self.assertEqual(result['receipt_service_candidates'][0]['fields']['СубконтоЗатратБУ1'],
                         args[5]['Catalog_СтатьиЗатрат'][0]['Ref_Key'])

    def test_partial_receipt_search_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'lookup.json'
            p.write_text('{"value":[],"odata.nextLink":"opaque"}',encoding='utf-8')
            with self.assertRaises(ValueError): collection(p)


if __name__ == '__main__': unittest.main()
