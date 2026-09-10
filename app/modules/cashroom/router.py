from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, func, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.db.models.cashroom import CashDeal, CashAccount, CashMovement, CashAudit
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission
from app.shared.exceptions import NotFound, Conflict, ValidationError

router = APIRouter(prefix="/api/v1/cashroom", tags=["cashroom"])
DB = Annotated[AsyncSession, Depends(get_db)]
Actor = Annotated[User, Depends(requires_permission(Permission.CASHROOM_MANAGE))]
Money = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=6, decimal_places=3)]

class DealBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    entered_on: date
    due_on: date | None = None
    payer: str = Field(min_length=1, max_length=200)
    receiver: str = Field(min_length=1, max_length=200)
    payer_inn: str = Field(default="", max_length=12)
    receiver_inn: str = Field(default="", max_length=12)
    client: str = Field(min_length=1, max_length=200)
    executor: str = Field(min_length=1, max_length=200)
    manager: str = Field(default="", max_length=200)
    amount: Money
    executor_rate: Rate
    client_rate: Rate
    manager_rate: Rate = Decimal(0)
    comment: str = Field(default="", max_length=5000)
    version: int = Field(default=1, ge=1)

    @field_validator("payer_inn", "receiver_inn")
    @classmethod
    def validate_inn(cls, value):
        if value and (not value.isascii() or not value.isdigit() or len(value) not in (10, 12)):
            raise ValueError("ИНН должен содержать 10 или 12 цифр")
        return value

class MovementBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    operation_key: UUID
    account_id: int
    deal_id: int | None = None
    kind: Literal["receive", "issue", "income", "expense", "opening"]
    amount: Money
    occurred_on: date
    client: str = Field(default="", max_length=200)
    manager: str = Field(default="", max_length=200)
    comment: str = Field(default="", max_length=5000)
    comment2: str = Field(default="", max_length=5000)

class AccountBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_config = ConfigDict(str_strip_whitespace=True)

