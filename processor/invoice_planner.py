"""Offline discovery plan only. No transport or executable POST payload."""

import datetime as dt
import uuid
import xml.etree.ElementTree as ET

ORG = '57495537-f978-11ee-ad65-94de80502ae1'
SUPPLIER = 'b711f358-7da3-11f0-8757-52540067a9c9'
CONTRACT = '01ce0e08-09a5-11f1-9689-52540067a9c9'
ESF = 'Document_ЭСФ'
INVOICE = 'Document_СчетФактураПолученный'


def schema_map(metadata: bytes, entity: str) -> dict:
    """Resolve qualified row types recursively; preserve metadata constraints."""
    root = ET.fromstring(metadata)
    types, aliases, sets = {}, {}, {}
    for schema in root.iter():
        if schema.tag.rsplit('}', 1)[-1] != 'Schema':
            continue
        namespace = schema.get('Namespace', '')
        if schema.get('Alias'):
            aliases[schema.get('Alias')] = namespace
        for node in schema:
            if node.tag.rsplit('}', 1)[-1] in ('EntityType', 'ComplexType'):
                key = namespace + '.' + node.attrib['Name']
                if key in types:
                    raise ValueError('Duplicate qualified metadata type')
                types[key] = node
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] == 'EntitySet':
            if node.attrib['Name'] in sets:
                raise ValueError('Duplicate entity set')
            sets[node.attrib['Name']] = node.attrib['EntityType']

    def resolve(name):
        prefix, _, suffix = name.rpartition('.')
        return aliases.get(prefix, prefix) + '.' + suffix

    if entity not in sets:
        raise ValueError('Entity set absent from metadata')
    pending, result = [resolve(sets[entity])], {}
    while pending:
        name = pending.pop()
        if name in result:
            continue
        if name not in types:
            raise ValueError('Referenced metadata type absent')
        node = types[name]
        if node.get('BaseType'):
            raise ValueError('Inherited metadata types require explicit support')
        fields = [dict(child.attrib) for child in node
                  if child.tag.rsplit('}', 1)[-1] == 'Property']
        if len({field['Name'] for field in fields}) != len(fields):
            raise ValueError('Duplicate property')
        result[name] = fields
        for field in fields:
            target = field['Type']
            if target.startswith('Collection(') and target.endswith(')'):
                target = target[11:-1]
            if not target.startswith('Edm.'):
                field['ResolvedType'] = resolve(target)
                pending.append(resolve(target))
    return {'entity': entity, 'root_type': resolve(sets[entity]), 'types': result}


def guid(value):
    parsed = uuid.UUID(str(value))
    if not parsed.int:
        raise ValueError('Zero reference')
    return str(parsed)


