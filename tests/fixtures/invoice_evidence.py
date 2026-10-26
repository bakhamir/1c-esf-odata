"""Invented values and identifiers; represents observed shapes, not live data."""
from decimal import Decimal

from processor.invoice_planner import ORG, SUPPLIER, CONTRACT, ESF, INVOICE


def key(n):
    return f'00000000-0000-4000-8000-{n:012d}'


def example(n=1):
    common = {'Организация_Key': ORG, 'Контрагент_Key': SUPPLIER, 'DeletionMark': False}
    items = []
    services = []
    for index, net in enumerate((Decimal('12.50'), Decimal('7.25'))):
        vat = Decimal('1.50') if index == 0 else Decimal('0.87')
        row = {'Товар': key(30+index), 'Товар_Type': 'StandardODATA.Catalog_Номенклатура',
               'ТоварНаименование': 'Invented service ' + str(index), 'Количество': 1,
               'Цена': net, 'СуммаБезНалогов': net, 'СуммаНДС': vat, 'Сумма': net+vat,
               'ОборотПоРеализации': net, 'СтавкаНДС_Key': key(40),
               'ЕдиницаИзмерения_Key': key(50), 'ЕдиницаИзмеренияХраненияОстатков_Key': key(50)}
        items.append(row)
        services.append({'Номенклатура_Key': row['Товар'], 'Количество': 1, 'Цена': net,
                         'Сумма': net, 'СуммаНДС': vat, 'СтавкаНДС_Key': key(40),
                         'ОборотПоРеализации': net, 'Содержание': '', 'ДатаОборота': '0001-01-01T00:00:00'})
    source = {**common, 'Ref_Key': key(n), 'Number': 'SYNTHETIC-000'+str(n),
              'Date': '2026-10-02T00:00:00', 'ДоговорПоставки_Key': CONTRACT,
              'СчетФактура': key(n+10), 'СчетФактура_Type': 'StandardODATA.'+INVOICE,
              'Валюта_Key': key(60), 'СуммаДокумента': Decimal('22.12'), 'Товары': items}
    invoice = {**common, 'Ref_Key': key(n+10), 'Date': '2026-10-03T10:00:00',
               'ДоговорКонтрагента_Key': CONTRACT, 'ВалютаДокумента_Key': key(60),
               'НомерВходящегоДокумента': source['Number'], 'ДатаВходящегоДокумента': source['Date'],
               'СуммаДокумента': Decimal('22.12'), 'Услуги': list(reversed(services))}
    return source, invoice


def target():
    source, _ = example(9)
    source.update({'СчетФактура': '', 'СчетФактура_Type': 'StandardODATA.Undefined',
                   'ДокументПодтверждающийПоставкуНомер': ' 0009/TEST ',
                   'ДокументПодтверждающийПоставкуАВРНомер': ''})
    return source


def catalogs():
    return {
        'Catalog_ДоговорыКонтрагентов': [{'Ref_Key': CONTRACT, 'DeletionMark': False, 'IsFolder': False,
            'Owner_Key': SUPPLIER, 'Организация_Key': ORG, 'Description': 'ALA-58/2025 SD'}],
        'Catalog_Номенклатура': [{'Ref_Key': key(n), 'DeletionMark': False, 'IsFolder': False,
            'Услуга': True, 'БазоваяЕдиницаИзмерения_Key': key(50)} for n in (30,31)],
        'Catalog_КлассификаторЕдиницИзмерения': [{'Ref_Key': key(50), 'DeletionMark': False, 'Description': 'Усл'}],
        'Catalog_СтавкиНДС': [{'Ref_Key': key(40), 'DeletionMark': False}],
        'Catalog_Валюты': [{'Ref_Key': key(60), 'DeletionMark': False}]}


def metadata():
    header = ''.join(f'<Property Name="{name}" Type="{kind}"/>' for name,kind in (
        ('Организация_Key','Edm.Guid'),('Контрагент_Key','Edm.Guid'),('ДоговорКонтрагента_Key','Edm.Guid'),
        ('ВалютаДокумента_Key','Edm.Guid'),('НомерВходящегоДокумента','Edm.String')))
    row = ''.join(f'<Property Name="{name}" Type="{kind}"/>' for name,kind in (
        ('Номенклатура_Key','Edm.Guid'),('СтавкаНДС_Key','Edm.Guid'),('Количество','Edm.Double'),
        ('Цена','Edm.Double'),('Сумма','Edm.Double'),('СуммаНДС','Edm.Double'),('ОборотПоРеализации','Edm.Double')))
    return f'''<Schema Namespace="StandardODATA"><EntityType Name="{ESF}">
      <Property Name="Товары" Type="Collection(StandardODATA.Row)"/></EntityType>
      <EntityType Name="{INVOICE}">{header}<Property Name="Услуги" Type="Collection(StandardODATA.Row)"/></EntityType>
      <ComplexType Name="Row">{row}</ComplexType><EntityContainer>
      <EntitySet Name="{ESF}" EntityType="StandardODATA.{ESF}"/>
      <EntitySet Name="{INVOICE}" EntityType="StandardODATA.{INVOICE}"/></EntityContainer></Schema>'''.encode('utf-8')
