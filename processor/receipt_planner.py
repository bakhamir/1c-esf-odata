"""Offline continuation for an existing linked invoice. Never creates it again."""
import datetime as dt

from processor.invoice_planner import ORG, SUPPLIER, CONTRACT, INVOICE, guid, schema_map
from processor.invoice_evidence import table, number, compare_pairs

RECEIPT = 'Document_ПоступлениеТоваровУслуг'


def scoped(doc, contract_field):
    guid(doc['Ref_Key'])
    if (guid(doc['Организация_Key']) != ORG or guid(doc['Контрагент_Key']) != SUPPLIER
            or guid(doc[contract_field]) != CONTRACT or doc.get('DeletionMark') is not False):
        raise ValueError('Document outside prototype scope')


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('Date must be an exact string')
    result = dt.datetime.fromisoformat(value)
    if result.tzinfo is not None:
        raise ValueError('Timezone ambiguity')
    return result


def unique_catalog(catalogs, entity, label, owner=None):
    rows = catalogs.get(entity)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Missing catalog evidence')
    matches = [row for row in rows if row.get('Description') == label
               and row.get('DeletionMark') is False
               and (owner is not None or row.get('IsFolder') is False)
               and (owner is None or row.get('Owner_Key') == owner)]
    if len(matches) != 1:
        raise ValueError('Catalog lookup missing or ambiguous')
    return guid(matches[0]['Ref_Key'])