def plan_initial_invoice(metadata: bytes, target: dict, source: dict, sample: dict,
                         reference_pairs=None, catalogs=None) -> dict:
    """Compare evidence, never infer that a final sample is a creation template."""
    maps = {entity: schema_map(metadata, entity) for entity in (ESF, INVOICE)}
    for doc in (target, source, sample):
        guid(doc.get('Ref_Key'))
        if guid(doc.get('Организация_Key')) != ORG or guid(doc.get('Контрагент_Key')) != SUPPLIER:
            raise ValueError('Document outside prototype scope')
        if doc.get('DeletionMark') is not False:
            raise ValueError('Deleted or unknown deletion state')
    for doc in (target, source):
        stamp = dt.datetime.fromisoformat(doc['Date'])
        if stamp.tzinfo is not None or not dt.date(2026, 9, 21) <= stamp.date() <= dt.date(2026, 10, 13):
            raise ValueError('ESF outside prototype period')
    if guid(source.get('СчетФактура')) != guid(sample['Ref_Key']) or source.get('СчетФактура_Type') != 'StandardODATA.' + INVOICE:
        raise ValueError('Reference pair does not match')
    if guid(target['Ref_Key']) == guid(source['Ref_Key']):
        raise ValueError('Target must differ from linked example')
    if target.get('СчетФактура') not in ('', None) or target.get('СчетФактура_Type') != 'StandardODATA.Undefined':
        raise ValueError('Target already linked or inconsistent')
    if 'СчетФактура' not in target or guid(target.get('ДоговорПоставки_Key')) != CONTRACT:
        raise ValueError('Target contract or link field invalid')

    blockers = ['creation_semantics_unverified', 'esf_link_side_effects_unverified',
                'initial_invoice_defaults_unverified', 'created_invoice_date_unknown',
                'reference_autofill_unverified', 'catalog_values_unverified']
    field_map = []
    for entity, doc in ((ESF, target), (INVOICE, sample)):
        schema = maps[entity]
        for field in schema['types'][schema['root_type']]:
            name = field['Name']
            field_map.append({'entity': entity, 'field': name, 'type': field['Type'],
                              'present': name in doc, 'is_null': name in doc and doc[name] is None})
    header = {f['Name']: f['Type'] for f in maps[INVOICE]['types'][maps[INVOICE]['root_type']]}
    candidates = []
    for dest, origin in (('Организация_Key', 'Организация_Key'),
                         ('Контрагент_Key', 'Контрагент_Key'),
                         ('ДоговорКонтрагента_Key', 'ДоговорПоставки_Key')):
        if header.get(dest) != 'Edm.Guid':
            blockers.append('invoice_header_schema_mismatch:' + dest)
        else:
            candidates.append({'field': dest, 'source': 'target_esf.' + origin,
                               'value': target[origin], 'mapping_status': 'candidate_requires_semantic_confirmation'})
    supply_fields = ('ДокументПодтверждающийПоставкуНомер', 'ДокументПодтверждающийПоставкуАВРНомер')
    values = [target.get(name) for name in supply_fields]
    if any(value is not None and not isinstance(value, str) for value in values) or sum(bool(v and v.strip()) for v in values) != 1:
        blockers.append('supply_number_missing_or_ambiguous')
        supply = None
    else:
        supply = next(v for v in values if v and v.strip())
    blockers.append('supply_field_ui_mapping_unverified')
    sections, section_rows = {}, {}
    for label, doc, name in (('source_esf_items', source, 'Товары'),
                             ('target_esf_items', target, 'Товары'),
                             ('reference_invoice_services', sample, 'Услуги')):
        rows = doc.get(name)
        if isinstance(rows, dict):
            if any(rows.get(k) for k in ('__next', '@odata.nextLink', 'odata.nextLink')):
                raise ValueError('Partial section')
            rows = rows.get('results')
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Malformed section')
        sections[label] = {'rows': len(rows), 'fields': sorted({k for row in rows for k in row})}
        section_rows[label] = rows
        if not rows:
            blockers.append('empty_section:' + label)
    blockers.append('service_row_mapping_unverified')
    from processor.invoice_evidence import compare_pairs, target_row_candidates, check_catalogs
    # Existing call signatures remain valid. Extra evidence is compared, not trusted as a flag.
    evidence = compare_pairs([(source, sample)] + list(reference_pairs or []))
    if any(not pair['contract_consistent'] for pair in evidence['pairs']):
        blockers.append('reference_contract_mismatch')
    catalog_report = check_catalogs(target, catalogs)
    if catalog_report['issues']:
        blockers.extend(catalog_report['issues'])
    service_property = next((field for field in maps[INVOICE]['types'][maps[INVOICE]['root_type']]
                             if field['Name'] == 'Услуги'), {})
    service_type = service_property.get('ResolvedType')
    service_fields = {}
    if header.get('Услуги', '').startswith('Collection(') and service_type in maps[INVOICE]['types']:
        service_fields = {field['Name']: field['Type'] for field in maps[INVOICE]['types'][service_type]}
    row_proposals = []
    usable = [pair for pair in evidence['pairs'] if pair['contract_consistent']]
    if len(usable) >= 2 and all(pair['row_match'] == 'unique_value_match'
                               and pair.get('all_net_plus_vat_equal_gross') for pair in usable):
        row_proposals, row_issues = target_row_candidates(target, service_fields)
        blockers.extend(row_issues)
    for destination, origin, expected in (
            ('ВалютаДокумента_Key', 'Валюта_Key', 'Edm.Guid'),
            ('НомерВходящегоДокумента', 'Number', 'Edm.String')):
        if header.get(destination) == expected and origin in target:
            value = target[origin]
            valid = isinstance(value, str) and bool(value)
            if expected == 'Edm.Guid':
                try:
                    guid(value)
                except ValueError:
                    valid = False
            if valid:
                candidates.append({'field': destination, 'source': 'target_esf.' + origin,
                                   'value': value, 'mapping_status': 'observed_candidate_requires_semantic_confirmation'})
    row_candidates = []
    # A single-row example permits comparison, not a general positional join.
    if all(len(section_rows[label]) == 1 for label in ('source_esf_items', 'reference_invoice_services')):
        origin = section_rows['source_esf_items'][0]
        reference = section_rows['reference_invoice_services'][0]
        for dest, src in (('Номенклатура_Key', 'Товар'), ('Содержание', 'ТоварНаименование'),
                          ('Количество', 'Количество'), ('Цена', 'Цена'), ('Сумма', 'Сумма'),
                          ('Сумма', 'СуммаБезНалогов'),
                          ('СуммаНДС', 'СуммаНДС'), ('СтавкаНДС_Key', 'СтавкаНДС_Key'),
                          ('ОборотПоРеализации', 'ОборотПоРеализации')):
            row_candidates.append({'invoice_field': dest, 'esf_field': src,
                                   'both_present': src in origin and dest in reference,
                                   'equal_in_single_reference_pair': src in origin and dest in reference
                                   and origin[src] == reference[dest],
                                   'mapping_status': 'observation_only'})
    return {'version': 2, 'mode': 'offline_discovery_plan', 'status': 'blocked',
            'execution_supported': False, 'payload_complete': False,
            'schema_maps': maps, 'field_map': field_map, 'sections': sections,
            'row_mapping_observations': row_candidates,
            'reference_comparison': evidence, 'catalog_resolution': catalog_report,
            'candidate_service_rows': row_proposals,
            'candidate_header_fields': candidates, 'supply_number': supply,
            'blockers': blockers,
            'dependencies': {'Date': 'read_created_invoice_date_then_set_time_10:00:00',
                             'receipt_incoming_date': 'created_received_invoice_date',
                             'ДокументОснование': 'future_receipt_reference_semantics_unverified'},
            'excluded_sample_fields': ['Ref_Key', 'Number', 'Date', 'DataVersion',
                                       'ДокументОснование', 'ДокументОснование_Type', 'ДокументыОснования'],
            'note': 'Candidate mappings only; no POST body or link PATCH is generated.'}
