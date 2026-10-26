import copy
import unittest

from fixtures.invoice_evidence import target, example
from processor.creation_observer import TARGET, observe_creation
from processor.invoice_planner import INVOICE


def snapshots():
    before = target()
    before.update(Ref_Key=TARGET, Number='28000019906', Posted=True, DataVersion='synthetic-before')
    after = copy.deepcopy(before)
    _, invoice = example()
    invoice.update(Number='SYNTHETIC-INVOICE', Posted=False)
    after.update({'СчетФактура': invoice['Ref_Key'], 'СчетФактура_Type': 'StandardODATA.'+INVOICE,
                  'DataVersion': 'synthetic-after'})
    return before, after, invoice


class CreationObserverTests(unittest.TestCase):
    def test_linked_snapshot_is_not_claimed_to_prove_semantics(self):
        args = snapshots(); original = copy.deepcopy(args)
        result = observe_creation(*args)
        self.assertEqual(result['status'], 'observed_linked_unposted_invoice')
        self.assertFalse(result['creation_semantics_proven'])
        self.assertEqual(args, original)
        self.assertTrue(result['esf_posted_state_preserved'])

    def test_changed_service_amount_requires_review(self):
        args = snapshots(); args[1]['Товары'][0]['Сумма'] += 1
        result = observe_creation(*args)
        self.assertIn('Товары', result['protected_changed_field_names'])
        self.assertEqual(result['status'], 'stop_requires_review')

    def test_posted_invoice_and_missing_link_require_review(self):
        for mode in ('posted', 'missing_link'):
            args = snapshots()
            if mode == 'posted':
                args[2]['Posted'] = True
            else:
                args[1]['СчетФактура'] = ''
            self.assertEqual(observe_creation(*args)['status'], 'stop_requires_review')

    def test_already_linked_baseline_and_incomplete_snapshot_rejected(self):
        for mode in ('linked', 'missing'):
            args = snapshots()
            if mode == 'linked':
                args[0]['СчетФактура'] = args[2]['Ref_Key']
            else:
                del args[0]['Posted']
            with self.assertRaises(ValueError):
                observe_creation(*args)


if __name__ == '__main__':
    unittest.main()
