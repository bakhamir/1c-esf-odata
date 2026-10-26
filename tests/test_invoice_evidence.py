import copy
import unittest
from decimal import Decimal
from fixtures.invoice_evidence import example, target, catalogs, metadata, key
from processor.invoice_evidence import compare_pairs, check_catalogs, target_row_candidates, number
from processor.invoice_planner import plan_initial_invoice


class EvidenceTests(unittest.TestCase):
    def test_reordered_rows_match_without_position(self):
        result = compare_pairs([example(1), example(2)])
        self.assertEqual(result['matched_rows'], 4)
        self.assertTrue(all(p['all_net_plus_vat_equal_gross'] for p in result['pairs']))
        self.assertFalse(result['pairs'][0]['document_calendar_dates_equal'])

    def test_duplicate_rows_remain_ambiguous(self):
        source, invoice = example()
        source['Товары'] *= 2
        invoice['Услуги'] *= 2
        self.assertEqual(compare_pairs([(source, invoice)])['pairs'][0]['row_match'], 'ambiguous_or_empty')

    def test_different_values_do_not_become_mapping_proof(self):
        source, invoice = example()
        invoice['Услуги'][0]['Цена'] += 1
        self.assertEqual(compare_pairs([(source, invoice)])['matched_rows'], 0)

    def test_duplicate_esf_cannot_inflate_evidence(self):
        with self.assertRaises(ValueError):
            compare_pairs([example(), example()])

    def test_contract_mismatch_excluded(self):
        source, invoice = example()
        invoice['ДоговорКонтрагента_Key'] = key(99)
        result = compare_pairs([(source, invoice)])
        self.assertEqual(result['contract_consistent_pairs'], 0)
        self.assertEqual(result['matched_rows'], 0)

    def test_wrong_reference_scope_rejected(self):
        source, invoice = example()
        invoice['Контрагент_Key'] = key(99)
        with self.assertRaises(ValueError):
            compare_pairs([(source, invoice)])

    def test_invalid_numeric_types_are_rejected(self):
        for value in (True, 1.1, '1.1', Decimal('NaN'), Decimal('Infinity')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)

    def test_catalog_resolution_is_target_specific(self):
        data = catalogs()
        self.assertEqual(check_catalogs(target(), data)['issues'], [])
        data['Catalog_КлассификаторЕдиницИзмерения'][0]['Description'] = 'Усл.'
        self.assertIn('unit_label_requires_confirmation', check_catalogs(target(), data)['issues'])

    def test_deleted_and_duplicate_catalogs_block(self):
        for mode in ('deleted', 'duplicate'):
            data = catalogs()
            rows = data['Catalog_Номенклатура']
            if mode == 'deleted':
                rows[0]['DeletionMark'] = True
            else:
                rows.append(copy.deepcopy(rows[0]))
            self.assertTrue(check_catalogs(target(), data)['issues'])

    def test_proposals_remain_blocked_and_do_not_copy_defaults(self):
        source, invoice = example()
        t = target(); original = copy.deepcopy(t)
        result = plan_initial_invoice(metadata(), t, source, invoice,
                                      reference_pairs=[example(2)], catalogs=catalogs())
        self.assertEqual(len(result['candidate_service_rows']), 2)
        fields = result['candidate_service_rows'][0]['fields']
        self.assertEqual(fields['Сумма'], '12.50')
        self.assertNotIn('Содержание', fields)
        self.assertNotIn('ДатаОборота', fields)
        self.assertNotIn('Date', {p['field'] for p in result['candidate_header_fields']})
        self.assertEqual(t, original)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['payload_complete'])
        self.assertEqual(len(result['blockers']), 8)

    def test_one_pair_does_not_enable_row_proposals(self):
        result = plan_initial_invoice(metadata(), target(), *example())
        self.assertEqual(result['candidate_service_rows'], [])

    def test_bad_target_arithmetic_blocks_its_row(self):
        t = target(); t['Товары'][0]['Сумма'] += 1
        result = plan_initial_invoice(metadata(), t, *example(), reference_pairs=[example(2)])
        self.assertIn('invalid_target_service_row:1', result['blockers'])
        self.assertEqual(len(result['candidate_service_rows']), 1)

    def test_non_numeric_schema_cannot_generate_numeric_candidates(self):
        xml = metadata().replace(b'Edm.Double', b'Edm.String')
        result = plan_initial_invoice(xml, target(), *example(), reference_pairs=[example(2)])
        self.assertEqual(result['candidate_service_rows'], [])


if __name__ == '__main__':
    unittest.main()
