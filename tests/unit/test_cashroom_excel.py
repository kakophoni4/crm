from io import BytesIO
from datetime import datetime
from types import SimpleNamespace
import openpyxl
import pytest
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.modules.cashroom.import_excel import parse_workbook, import_records
from app.modules.cashroom.router import accounts, deals
from app.modules.db.models.cashroom import CashAccount, CashDeal, CashMovement, CashAudit
from app.shared.exceptions import ValidationError


def workbook():
    book=openpyxl.Workbook();sheet=book.active
    sheet.append(['Дата захода']+[None]*21)
    sheet.append([datetime(2026,9,1),None,'Плательщик','Получатель','1234567890','0123456789','Клиент','Исполнитель',1000,10,20,None,None,900,800,datetime(2026,9,2),None,'Менеджер',1,None,None,'Комментарий'])
    sheet.append([datetime(2026,9,1)])
    cash=book.create_sheet('расходы приходы');cash.append(['Дата','Сумма','Касса','Клиент','Менеджер','Комментарий','Комментарий 2'])
    cash.append([datetime(2026,9,1),500,2,None,None,'Первичный баланс'])
    cash.append([datetime(2026,9,2),-50,1,None,None,'Расход'])
    out=BytesIO();book.save(out);book.close();return out.getvalue()


def test_parse_preserves_identifiers_and_marks_assumed_dates():
    records,warnings=parse_workbook(workbook())
    assert len(records)==3
    assert records[0]['data']['deal']['receiver_inn']=='0123456789'
    assert records[0]['data']['received_on']=='2026-09-02'
    assert len(warnings)==2
    assert parse_workbook(workbook())[0]==records


def test_rejects_invalid_file():
    with pytest.raises(ValidationError):parse_workbook(b'not an xlsx')


@pytest.mark.asyncio
async def test_preview_import_repeat_and_cash_totals():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as conn:
            await conn.execute(text('CREATE TABLE users (id BIGINT PRIMARY KEY, full_name TEXT)'))
            await conn.execute(text("INSERT INTO users VALUES (1, 'Администратор')"))
            for model in (CashAccount,CashDeal,CashMovement,CashAudit):
                await conn.run_sync(lambda c,t=model.__table__:t.create(c))
        async with async_sessionmaker(engine,expire_on_commit=False)() as db:
            records,warnings=parse_workbook(workbook());actor=SimpleNamespace(id=1)
            preview=await import_records(db,actor,records,warnings)
            assert preview['account_changes']=={'1':'50','2':'500'}
            assert await db.scalar(select(func.count()).select_from(CashDeal))==0
            result=await import_records(db,actor,records,warnings,apply=True);await db.commit()
            assert result['deals']==1 and result['operations']==2
            balances={a['name']:a['balance'] for a in await accounts(db,actor)}
            assert balances=={'Касса 1':'50.00','Касса 2':'500.00'}
            result=await deals(db,actor,page=1,page_size=30)
            assert result['items'][0]['received']=='900.00'
            assert result['items'][0]['issued']=='800.00'
            assert result['items'][0]['profit']=='90.00'
            again=await import_records(db,actor,records,warnings,apply=True);await db.commit()
            assert again['skipped']==3 and again['deals']==0 and again['operations']==0
            assert await db.scalar(select(func.count()).select_from(CashMovement))==4
            # A failure rolls back the whole new batch, including account/deal inserts.
            modified=[dict(r,source_key=r['source_key']+'-new') for r in records]
            await import_records(db,actor,modified,warnings,apply=True)
            await db.rollback()
            assert await db.scalar(select(func.count()).select_from(CashDeal))==1
    finally:await engine.dispose()
