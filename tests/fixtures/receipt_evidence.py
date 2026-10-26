"""Synthetic linked-invoice continuation with distinct invoice/receipt dates."""
from copy import deepcopy
from fixtures.invoice_evidence import example, key
from processor.invoice_planner import ORG
from processor.receipt_planner import RECEIPT, INVOICE


def evidence():
    esf, invoice = example()
    esf.update({'ДокументПодтверждающийПоставкуНомер': ' 0001/ACT ',
                'ДокументПодтверждающийПоставкуАВРНомер': ''})
    invoice.update({'Number': 'SYNTHETIC-INVOICE', 'Posted': False, 'Товары': [],
                    'ДокументОснование': '', 'ДокументОснование_Type': 'StandardODATA.Undefined',
                    'ДокументыОснования': [], 'ПодтвержденДокументамиОтгрузки': False})
    ref_esf, ref_invoice = example(2)
    ref_invoice.update({'ДокументОснование': key(70), 'ДокументОснование_Type': 'StandardODATA.'+RECEIPT})
    reference = {'Ref_Key': key(70), 'Организация_Key': invoice['Организация_Key'],
                 'Контрагент_Key': invoice['Контрагент_Key'], 'ДоговорКонтрагента_Key': invoice['ДоговорКонтрагента_Key'],
                 'DeletionMark': False, 'Date': '2026-10-08T10:00:00',
                 'ДокументОснование': ref_invoice['Ref_Key'], 'ДокументОснование_Type': 'StandardODATA.'+INVOICE,
                 'УчитыватьКПН': True, 'ВидУчетаНУ_Key': key(80), 'ВидОперации': 'Услуги',
                 'ВидВходящегоДокумента': 'Акт выполненных работ', 'ДатаВходящегоДокумента': '2026-10-01T00:00:00',
                 'Услуги': [{'СубконтоЗатратБУ1': key(81), 'СубконтоЗатратБУ1_Type': 'StandardODATA.Catalog_СтатьиЗатрат',
                            'СубконтоЗатратБУ3': key(82), 'СубконтоЗатратБУ3_Type': 'StandardODATA.Catalog_ПодразделенияОрганизаций',
                            'СчетЗатратБУ_Key': 'DO-NOT-COPY-ACCOUNT'}]}
    catalogs = {'Catalog_ВидыУчетаНУ': [{'Ref_Key': key(80), 'Description': 'НУ', 'DeletionMark': False, 'IsFolder': False}],
                'Catalog_СтатьиЗатрат': [{'Ref_Key': key(81), 'Description': 'Расходы по перелету', 'DeletionMark': False, 'IsFolder': False}],
                'Catalog_ПодразделенияОрганизаций': [{'Ref_Key': key(82), 'Description': 'Основное подразделение',
                                                    'DeletionMark': False, 'Owner_Key': ORG}]}
    headers = {
        'Организация_Key':'Edm.Guid','Контрагент_Key':'Edm.Guid','ДоговорКонтрагента_Key':'Edm.Guid',
        'ВалютаДокумента_Key':'Edm.Guid','ДокументОснование':'Edm.String','ДокументОснование_Type':'Edm.String',
        'ВидОперации':'Edm.String','УчитыватьКПН':'Edm.Boolean','ВидУчетаНУ_Key':'Edm.Guid',
        'ВидВходящегоДокумента':'Edm.String','НомерВходящегоДокумента':'Edm.String','ДатаВходящегоДокумента':'Edm.DateTime'}
    fields = {'Номенклатура_Key':'Edm.Guid','СтавкаНДС_Key':'Edm.Guid','Количество':'Edm.Double',
              'Цена':'Edm.Double','Сумма':'Edm.Double','СуммаНДС':'Edm.Double','Содержание':'Edm.String',
              'СубконтоЗатратБУ1':'Edm.String','СубконтоЗатратБУ1_Type':'Edm.String',
              'СубконтоЗатратБУ3':'Edm.String','СубконтоЗатратБУ3_Type':'Edm.String'}
    props = lambda data: ''.join(f'<Property Name="{k}" Type="{v}"/>' for k,v in data.items())
    xml = f'''<Schema Namespace="StandardODATA"><EntityType Name="{RECEIPT}">{props(headers)}
     <Property Name="Услуги" Type="Collection(StandardODATA.Service)"/></EntityType>
     <ComplexType Name="Service">{props(fields)}</ComplexType><EntityContainer>
     <EntitySet Name="{RECEIPT}" EntityType="StandardODATA.{RECEIPT}"/></EntityContainer></Schema>'''.encode('utf-8')
    return [xml, esf, invoice, ref_invoice, reference, catalogs]
