"""Import cashroom workbooks. No customer data is stored in this module."""
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZipFile, BadZipFile

import openpyxl
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text

from app.modules.db.models.cashroom import CashAccount, CashAudit, CashDeal, CashMovement
from app.shared.exceptions import ValidationError


def parse_workbook(content: bytes):
    from app.modules.cashroom.router import DealBody, MovementBody
    try:
        with ZipFile(BytesIO(content)) as z:
            if sum(f.file_size for f in z.infolist()) > 40_000_000:
                raise ValueError("Слишком большой Excel после распаковки")
        book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (BadZipFile, ValueError, KeyError, OSError) as exc:
        raise ValidationError(message="Не удалось прочитать XLSX") from exc
    def string(v):
        return "" if v is None else str(v).strip()
    def number(v, default=None):
        if v is None:
            if default is None: raise ValueError("Не заполнено число")
            return Decimal(default)
        result = Decimal(str(v).replace(" ", "").replace(",", "."))
        if not result.is_finite(): raise ValueError("Некорректное число")
        return result
    def day(v):
        if v is None: return None
        if isinstance(v, datetime): return v.date()
        if isinstance(v, date): return v
        raise ValueError("Дата должна быть датой Excel")
    records, warnings, seen = [], [], Counter()
    def add(kind, sheet, row, data):
        serial = jsonable_encoder(data, custom_encoder={Decimal: lambda v: format(v.normalize(), 'f')})
        digest = sha256(json.dumps([kind, serial], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        seen[digest] += 1
        records.append(dict(kind=kind, sheet=sheet, row=row, data=serial, source_key=f"{digest}:{seen[digest]}"))
    try:
        if len(book.worksheets) != 2: raise ValueError("Ожидается два листа: сделки и расходы/приходы")
        for sheet in book.worksheets:
            if sheet.max_row > 10000: raise ValueError("Не более 10 000 строк на лист")
        sheet = book.worksheets[0]
        header = next(sheet.values)
        if str(header[0]).strip().lower() != "дата захода": raise ValueError("Первый лист не похож на реестр сделок")
        for rownum, raw in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
            r = list(raw) + [None] * 22
            if not any(r[k] is not None for k in (2,3,6,7,8)):
                if r[0] is not None: warnings.append(f"Сделки: строка {rownum} содержит только дату, пропущена")
                continue
            try:
                deal = DealBody(entered_on=day(r[0]), due_on=day(r[1]), payer=string(r[2]), receiver=string(r[3]),
                    payer_inn=string(r[4]), receiver_inn=string(r[5]), client=string(r[6]), executor=string(r[7]),
                    amount=number(r[8]), executor_rate=number(r[9]), client_rate=number(r[10]),
                    manager=string(r[17]), manager_rate=number(r[18],0), comment=string(r[21]))
                received, issued = number(r[13],0), number(r[14],0)
                if received < 0 or issued < 0: raise ValueError("Получение и выдача не могут быть отрицательными")
                issued_on = day(r[15])
                received_on = issued_on or day(r[0])
                if received: warnings.append(f"Сделка, строка {rownum}: дата получения отсутствует; использована {received_on.isoformat()}")
                if issued and not issued_on:
                    issued_on = day(r[0]); warnings.append(f"Сделка, строка {rownum}: для выдачи использована дата захода")
                for amount in (received, issued):
                    if amount: MovementBody(operation_key=uuid5(NAMESPACE_URL,'validate'),account_id=1,deal_id=1,kind='receive',amount=amount,occurred_on=received_on)
                add('deal',sheet.title,rownum,dict(deal=deal.model_dump(exclude={'version'}),received=received,issued=issued,received_on=received_on,issued_on=issued_on))
            except Exception as exc:
                raise ValueError(f"Сделки, строка {rownum}: проверьте поля, суммы, ИНН и даты") from exc
        sheet = book.worksheets[1]
        header = next(sheet.values)
        if [str(v).strip().lower() for v in header[:3]] != ['дата','сумма','касса']: raise ValueError("Второй лист не похож на кассовый журнал")
        for rownum, raw in enumerate(sheet.iter_rows(min_row=2,values_only=True),2):
            r=list(raw)+[None]*7
            if not any(r[k] is not None for k in range(1,7)):
                if r[0] is not None: warnings.append(f"Кассы: строка {rownum} содержит только дату, пропущена")
                continue
            try:
                amount=number(r[1]); account=string(r[2])
                if not account or len(account)>80: raise ValueError("Не указана касса")
                if amount==0: raise ValueError("Нулевая операция")
                body=MovementBody(operation_key=uuid5(NAMESPACE_URL,'validate'),account_id=1,
                    kind='expense' if amount<0 else 'opening' if 'первичный баланс' in string(r[5]).lower() else 'income',
                    amount=abs(amount),occurred_on=day(r[0]),client=string(r[3]),manager=string(r[4]),comment=string(r[5]),comment2=string(r[6]))
                add('movement',sheet.title,rownum,dict(account=account,movement=body.model_dump(exclude={'operation_key','account_id','deal_id'})))
            except Exception as exc:
                raise ValueError(f"Кассы, строка {rownum}: проверьте сумму, дату и номер кассы") from exc
    except ValueError as exc:
        raise ValidationError(message=str(exc)) from exc
    finally:
        book.close()
    if not records: raise ValidationError(message="В файле нет записей для импорта")
    return records, warnings


async def import_records(db, actor, records, warnings, *, apply=False):
    # Serialize imports across workers. Row fingerprints also survive renaming/resaving XLSX.
    if apply and db.bind.dialect.name == 'postgresql':
        await db.execute(text("SELECT pg_advisory_xact_lock(731819401)"))
    existing = set((await db.scalars(select(CashAudit.changes['source_key'].as_string()).where(CashAudit.action=='excel_import'))).all())
    fresh=[r for r in records if r['source_key'] not in existing]
    changes={}
    for r in fresh:
        d=r['data']
        if r['kind']=='deal':
            changes['1']=changes.get('1',Decimal(0))+Decimal(d['received'])-Decimal(d['issued'])
        else:
            m=d['movement']; changes[d['account']]=changes.get(d['account'],Decimal(0))+Decimal(m['amount'])*(-1 if m['kind']=='expense' else 1)
    summary=dict(deals=sum(r['kind']=='deal' for r in fresh),operations=sum(r['kind']=='movement' for r in fresh),
                 skipped=len(records)-len(fresh),account_changes={k:str(v) for k,v in changes.items()},warnings=warnings)
    if not apply: return summary
    from app.modules.cashroom.router import DealBody, MovementBody
    async def account_id(name):
        names=[name,f"Касса {name}"]
        rows=list((await db.scalars(select(CashAccount).where(CashAccount.name.in_(names)))).all())
        if len(rows)>1: raise ValidationError(message=f"Найдены две кассы для номера {name}: переименуйте лишнюю перед импортом")
        if rows: return rows[0].id
        account=CashAccount(name=f"Касса {name}");db.add(account);await db.flush();return account.id
    account_cache={}
    for name in changes: account_cache[name]=await account_id(name)
    for r in fresh:
        data=r['data'];deal_id=None;movement_id=None
        marker=f"Excel: {r['sheet']}, строка {r['row']}"
        if r['kind']=='deal':
            validated=DealBody(**data['deal'])
            row=CashDeal(**validated.model_dump(exclude={'version'}),created_by=actor.id)
            db.add(row);await db.flush();deal_id=row.id
            for kind,key in [('receive','received'),('issue','issued')]:
                if Decimal(data[key])>0:
                    body=MovementBody(operation_key=uuid5(NAMESPACE_URL,r['source_key']+kind),account_id=account_cache['1'],deal_id=deal_id,kind=kind,
                        amount=data[key],occurred_on=data[key+'_on'],client=row.client,manager=row.manager,
                        comment=marker,comment2='Дата получения условная: в Excel отдельной даты нет' if kind=='receive' else '')
                    values=body.model_dump();values['operation_key']=str(body.operation_key)
                    db.add(CashMovement(**values,created_by=actor.id))
        else:
            body=MovementBody(**data['movement'],operation_key=uuid5(NAMESPACE_URL,r['source_key']),account_id=account_cache[data['account']])
            values=body.model_dump();values['operation_key']=str(body.operation_key)
            row=CashMovement(**values,created_by=actor.id);db.add(row);await db.flush();movement_id=row.id
        db.add(CashAudit(actor_id=actor.id,action='excel_import',deal_id=deal_id,movement_id=movement_id,
                         changes={'source_key':r['source_key'],'sheet':r['sheet'],'row':r['row'],'cash_account_for_deals':'1'}))
    await db.flush()
    return summary
