"""Pure comparison of saved evidence. Observations never authorize writes."""
import datetime as dt
from decimal import Decimal, InvalidOperation

from processor.invoice_planner import ORG, SUPPLIER, CONTRACT, INVOICE, guid


def table(document, name):
    rows = document.get(name)
    if isinstance(rows, dict):
        if any(rows.get(key) for key in ('__next', '@odata.nextLink', 'odata.nextLink')):
            raise ValueError('Partial evidence table')
        rows = rows.get('results')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Invalid evidence table')
    return rows


def number(value):
    # float inputs have already lost original decimal precision; reject them.
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError('Expected exact numeric JSON value')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Nonfinite amount')
    return result


def fingerprint(row, source):
    return (guid(row['Товар' if source else 'Номенклатура_Key']),
            *(number(row[key]) for key in ('Количество', 'Цена',
               'СуммаБезНалогов' if source else 'Сумма', 'СуммаНДС')),
            guid(row['СтавкаНДС_Key']))


def compare_pairs(pairs):
    reports, seen = [], set()
    for source, invoice in pairs:
        for doc in (source, invoice):
            if (guid(doc['Организация_Key']) != ORG or guid(doc['Контрагент_Key']) != SUPPLIER
                    or doc.get('DeletionMark') is not False):
                raise ValueError('Reference outside prototype scope')
        stamp = dt.datetime.fromisoformat(source['Date'])
        if stamp.tzinfo is not None or not dt.date(2026, 9, 21) <= stamp.date() <= dt.date(2026, 10, 13):
            raise ValueError('Reference period mismatch')
        key = guid(source['Ref_Key'])
        if key in seen:
            raise ValueError('Duplicate reference ESF cannot increase evidence count')
        seen.add(key)
        if guid(source['СчетФактура']) != guid(invoice['Ref_Key']) or source['СчетФактура_Type'] != 'StandardODATA.' + INVOICE:
            raise ValueError('Unrelated reference pair')
        same_contract = (source.get('ДоговорПоставки_Key') == CONTRACT
                         and invoice.get('ДоговорКонтрагента_Key') == CONTRACT)
        report = {'contract_consistent': same_contract, 'row_match': 'unverified',
                  'matched_rows': 0, 'header_equal': {}}
        for label, left, right in (
            ('currency', 'Валюта_Key', 'ВалютаДокумента_Key'),
            ('total', 'СуммаДокумента', 'СуммаДокумента'),
            ('incoming_number', 'Number', 'НомерВходящегоДокумента')):
            report['header_equal'][label] = (source[left] == invoice[right]
                                             if left in source and right in invoice else None)
        report['document_calendar_dates_equal'] = source['Date'][:10] == invoice['Date'][:10]
        report['header_equal']['incoming_calendar_date'] = (
            source['Date'][:10] == invoice['ДатаВходящегоДокумента'][:10]
            if isinstance(invoice.get('ДатаВходящегоДокумента'), str) else None)
        a, b = table(source, 'Товары'), table(invoice, 'Услуги')
        if not same_contract:
            report['row_match'] = 'excluded_contract_mismatch'
        else:
            try:
                af, bf = [fingerprint(r, True) for r in a], [fingerprint(r, False) for r in b]
                if not a or len(set(af)) != len(af) or len(set(bf)) != len(bf):
                    report['row_match'] = 'ambiguous_or_empty'
                elif set(af) != set(bf):
                    report['row_match'] = 'different_values'
                else:
                    report['row_match'] = 'unique_value_match'
                    report['matched_rows'] = len(af)
                    matched = {fp: row for fp, row in zip(bf, b)}
                    report['all_net_plus_vat_equal_gross'] = all(
                        number(matched[fp]['Сумма']) + number(matched[fp]['СуммаНДС']) == number(row['Сумма'])
                        for fp, row in zip(af, a))
                    report['all_content_empty'] = all(row.get('Содержание') == '' for row in b)
                    report['all_turnover_equal'] = all(
                        'ОборотПоРеализации' in row and 'ОборотПоРеализации' in matched[fp]
                        and number(row['ОборотПоРеализации']) == number(matched[fp]['ОборотПоРеализации'])
                        for fp, row in zip(af, a))
            except (ValueError, KeyError, InvalidOperation):
                report['row_match'] = 'invalid_or_missing_fields'
        reports.append(report)
    return {'pair_count': len(reports), 'contract_consistent_pairs': sum(r['contract_consistent'] for r in reports),
            'matched_rows': sum(r['matched_rows'] for r in reports), 'pairs': reports,
            'limitation': 'Matching fields define the join; they are not independent proof of copying or creation semantics.'}