def plan_linked_receipt(metadata, esf, invoice, reference_invoice, reference_receipt,
                        catalogs, existing_receipts=None):
    """Propose required fields while retaining unknown creation/default semantics."""
    scoped(esf, 'ДоговорПоставки_Key')
    scoped(invoice, 'ДоговорКонтрагента_Key')
    esf_date, invoice_date = stamp(esf['Date']), stamp(invoice['Date'])
    if not dt.date(2026, 9, 21) <= esf_date.date() <= dt.date(2026, 10, 13):
        raise ValueError('ESF date outside prototype period')
    if (guid(esf['СчетФактура']) != guid(invoice['Ref_Key'])
            or esf['СчетФактура_Type'] != 'StandardODATA.' + INVOICE):
        raise ValueError('ESF invoice link mismatch')
    if invoice.get('Posted') is not False:
        raise ValueError('Expected unposted linked invoice for this continuation')
    if table(invoice, 'Товары'):
        raise ValueError('Goods rows require a separate plan')
    services = table(invoice, 'Услуги')
    if not services:
        raise ValueError('No invoice services')
    comparison = compare_pairs([(esf, invoice)])['pairs'][0]
    if number(esf['СуммаДокумента']) != number(invoice['СуммаДокумента']):
        raise ValueError('Source totals differ')
    if (comparison['row_match'] != 'unique_value_match'
            or comparison.get('all_net_plus_vat_equal_gross') is not True
            or comparison['header_equal']['currency'] is not True
            or comparison['header_equal']['total'] is not True):
        raise ValueError('Linked invoice differs from originating ESF; review before receipt planning')

    blockers = ['receipt_creation_semantics_unverified', 'receipt_initial_defaults_unverified',
                'created_receipt_date_unknown', 'receipt_invoice_backlink_effects_unverified',
                'supply_field_ui_mapping_unverified', 'accounting_defaults_not_verified',
                'recovery_journal_not_implemented']
    # This stage must never duplicate an existing basis, even when the caller ignores a warning.
    basis = invoice.get('ДокументОснование')
    if ('ДокументОснование' not in invoice or 'ДокументОснование_Type' not in invoice
            or basis not in ('', None) or invoice['ДокументОснование_Type'] != 'StandardODATA.Undefined'
            or table(invoice, 'ДокументыОснования')):
        raise ValueError('Invoice already has a basis or basis state is incomplete')
    if existing_receipts is None:
        blockers.append('existing_receipt_lookup_missing')
    else:
        if not isinstance(existing_receipts, list):
            raise ValueError('Receipt candidates must be a complete saved list')
        for row in existing_receipts:
            # Include deletion-marked matches in detection: no automatic recreation after a soft delete.
            if not isinstance(row, dict):
                raise ValueError('Malformed receipt candidate')
            if (guid(row['Организация_Key']) != ORG or guid(row['Контрагент_Key']) != SUPPLIER
                    or guid(row['ДокументОснование']) != guid(invoice['Ref_Key'])
                    or row['ДокументОснование_Type'] != 'StandardODATA.' + INVOICE):
                raise ValueError('Unrelated receipt candidate')
        if existing_receipts:
            raise ValueError('Receipt already exists; inspect instead of creating again')
    if invoice_date.time() != dt.time(10):
        blockers.append('invoice_time_not_10')
    if invoice.get('ПодтвержденДокументамиОтгрузки') is not False:
        blockers.append('invoice_shipping_confirmation_requires_review')

    supply_fields = ('ДокументПодтверждающийПоставкуНомер', 'ДокументПодтверждающийПоставкуАВРНомер')
    supplies = [esf.get(name) for name in supply_fields]
    if (any(v is not None and not isinstance(v, str) for v in supplies)
            or sum(bool(v and v.strip()) for v in supplies) != 1):
        raise ValueError('Missing or ambiguous supply number')
    supply_index = next(i for i, value in enumerate(supplies) if value and value.strip())
    supply = supplies[supply_index]

    for doc in (reference_invoice, reference_receipt):
        scoped(doc, 'ДоговорКонтрагента_Key')
    if (guid(reference_invoice['ДокументОснование']) != guid(reference_receipt['Ref_Key'])
            or reference_invoice['ДокументОснование_Type'] != 'StandardODATA.' + RECEIPT
            or guid(reference_receipt['ДокументОснование']) != guid(reference_invoice['Ref_Key'])
            or reference_receipt['ДокументОснование_Type'] != 'StandardODATA.' + INVOICE):
        raise ValueError('Reference invoice/receipt chain mismatch')

    tax = unique_catalog(catalogs, 'Catalog_ВидыУчетаНУ', 'НУ')
    cost = unique_catalog(catalogs, 'Catalog_СтатьиЗатрат', 'Расходы по перелету')
    department = unique_catalog(catalogs, 'Catalog_ПодразделенияОрганизаций', 'Основное подразделение', ORG)
    if reference_receipt.get('УчитыватьКПН') is not True or reference_receipt.get('ВидУчетаНУ_Key') != tax:
        blockers.append('tax_accounting_mapping_unverified')
    if reference_receipt.get('ВидОперации') != 'Услуги':
        blockers.append('services_operation_mapping_unverified')
    if reference_receipt.get('ВидВходящегоДокумента') != 'Акт выполненных работ':
        blockers.append('incoming_document_type_mapping_unverified')

    schema = schema_map(metadata, RECEIPT)
    header_properties = schema['types'][schema['root_type']]
    header_types = {f['Name']: f['Type'] for f in header_properties}
    service_prop = next((f for f in header_properties if f['Name'] == 'Услуги'), {})
    row_type = service_prop.get('ResolvedType')
    if not service_prop.get('Type', '').startswith('Collection(') or row_type not in schema['types']:
        raise ValueError('Receipt service schema missing')
    row_types = {f['Name']: f['Type'] for f in schema['types'][row_type]}
    header = {
        'Организация_Key': ORG, 'Контрагент_Key': SUPPLIER, 'ДоговорКонтрагента_Key': CONTRACT,
        'ВалютаДокумента_Key': guid(invoice['ВалютаДокумента_Key']),
        'ДокументОснование': guid(invoice['Ref_Key']), 'ДокументОснование_Type': 'StandardODATA.' + INVOICE,
        'ВидОперации': 'Услуги', 'УчитыватьКПН': True, 'ВидУчетаНУ_Key': tax,
        'ВидВходящегоДокумента': 'Акт выполненных работ', 'НомерВходящегоДокумента': supply,
        'ДатаВходящегоДокумента': dt.datetime.combine(invoice_date.date(), dt.time()).isoformat()}
    for name, value in header.items():
        expected = ('Edm.Boolean' if isinstance(value, bool) else 'Edm.Guid' if name.endswith('_Key')
                    else 'Edm.DateTime' if name == 'ДатаВходящегоДокумента' else 'Edm.String')
        if header_types.get(name) != expected:
            raise ValueError('Receipt header schema mismatch')
    proposals = []
    for index, row in enumerate(services, start=1):
        fields = {k: guid(row[k]) for k in ('Номенклатура_Key', 'СтавкаНДС_Key')}
        for name in ('Количество', 'Цена', 'Сумма', 'СуммаНДС'):
            if row_types.get(name) not in ('Edm.Double', 'Edm.Decimal', 'Edm.Int64', 'Edm.Int32'):
                raise ValueError('Receipt numeric schema mismatch')
            fields[name] = str(number(row[name]))
        if not isinstance(row.get('Содержание'), str):
            raise ValueError('Invoice service content absent')
        fields.update({'Содержание': row['Содержание'], 'СубконтоЗатратБУ1': cost,
                       'СубконтоЗатратБУ1_Type': 'StandardODATA.Catalog_СтатьиЗатрат',
                       'СубконтоЗатратБУ3': department,
                       'СубконтоЗатратБУ3_Type': 'StandardODATA.Catalog_ПодразделенияОрганизаций'})
        for name in fields:
            if name not in ('Количество', 'Цена', 'Сумма', 'СуммаНДС'):
                if row_types.get(name) != ('Edm.Guid' if name.endswith('_Key') else 'Edm.String'):
                    raise ValueError('Receipt row schema mismatch')
        proposals.append({'line': index, 'fields': fields,
                          'numeric_encoding': 'decimal_text_for_review_not_wire_JSON'})
    deviations = []
    expected_incoming = stamp(reference_invoice['Date']).date()
    if stamp(reference_receipt['ДатаВходящегоДокумента']).date() != expected_incoming:
        deviations.append('reference_incoming_date_differs_from_spec')
    reference_rows = table(reference_receipt, 'Услуги')
    if not reference_rows:
        raise ValueError('Reference services absent')
    for row in reference_rows:
        if row.get('СубконтоЗатратБУ1') != cost:
            deviations.append('reference_cost_subconto_differs_from_spec')
        if row.get('СубконтоЗатратБУ1_Type') != 'StandardODATA.Catalog_СтатьиЗатрат':
            blockers.append('cost_subconto_type_unverified')
        if row.get('СубконтоЗатратБУ3_Type') != 'StandardODATA.Catalog_ПодразделенияОрганизаций':
            blockers.append('department_subconto_type_unverified')
    return {'version': 1, 'mode': 'offline_linked_invoice_continuation', 'status': 'blocked',
            'execution_supported': False, 'payload_complete': False, 'create_invoice_again': False,
            'source_invoice_date_known': True,
            'initial_invoice_observed': {'posted': False, 'basis_empty': True,
                                         'service_rows': len(services), 'time_10': invoice_date.time() == dt.time(10),
                                         'content_all_empty': all(row.get('Содержание') == '' for row in services),
                                         'row_turnover_dates_all_unset': all(
                                             isinstance(row.get('ДатаОборота'), str) and row['ДатаОборота'].startswith('0001-01-01')
                                             for row in services),
                                         'matched_origin_rows': comparison['matched_rows'],
                                         'limitation': 'Observed initial values, not universal defaults for future POST.'},
            'receipt_header_candidates': header, 'receipt_service_candidates': proposals,
            'reference_deviations': sorted(set(deviations)), 'blockers': sorted(set(blockers)),
            'supply_number_source': supply_fields[supply_index],
            'receipt_date_policy': {'calendar_date': 'preserve_created_receipt_own_date', 'time': '10:00:00'},
            'untouched_accounting_fields': ['СчетЗатратБУ_Key', 'СчетЗатратНУ_Key', 'СчетУчетаНДС_Key',
                                           'СубконтоЗатратБУ2', 'СубконтоЗатратНУ1', 'СубконтоЗатратНУ2',
                                           'СубконтоЗатратНУ3', 'НДСВидОборота', 'НДСВидПоступления_Key'],
            'next_stages': ['create_receipt_after_separate_approval', 'verify_receipt',
                            'post_receipt_after_separate_approval', 'confirm_shipping_and_post_invoice',
                            'verify_origin_esf_and_post_only_if_required_and_approved'],
            'limitations': ['No API command equivalence, initial defaults or server freshness proven.',
                            'No reference accounting values copied except explicitly required candidates.',
                            'Empty reverse-link search cannot exclude receipts created under other link fields.']}
