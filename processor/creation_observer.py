"""Compare saved snapshots around a separately authorized native UI operation.

No network, creation, posting, retry, rollback or authorization mechanism.
"""
import datetime as dt

from processor.invoice_planner import ORG, SUPPLIER, CONTRACT, INVOICE, guid

TARGET = 'e3ce4858-c61b-11f1-9a8a-52540009ca86'
MONITORED = ('Ref_Key', 'Number', 'Date', 'DeletionMark', 'Posted', 'DataVersion',
             'Организация_Key', 'Контрагент_Key', 'ДоговорПоставки_Key',
             'СчетФактура', 'СчетФактура_Type', 'Товары', 'Валюта_Key', 'СуммаДокумента',
             'ДокументПодтверждающийПоставкуНомер', 'ДокументПодтверждающийПоставкуАВРНомер')


def observe_creation(before, after, invoice):
    """Report observed state only; never claim that unrelated server effects are absent."""
    for doc in (before, after):
        if any(name not in doc for name in MONITORED):
            raise ValueError('Incomplete monitored snapshot')
        if (guid(doc['Ref_Key']) != TARGET or doc['Number'] != '28000019906'
                or guid(doc['Организация_Key']) != ORG or guid(doc['Контрагент_Key']) != SUPPLIER
                or guid(doc['ДоговорПоставки_Key']) != CONTRACT or doc['DeletionMark'] is not False):
            raise ValueError('Target identity or scope changed')
        stamp = dt.datetime.fromisoformat(doc['Date'])
        if stamp.tzinfo is not None or not dt.date(2026, 9, 21) <= stamp.date() <= dt.date(2026, 10, 13):
            raise ValueError('Target date outside scope')
        if not isinstance(doc['Товары'], list) or not doc['Товары'] or any(not isinstance(r, dict) for r in doc['Товары']):
            raise ValueError('Malformed monitored rows')
    if before['СчетФактура'] not in ('', None) or before['СчетФактура_Type'] != 'StandardODATA.Undefined':
        raise ValueError('Baseline already linked; do not recreate')
    invoice_key = guid(invoice['Ref_Key'])
    if (guid(invoice['Организация_Key']) != ORG or guid(invoice['Контрагент_Key']) != SUPPLIER
            or guid(invoice['ДоговорКонтрагента_Key']) != CONTRACT or invoice.get('DeletionMark') is not False):
        raise ValueError('Created invoice scope mismatch')
    if not isinstance(invoice.get('Number'), str) or not invoice['Number']:
        raise ValueError('Created invoice number absent')
    date = dt.datetime.fromisoformat(invoice['Date'])
    if date.tzinfo is not None:
        raise ValueError('Ambiguous invoice date')
    changed = sorted(name for name in MONITORED if before[name] != after[name])
    protected_changes = [name for name in changed if name not in ('DataVersion', 'СчетФактура', 'СчетФактура_Type')]
    linked = (str(after['СчетФактура']).lower() == invoice_key
              and after['СчетФактура_Type'] == 'StandardODATA.' + INVOICE)
    issues = []
    if not linked:
        issues.append('invoice_link_not_verified')
    if invoice.get('Posted') is not False:
        issues.append('invoice_not_confirmed_unposted')
    if protected_changes:
        issues.append('protected_esf_fields_changed')
    return {'version': 1, 'mode': 'offline_creation_observation',
            'status': 'stop_requires_review' if issues else 'observed_linked_unposted_invoice',
            'issues': issues, 'changed_field_names': changed,
            'protected_changed_field_names': protected_changes, 'monitored_fields': list(MONITORED),
            'invoice_link_matches': linked, 'invoice_time_is_10': date.time() == dt.time(10),
            'esf_posted_state_preserved': before['Posted'] == after['Posted'],
            'execution_supported': False, 'creation_semantics_proven': False,
            'limitations': ['Only selected ESF fields are compared; registers and other records are not observed.',
                            'Snapshots alone do not prove the cause or order of server effects.',
                            'No retry or automatic correction is authorized by this report.']}