def target_row_candidates(target, metadata_fields):
    """Produce exact-value proposals only; no guessed content/defaults or JSON body."""
    proposals, problems = [], []
    for index, row in enumerate(table(target, 'Товары'), start=1):
        try:
            if row.get('Товар_Type') != 'StandardODATA.Catalog_Номенклатура':
                raise ValueError('Unsupported product type')
            mapping = {'Номенклатура_Key': guid(row['Товар']), 'СтавкаНДС_Key': guid(row['СтавкаНДС_Key'])}
            if number(row['СуммаБезНалогов']) + number(row['СуммаНДС']) != number(row['Сумма']):
                raise ValueError('Net VAT gross mismatch')
            for dest, origin in (('Количество', 'Количество'), ('Цена', 'Цена'),
                                  ('Сумма', 'СуммаБезНалогов'), ('СуммаНДС', 'СуммаНДС'),
                                  ('ОборотПоРеализации', 'ОборотПоРеализации')):
                mapping[dest] = str(number(row[origin]))
            for name, value in mapping.items():
                expected = 'Edm.Guid' if name.endswith('_Key') else ('Edm.Double', 'Edm.Decimal', 'Edm.Int64', 'Edm.Int32')
                actual = metadata_fields.get(name)
                matches = actual == expected if isinstance(expected, str) else actual in expected
                if not matches:
                    raise ValueError('Row schema mismatch')
            proposals.append({'line': index, 'fields': mapping,
                              'numeric_encoding': 'decimal_text_for_review_not_wire_JSON',
                              'status': 'observed_mapping_candidate_not_executable',
                              'unresolved_fields': ['Содержание', 'ДатаОборота']})
        except (ValueError, KeyError, InvalidOperation):
            problems.append('invalid_target_service_row:' + str(index))
    if not proposals and not problems:
        problems.append('empty_target_service_rows')
    return proposals, problems


def check_catalogs(target, catalogs):
    """Verify exact target references; never equate unit labels by punctuation."""
    if catalogs is None:
        return {'status': 'not_provided', 'issues': ['catalog_evidence_missing']}
    if not isinstance(catalogs, dict):
        raise ValueError('Invalid catalog evidence')
    issues = []
    def exact(entity, key):
        rows = catalogs.get(entity, [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError('Invalid catalog rows')
        found = [r for r in rows if r.get('Ref_Key') == key]
        if len(found) != 1 or found[0].get('DeletionMark') is not False:
            issues.append('catalog_missing_duplicate_or_deleted:' + entity)
            return {}
        return found[0]
    contract = exact('Catalog_ДоговорыКонтрагентов', CONTRACT)
    if (contract.get('Owner_Key') != SUPPLIER or contract.get('Организация_Key') != ORG
            or contract.get('IsFolder') is not False
            or 'ALA-58/2025 SD' not in (contract.get('Description'), contract.get('НомерДоговора'))):
        issues.append('contract_catalog_scope_invalid')
    for row in table(target, 'Товары'):
        product = exact('Catalog_Номенклатура', row.get('Товар'))
        if product.get('Услуга') is not True or product.get('IsFolder') is not False:
            issues.append('target_product_not_verified_service')
        for field in ('ЕдиницаИзмерения_Key', 'ЕдиницаИзмеренияХраненияОстатков_Key'):
            unit = exact('Catalog_КлассификаторЕдиницИзмерения', row.get(field))
            if unit.get('Description') != 'Усл':
                issues.append('unit_label_requires_confirmation')
        if product.get('БазоваяЕдиницаИзмерения_Key') != row.get('ЕдиницаИзмерения_Key'):
            issues.append('product_base_unit_differs')
        exact('Catalog_СтавкиНДС', row.get('СтавкаНДС_Key'))
    exact('Catalog_Валюты', target.get('Валюта_Key'))
    return {'status': 'references_checked_with_issues' if issues else 'target_references_resolved',
            'issues': sorted(set(issues)),
            'limitation': 'Saved evidence only; no freshness, accounting analytics or form semantics asserted.'}
