from __future__ import annotations

# ruff: noqa: RUF001 -- user-facing messages are in Russian
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.service import ChatService
from app.modules.contacts.scope import contact_visibility_clause
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.contacts.serialization import can_see_telegram_user_id
from app.modules.contacts.service import ContactService
from app.modules.db.models.contact import Contact
from app.modules.db.models.enums import UserRole
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import AppError, NotFound, PermissionDenied, ValidationError
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings

router = APIRouter(prefix="/api/v1/vpn", tags=["vpn"])
Reader = Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))]
Writer = Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))]
Database = Annotated[AsyncSession, Depends(get_db)]


class CreateSubscription(BaseModel):
    contact_id: int = Field(gt=0)
    days: int = Field(default=30, ge=1, le=3650)
    kind: Literal["gift", "purchase"] = "gift"
    source_bot_id: int | None = Field(default=None, gt=0)
    source_chat_id: int | None = Field(default=None, gt=0)


class SubscriptionAction(BaseModel):
    action: Literal["renew", "revoke", "resume", "rotate_link", "delete"]
    days: int | None = Field(default=None, ge=1, le=3650)


class NodeSettings(BaseModel):
    drained: bool = False
    capacity_mbps: float | None = Field(default=None, ge=1, le=100000)


class BotCheck(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class BotConfirm(BaseModel):
    challenge: str = Field(min_length=32, max_length=100)
    confirmation: Literal["ЗАМЕНИТЬ БОТА"]


class BotRequestAction(BaseModel):
    state: Literal["done", "dismissed"]


class RequestRenewal(BaseModel):
    days: int = Field(ge=1, le=3650)


@router.get("/bot/notifications")
async def bot_notifications(actor: Reader) -> Any:
    if actor.role != UserRole.ADMIN:
        raise PermissionDenied(message="Рассылка доступна администратору")
    return await control("GET", "/internal/bot/notifications")


@router.get("/bot/requests")
async def bot_requests(
    actor: Reader,
    db: Database,
    contact_id: int | None = Query(default=None, gt=0),
    state: Literal["open", "done", "dismissed"] | None = None,
) -> Any:
    if contact_id is not None:
        await ContactService(db).get_contact(actor, contact_id)
    query = []
    if contact_id:
        query.append(f"contact_id={contact_id}")
    if state:
        query.append(f"state={state}")
    data = await control("GET", "/internal/bot/requests" + ("?" + "&".join(query) if query else ""))
    ids = {item["contact_id"] for item in data["items"] if item["contact_id"] is not None}
    contacts = {}
    if ids:
        ctx = await ScopeLoader(db).load(actor)
        stmt = select(Contact.id, Contact.full_name, Contact.telegram_username).where(
            Contact.id.in_(ids)
        )
        clause = contact_visibility_clause(ctx)
        if clause is not None:
            stmt = stmt.where(clause)
        rows = await db.execute(stmt)
        contacts = {row.id: row for row in rows.all()}
    if actor.role != UserRole.ADMIN:
        data["items"] = [item for item in data["items"] if item["contact_id"] in contacts]
    for item in data["items"]:
        contact = contacts.get(item["contact_id"])
        item["contact_name"] = contact.full_name if contact else None
        item["telegram_username"] = contact.telegram_username if contact else None
    if not can_see_telegram_user_id(actor):
        for item in data["items"]:
            item.pop("user_id", None)
    return data


@router.get("/bot/requests/count")
async def bot_request_count(actor: Reader, db: Database) -> Any:
    data = await bot_requests(actor, db, contact_id=None, state="open")
    return {"open": len(data["items"])}


@router.post("/bot/requests/{identity}")
async def handle_bot_request(
    identity: int, body: BotRequestAction, actor: Writer, db: Database
) -> Any:
    value = await control("GET", f"/internal/bot/requests/{identity}")
    if value["contact_id"] is not None:
        await ContactService(db).get_contact(actor, value["contact_id"])
    elif actor.role != UserRole.ADMIN:
        raise PermissionDenied(message="Заявка без контакта доступна администратору")
    result = await control(
        "POST", f"/internal/bot/requests/{identity}", {**body.model_dump(), "actor_id": actor.id}
    )
    if not can_see_telegram_user_id(actor):
        result.pop("user_id", None)
    return result


@router.post("/bot/requests/{identity}/renew")
async def renew_bot_request(
    identity: int, body: RequestRenewal, actor: Writer, db: Database
) -> Any:
    value = await control("GET", f"/internal/bot/requests/{identity}")
    if value["contact_id"] is None:
        raise ValidationError(message="Сначала привяжите заявку к контакту")
    await ContactService(db).get_contact(actor, value["contact_id"])
    return await control(
        "POST",
        f"/internal/bot/requests/{identity}/renew",
        {"days": body.days, "actor_id": actor.id},
    )


@router.post("/bot/prepare")
async def prepare_bot(body: BotCheck, actor: Writer) -> Any:
    if actor.role != UserRole.ADMIN:
        raise PermissionDenied(message="Смена бота доступна только администратору")
    return await control(
        "POST", "/internal/bot/prepare", {"token": body.token, "actor_id": actor.id}
    )


@router.post("/bot/confirm")
async def confirm_bot(body: BotConfirm, actor: Writer) -> Any:
    if actor.role != UserRole.ADMIN:
        raise PermissionDenied(message="Смена бота доступна только администратору")
    return await control(
        "POST", "/internal/bot/confirm", {**body.model_dump(), "actor_id": actor.id}
    )


async def control(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    token = settings.vpn_control_token.get_secret_value()
    if not token:
        raise AppError("vpn_unavailable", "VPN-сервис ещё не подключён", status=503)
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            result = await client.request(
                method,
                settings.vpn_control_url.rstrip("/") + path,
                json=body,
                headers={"Authorization": "Bearer " + token},
            )
        if result.status_code == 404:
            raise NotFound(message="VPN-подписка не найдена")
        if result.status_code == 400:
            raise ValidationError(message="Операция недоступна для этой подписки")
        result.raise_for_status()
        return result.json()
    except httpx.HTTPError as exc:
        raise AppError("vpn_unavailable", "VPN-сервис временно недоступен", status=503) from exc


def redact(value: dict[str, Any], actor: User) -> dict[str, Any]:
    if not can_see_telegram_user_id(actor):
        value.pop("telegram_user_id", None)
    return value


@router.get("/fleet")
async def fleet(actor: Reader) -> Any:
    return await control("GET", "/internal/fleet")


@router.post("/nodes/{node_id}")
async def node_settings(
    node_id: Literal["pl", "rs", "ee", "fi", "ch", "ro", "kz"], body: NodeSettings, actor: Writer
) -> Any:
    if actor.role != UserRole.ADMIN:
        raise PermissionDenied(message="Настройки серверов доступны администратору")
    return await control(
        "POST", f"/internal/nodes/{node_id}", {**body.model_dump(), "actor_id": actor.id}
    )


@router.get("/subscriptions")
async def subscriptions(
    actor: Reader, db: Database, contact_id: int | None = Query(default=None, gt=0)
) -> Any:
    if contact_id is None and actor.role != UserRole.ADMIN:
        raise PermissionDenied(message="Выберите контакт для просмотра его VPN-подписок")
    if contact_id is not None:
        await ContactService(db).get_contact(actor, contact_id)
    data = await control(
        "GET", "/internal/subscriptions" + (f"?contact_id={contact_id}" if contact_id else "")
    )
    data["items"] = [redact(item, actor) for item in data["items"]]
    return data


@router.post("/subscriptions", status_code=201)
async def create_subscription(body: CreateSubscription, actor: Writer, db: Database) -> Any:
    contact_data = await ContactService(db).get_contact(actor, body.contact_id)
    if body.source_chat_id is not None:
        chat = await ChatService(db).get_chat(actor, body.source_chat_id)
        if chat["contact_id"] != body.contact_id or chat.get("bot_id") != body.source_bot_id:
            raise ValidationError(message="Чат и бот не соответствуют выбранному контакту")
    contact = await db.get(Contact, body.contact_id)
    if contact is None:
        raise NotFound()
    bot = None
    if body.source_bot_id is not None:
        bot = next(
            (item for item in contact_data["linked_bots"] if item["bot_id"] == body.source_bot_id),
            None,
        )
        if bot is None:
            raise ValidationError(message="Бот не связан с выбранным контактом")
    # Telegram identity comes from the authorized CRM contact, never from a submitted username.
    value = await control(
        "POST",
        "/internal/subscriptions",
        {
            **body.model_dump(),
            "actor_id": actor.id,
            "contact_name": contact.full_name,
            "telegram_user_id": contact.telegram_user_id,
            "telegram_username": contact.telegram_username,
            "source_bot_name": bot["bot_name"] if bot else None,
        },
    )
    return redact(value, actor)


async def authorized_subscription(identity: UUID, actor: User, db: AsyncSession) -> dict[str, Any]:
    value = await control("GET", f"/internal/subscriptions/{identity}")
    await ContactService(db).get_contact(actor, value["contact_id"])
    return value


@router.get("/subscriptions/{identity}")
async def get_subscription(identity: UUID, actor: Reader, db: Database) -> Any:
    value = await authorized_subscription(identity, actor, db)
    events = value.get("events", [])
    ids = {event["actor_id"] for event in events}
    if ids:
        rows = await db.execute(
            select(User.id, User.username, User.full_name).where(User.id.in_(ids))
        )
        names = {user.id: (user.username or user.full_name or "Без имени") for user in rows.all()}
        for event in events:
            event["actor_name"] = names.get(event["actor_id"], "Удалённый сотрудник")
    return redact(value, actor)


@router.post("/subscriptions/{identity}/action")
async def subscription_action(
    identity: UUID, body: SubscriptionAction, actor: Writer, db: Database
) -> Any:
    await authorized_subscription(identity, actor, db)
    if body.action == "renew" and body.days is None:
        raise ValidationError(message="Укажите срок продления")
    return redact(
        await control(
            "POST",
            f"/internal/subscriptions/{identity}",
            {**body.model_dump(), "actor_id": actor.id},
        ),
        actor,
    )