class VoidBody(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    model_config = ConfigDict(str_strip_whitespace=True)


def money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate(amount, executor_rate, client_rate, manager_rate, received=0, issued=0):
    amount, received, issued = money(amount), money(received), money(issued)
    expected_received = money(amount * (1 - Decimal(executor_rate) / 100))
    expected_issued = money(amount * (1 - Decimal(client_rate) / 100))
    salary = money(amount * Decimal(manager_rate) / 100)
    return dict(expected_received=expected_received, expected_issued=expected_issued,
                received=received, issued=issued, receivable=expected_received-received,
                payable=expected_issued-issued, revenue=received-issued, salary=salary,
                profit=received-issued-salary, planned_profit=expected_received-expected_issued-salary)


def deal_out(deal, received=0, issued=0):
    data = {key: getattr(deal, key) for key in DealBody.model_fields}
    data["id"] = deal.id
    data.update(calculate(deal.amount, deal.executor_rate, deal.client_rate, deal.manager_rate, received, issued))
    data["status"] = ("closed" if data["receivable"] <= 0 and data["payable"] <= 0 else
                      "overdue" if deal.due_on and deal.due_on < date.today() and data["receivable"] > 0 else
                      "partial" if received or issued else "waiting")
    return jsonable_encoder(data, custom_encoder={Decimal: str})


def movement_out(row, account_name=""):
    data = {c.name: getattr(row, c.name) for c in CashMovement.__table__.columns}
    data["account_name"] = account_name
    return jsonable_encoder(data, custom_encoder={Decimal: str})


def totals_subquery():
    return select(CashMovement.deal_id,
        func.sum(case((CashMovement.kind == "receive", CashMovement.amount), else_=0)).label("received"),
        func.sum(case((CashMovement.kind == "issue", CashMovement.amount), else_=0)).label("issued")
    ).where(CashMovement.voided.is_(False), CashMovement.deal_id.is_not(None)).group_by(CashMovement.deal_id).subquery()


async def audit(db, actor, action, changes, deal_id=None, movement_id=None):
    db.add(CashAudit(actor_id=actor.id, action=action, changes=jsonable_encoder(changes, custom_encoder={Decimal: str}), deal_id=deal_id, movement_id=movement_id))


@router.get("/suggestions")
async def suggestions(db: DB, actor: Actor,
                      field: Literal["payer", "receiver", "payer_inn", "receiver_inn", "client", "executor", "manager"],
                      q: str = Query("", max_length=200)):
    column = getattr(CashDeal, field)
    pattern = "%" + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    return list((await db.scalars(select(column).where(column != "", column.ilike(pattern, escape="!"))
                                 .distinct().order_by(column).limit(20))).all())


@router.get("/deals")
async def deals(db: DB, actor: Actor, q: str = "", start: date | None = None, end: date | None = None,
                state: Literal["all", "waiting", "partial", "closed", "overdue"] = "all",
                page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    totals = totals_subquery()
    received, issued = func.coalesce(totals.c.received, 0), func.coalesce(totals.c.issued, 0)
    er = func.round(CashDeal.amount * (1-CashDeal.executor_rate/100), 2)
    ei = func.round(CashDeal.amount * (1-CashDeal.client_rate/100), 2)
    salary = func.round(CashDeal.amount * CashDeal.manager_rate/100, 2)
    status = case(((received >= er) & (issued >= ei), "closed"),
                  ((CashDeal.due_on < date.today()) & (received < er), "overdue"),
                  ((received > 0) | (issued > 0), "partial"), else_="waiting")
    query = select(CashDeal, received.label("received"), issued.label("issued")).outerjoin(totals, totals.c.deal_id == CashDeal.id)
    if q.strip():
        pattern = "%" + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        query = query.where(or_(*(getattr(CashDeal, key).ilike(pattern, escape="!") for key in ("payer", "receiver", "payer_inn", "receiver_inn", "client", "executor", "manager"))))
    if start: query = query.where(CashDeal.entered_on >= start)
    if end: query = query.where(CashDeal.entered_on <= end)
    if state != "all": query = query.where(status == state)
    summary_query = query.with_only_columns(CashDeal.amount.label("amount"), (er-received).label("receivable"), (ei-issued).label("payable"), (received-issued-salary).label("profit"), (er-ei-salary).label("planned_profit")).subquery()
    summary_row = (await db.execute(select(func.count().label("count"), *(func.coalesce(func.sum(summary_query.c[key]), 0).label(key) for key in ("amount", "receivable", "payable", "profit", "planned_profit"))).select_from(summary_query))).mappings().one()
    rows = (await db.execute(query.order_by(CashDeal.entered_on.desc(), CashDeal.id.desc()).offset((page-1)*page_size).limit(page_size))).all()
    return {"items": [deal_out(*row) for row in rows], "summary": jsonable_encoder(dict(summary_row), custom_encoder={Decimal: str})}


@router.post("/deals")
async def create_deal(body: DealBody, db: DB, actor: Actor):
    data = body.model_dump(exclude={"version"})
    row = CashDeal(**data, created_by=actor.id)
    db.add(row)
    await db.flush()
    await audit(db, actor, "deal_created", data, row.id)
    await db.commit()
    return {"id": row.id}


@router.put("/deals/{deal_id}")
async def update_deal(deal_id: int, body: DealBody, db: DB, actor: Actor):
    row = await db.get(CashDeal, deal_id, with_for_update=True)
    if row is None: raise NotFound()
    if row.version != body.version: raise Conflict(message="Сделку уже изменили. Откройте её заново перед сохранением")
    changes = {}
    for key, value in body.model_dump(exclude={"version"}).items():
        if getattr(row, key) != value:
            changes[key] = {"before": getattr(row, key), "after": value}
            setattr(row, key, value)
    if changes:
        row.version += 1
        await audit(db, actor, "deal_updated", changes, row.id)
    await db.commit()
    return {"id": row.id}


@router.get("/deals/{deal_id}")
async def detail(deal_id: int, db: DB, actor: Actor):
    row = await db.get(CashDeal, deal_id)
    if row is None: raise NotFound()
    movements = (await db.execute(select(CashMovement, CashAccount.name).join(CashAccount).where(CashMovement.deal_id == deal_id).order_by(CashMovement.occurred_on.desc(), CashMovement.id.desc()))).all()
    received = sum((m.amount for m, _ in movements if m.kind == "receive" and not m.voided), Decimal(0))
    issued = sum((m.amount for m, _ in movements if m.kind == "issue" and not m.voided), Decimal(0))
    history = (await db.execute(select(CashAudit, User.full_name).join(User, User.id == CashAudit.actor_id).where(CashAudit.deal_id == deal_id).order_by(CashAudit.id.desc()).limit(100))).all()
    return {"deal": deal_out(row, received, issued), "movements": [movement_out(m, name) for m, name in movements],
            "history": [{"id": a.id, "action": a.action, "actor": name, "at": a.created_at, "changes": a.changes} for a, name in history]}


@router.get("/accounts")
async def accounts(db: DB, actor: Actor):
    signed = case((CashMovement.kind.in_(["issue", "expense"]), -CashMovement.amount), else_=CashMovement.amount)
    query = select(CashAccount.id, CashAccount.name, func.coalesce(func.sum(case((CashMovement.voided.is_(False), signed), else_=0)), 0).label("balance")).outerjoin(CashMovement).group_by(CashAccount.id, CashAccount.name).order_by(CashAccount.name)
    return jsonable_encoder([dict(r) for r in (await db.execute(query)).mappings()], custom_encoder={Decimal: str})


@router.post("/accounts")
async def create_account(body: AccountBody, db: DB, actor: Actor):
    from sqlalchemy.exc import IntegrityError
    row = CashAccount(name=body.name)
    db.add(row)
    try: await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict(message="Касса с таким названием уже существует")
    return {"id": row.id}


@router.get("/movements")
async def movements(db: DB, actor: Actor, account_id: int | None = None, start: date | None = None, end: date | None = None, page: int = Query(1, ge=1)):
    query = select(CashMovement, CashAccount.name).join(CashAccount)
    if account_id: query = query.where(CashMovement.account_id == account_id)
    if start: query = query.where(CashMovement.occurred_on >= start)
    if end: query = query.where(CashMovement.occurred_on <= end)
    count = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(query.order_by(CashMovement.occurred_on.desc(), CashMovement.id.desc()).offset((page-1)*30).limit(30))).all()
    return {"items": [movement_out(m, name) for m, name in rows], "count": count}


@router.post("/movements")
async def create_movement(body: MovementBody, db: DB, actor: Actor):
    # A stable key allows retry after a lost response without recording the money twice.
    from sqlalchemy.exc import IntegrityError
    data = body.model_dump()
    data["operation_key"] = str(body.operation_key)
    existing = await db.scalar(select(CashMovement).where(CashMovement.operation_key == data["operation_key"]))
    if existing:
        if any(getattr(existing, k) != v for k, v in data.items()):
            raise Conflict(message="Этот платёж уже записан с другими данными")
        return {"id": existing.id}
    if (body.kind in ("receive", "issue")) != (body.deal_id is not None):
        raise ValidationError(message="Получение и выдача должны быть привязаны к сделке")
    if body.deal_id and await db.get(CashDeal, body.deal_id, with_for_update=True) is None: raise NotFound()
    if await db.get(CashAccount, body.account_id, with_for_update=True) is None: raise NotFound(message="Касса не найдена")
    row = CashMovement(**data, created_by=actor.id)
    db.add(row)
    try:
        await db.flush()
        await audit(db, actor, "payment_created", data, body.deal_id, row.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(CashMovement).where(CashMovement.operation_key == data["operation_key"]))
        if existing and all(getattr(existing, k) == v for k, v in data.items()): return {"id": existing.id}
        raise Conflict(message="Платёж уже существует; обновите журнал")
    return {"id": row.id}


@router.post("/movements/{movement_id}/void")
async def void_movement(movement_id: int, body: VoidBody, db: DB, actor: Actor):
    row = await db.get(CashMovement, movement_id, with_for_update=True)
    if row is None: raise NotFound()
    if not row.voided:
        row.voided = True
        await audit(db, actor, "payment_voided", {"reason": body.reason}, row.deal_id, row.id)
    await db.commit()
    return {"id": row.id}
