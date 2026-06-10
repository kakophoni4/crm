"""Idempotent dev seed: full CRM dataset for local testing."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.crypto import encrypt_secret
from app.modules.db.models.bot import Bot
from app.modules.db.models.bot_group_assignment import BotGroupAssignment
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.contact_group_transfer import ContactGroupTransfer
from app.modules.db.models.department import Department
from app.modules.db.models.enums import (
    BotOwnerType,
    ChatStatus,
    ContactStatus,
    MessageDirection,
    MessageKind,
    StatusKind,
    TransferStatus,
    UserRole,
    UserStatus,
)
from app.modules.db.models.group import Group
from app.modules.db.models.group_escalation_settings import GroupEscalationSettings
from app.modules.db.models.lead import Lead
from app.modules.db.models.status import Status
from app.modules.db.models.user import User
from app.shared.db import dispose_engine, get_engine

TEST_PASSWORD = "Test1234!"
_ADMIN_EMAIL = "admin@crm.local"
_BOT_CODE = "tg_main"

_DEPARTMENTS = {
    "dept_sales": "Продажи",
    "dept_support": "Поддержка",
}

_GROUPS: dict[str, tuple[str, str]] = {
    "grp_managers": ("Менеджеры", "dept_sales"),
    "grp_support_a": ("Операторы A", "dept_support"),
    "grp_support_b": ("Операторы B", "dept_support"),
}

_USERS: dict[str, dict[str, Any]] = {
    "senior1": {
        "username": "senior1",
        "email": "senior1@crm.local",
        "full_name": "Иван Петров",
        "role": UserRole.SENIOR,
        "group": "grp_managers",
    },
    "senior2": {
        "username": "senior2",
        "email": "senior2@crm.local",
        "full_name": "Мария Сидорова",
        "role": UserRole.SENIOR,
        "group": "grp_support_a",
    },
    "op1": {
        "username": "op1",
        "email": "op1@crm.local",
        "full_name": "Алексей Иванов",
        "role": UserRole.USER,
        "group": "grp_managers",
    },
    "op2": {
        "username": "op2",
        "email": "op2@crm.local",
        "full_name": "Ольга Козлова",
        "role": UserRole.USER,
        "group": "grp_managers",
    },
    "op3": {
        "username": "op3",
        "email": "op3@crm.local",
        "full_name": "Сергей Новиков",
        "role": UserRole.USER,
        "group": "grp_support_a",
    },
    "op4": {
        "username": "op4",
        "email": "op4@crm.local",
        "full_name": "Анна Волкова",
        "role": UserRole.USER,
        "group": "grp_support_b",
    },
}

_DEPARTMENT_HEADS = {
    "dept_sales": "senior1",
    "dept_support": "senior2",
}

_ESCALATION: dict[str, dict[str, Any]] = {
    "grp_managers": {
        "timeout": 10,
        "strategy": "first_responder",
        "notify_owner": True,
        "notify_group": True,
        "updated_by": "senior1",
    },
    "grp_support_a": {
        "timeout": 20,
        "strategy": "random_available",  # DB: chk_ges_reassign_strategy (no round_robin)
        "notify_owner": True,
        "notify_group": True,
        "updated_by": "senior2",
    },
    "grp_support_b": {
        "timeout": 30,
        "strategy": "first_responder",
        "notify_owner": False,
        "notify_group": True,
        "updated_by": "senior2",
    },
}

_CHAT_STATUSES = (
    ("new", "Новый", "#3498DB", 0),
    ("waiting", "Ожидает ответа", "#9B59B6", 1),
    ("answered", "Отвечен", "#F39C12", 2),
    ("done", "Завершён", "#27AE60", 3),
)

_LEAD_STATUSES = (
    ("new", "Новый", None, 0),
    ("in_progress", "В работе", None, 10),
    ("won", "Успешная продажа", None, 900),
    ("lost", "Неуспешная продажа", None, 910),
)

_CONTACTS: dict[str, dict[str, Any]] = {
    "c1": {
        "telegram_user_id": 111001,
        "telegram_username": "andrey_client",
        "full_name": "Андрей Клиентов",
        "phone": "+79001110001",
        "status": ContactStatus.ACTIVE,
        "source": "telegram",
        "department": "dept_sales",
        "created_by": "op1",
    },
    "c2": {
        "telegram_user_id": 111002,
        "telegram_username": "boris_t",
        "full_name": "Борис Тестов",
        "phone": "+79001110002",
        "status": ContactStatus.ACTIVE,
        "source": "telegram",
        "department": "dept_sales",
        "created_by": "op1",
    },
    "c3": {
        "telegram_user_id": 111003,
        "telegram_username": None,
        "full_name": "Вера Иванова",
        "phone": None,
        "status": ContactStatus.NEW,
        "source": "manual",
        "department": "dept_sales",
        "created_by": "op1",
    },
    "c4": {
        "telegram_user_id": 111004,
        "telegram_username": "galina_user",
        "full_name": "Галина Петрова",
        "phone": "+79001110004",
        "status": ContactStatus.ACTIVE,
        "source": "telegram",
        "department": "dept_support",
        "created_by": "op3",
    },
    "c5": {
        "telegram_user_id": 111005,
        "telegram_username": None,
        "full_name": "Дмитрий Сидоров",
        "phone": "+79001110005",
        "status": ContactStatus.ACTIVE,
        "source": "telegram",
        "department": "dept_support",
        "created_by": "op3",
    },
    "c6": {
        "telegram_user_id": 111006,
        "telegram_username": "elena_v",
        "full_name": "Елена Волкова",
        "phone": None,
        "status": ContactStatus.ARCHIVED,
        "source": "telegram",
        "department": "dept_support",
        "created_by": "op3",
    },
}

_ASSIGNMENTS: tuple[tuple[str, str, str | None, str], ...] = (
    ("c1", "grp_managers", "op1", "manual_transfer"),
    ("c2", "grp_managers", "op2", "auto_first_responder"),
    ("c3", "grp_managers", "op1", "manual_transfer"),
    ("c4", "grp_support_a", "op3", "auto_first_responder"),
    ("c5", "grp_support_a", None, "auto_first_responder"),
    ("c5", "grp_support_b", "op4", "manual_transfer"),
    ("c6", "grp_support_b", "op4", "manual_transfer"),
)

_CHAT_SPECS: dict[str, dict[str, Any]] = {
    "chat1": {
        "contact": "c1",
        "bot": True,
        "group": "grp_managers",
        "department": "dept_sales",
        "user": "op1",
        "status": ChatStatus.OPEN,
        "status_code": "new",
        "preview": "Здравствуйте, нужна помощь",
        "index": 1,
    },
    "chat2": {
        "contact": "c2",
        "bot": True,
        "group": "grp_managers",
        "department": "dept_sales",
        "user": "op2",
        "status": ChatStatus.IN_PROGRESS,
        "status_code": "answered",
        "preview": "Уточняем детали сделки",
        "index": 2,
    },
    "chat3": {
        "contact": "c3",
        "bot": False,
        "group": "grp_managers",
        "department": "dept_sales",
        "user": "op1",
        "status": ChatStatus.OPEN,
        "status_code": "waiting",
        "preview": "Ожидаем информацию от клиента",
        "index": 3,
    },
    "chat4": {
        "contact": "c4",
        "bot": True,
        "group": "grp_support_a",
        "department": "dept_support",
        "user": "op3",
        "status": ChatStatus.IN_PROGRESS,
        "status_code": "answered",
        "preview": "Работаем над вашим обращением",
        "index": 4,
    },
    "chat5": {
        "contact": "c5",
        "bot": True,
        "group": "grp_support_b",
        "department": "dept_support",
        "user": "op4",
        "status": ChatStatus.OPEN,
        "status_code": None,
        "preview": "Добрый день!",
        "index": 5,
    },
    "chat6": {
        "contact": "c6",
        "bot": False,
        "group": "grp_support_b",
        "department": "dept_support",
        "user": None,
        "status": ChatStatus.CLOSED,
        "status_code": "done",
        "preview": "Спасибо, вопрос решён",
        "index": 6,
    },
}

_CHAT_MESSAGES: dict[str, tuple[tuple[str, str, str | None, str | None], ...]] = {
    "chat1": (
        ("inbound", "text", "Здравствуйте, нужна помощь со сделкой", None),
        (
            "outbound",
            "text",
            "Добрый день! Готов помочь, уточните пожалуйста номер сделки",
            "op1",
        ),
        ("inbound", "text", "Сделка #12345", None),
    ),
    "chat2": (
        ("inbound", "text", "Когда будет доставка?", None),
        ("outbound", "text", "Ваша сделка в работе, ожидайте завтра", "op2"),
        ("inbound", "text", "Хорошо, спасибо", None),
        ("outbound", "text", "Уточняем детали с курьерской службой", "op2"),
    ),
    "chat3": (
        ("inbound", "text", "Здравствуйте, хочу вернуть товар", None),
        ("outbound", "text", "Пришлите фото товара и чек", "op1"),
        ("inbound", "system", "Чат поставлен на ожидание", None),
    ),
    "chat4": (
        ("inbound", "text", "Не работает приложение", None),
        ("outbound", "text", "Опишите проблему подробнее", "op3"),
        ("inbound", "text", "Ошибка при входе, пишет неверный пароль", None),
        ("outbound", "text", "Отправим ссылку для сброса пароля", "op3"),
    ),
    "chat5": (
        ("inbound", "text", "Добрый день!", None),
        ("outbound", "text", "Здравствуйте! Чем могу помочь?", "op4"),
    ),
    "chat6": (
        ("inbound", "text", "Вопрос по подписке", None),
        ("outbound", "text", "Отвечаем на ваш вопрос...", None),
        ("inbound", "text", "Спасибо, всё понятно!", None),
        ("inbound", "system", "Чат закрыт оператором", None),
    ),
}

_LEAD_SPECS: dict[str, dict[str, Any]] = {
    "lead1": {
        "contact": "c1",
        "group": "grp_managers",
        "bot": True,
        "chat": "chat1",
        "status_code": "in_progress",
        "title": "Сделка №12345",
        "closed": False,
    },
    "lead2": {
        "contact": "c2",
        "group": "grp_managers",
        "bot": True,
        "chat": "chat2",
        "status_code": "new",
        "title": "Доставка товара",
        "closed": False,
    },
    "lead3": {
        "contact": "c3",
        "group": "grp_managers",
        "bot": False,
        "chat": "chat3",
        "status_code": "new",
        "title": "Возврат товара",
        "closed": False,
    },
    "lead4": {
        "contact": "c4",
        "group": "grp_support_a",
        "bot": True,
        "chat": "chat4",
        "status_code": "in_progress",
        "title": "Техподдержка #4401",
        "closed": False,
    },
    "lead5": {
        "contact": "c5",
        "group": "grp_support_b",
        "bot": True,
        "chat": "chat5",
        "status_code": "new",
        "title": "Новое обращение",
        "closed": False,
    },
    "lead6": {
        "contact": "c6",
        "group": "grp_support_b",
        "bot": False,
        "chat": "chat6",
        "status_code": "won",
        "title": "Закрытый вопрос",
        "closed": True,
    },
}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_password(password: str) -> str:
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return digest.decode("utf-8")


def _parse_direction(value: str) -> MessageDirection:
    if value == "outbound":
        return MessageDirection.OUTBOUND
    return MessageDirection.INBOUND


def _parse_kind(value: str) -> MessageKind:
    return MessageKind(value)


async def _get_admin(session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.email == _ADMIN_EMAIL))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise RuntimeError(
            f"Admin user {_ADMIN_EMAIL!r} not found. Run migrations (0004_seed_admin) first."
        )
    return admin


async def _get_or_create_department(
    session: AsyncSession,
    name: str,
    *,
    created_by: int,
) -> Department:
    result = await session.execute(select(Department).where(Department.name == name))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    department = Department(name=name, created_by=created_by)
    session.add(department)
    await session.flush()
    return department


async def _get_or_create_group(
    session: AsyncSession,
    name: str,
    department_id: int,
    *,
    created_by: int,
) -> Group:
    result = await session.execute(
        select(Group).where(Group.name == name, Group.department_id == department_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    group = Group(name=name, department_id=department_id, created_by=created_by)
    session.add(group)
    await session.flush()
    return group


async def _get_or_create_user(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    full_name: str,
    role: UserRole,
    group_id: int | None,
    department_id: int,
    password_hash: str,
    created_by: int,
) -> User:
    result = await session.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.password_hash = password_hash
        existing.status = UserStatus.ACTIVE
        existing.role = role
        existing.group_id = group_id
        existing.department_id = department_id
        await session.flush()
        return existing
    user = User(
        email=email,
        username=username,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
        group_id=group_id,
        department_id=department_id,
        created_by=created_by,
    )
    session.add(user)
    await session.flush()
    return user


async def _get_or_create_status(
    session: AsyncSession,
    *,
    code: str,
    kind: str,
    label: str,
    color: str | None,
    sort_order: int,
) -> Status:
    result = await session.execute(
        select(Status).where(Status.code == code, Status.kind == kind)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.label = label
        existing.color = color
        existing.sort_order = sort_order
        existing.is_active = True
        await session.flush()
        return existing
    status = Status(
        code=code,
        kind=kind,
        label=label,
        color=color,
        sort_order=sort_order,
        is_active=True,
    )
    session.add(status)
    await session.flush()
    return status


async def _get_or_create_escalation(
    session: AsyncSession,
    *,
    group_id: int,
    timeout: int,
    strategy: str,
    notify_owner: bool,
    notify_group: bool,
    updated_by: int | None,
) -> GroupEscalationSettings:
    result = await session.execute(
        select(GroupEscalationSettings).where(GroupEscalationSettings.group_id == group_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.first_response_timeout_minutes = timeout
        existing.new_contact_reassign_strategy = strategy
        existing.notify_owner_on_inbound = notify_owner
        existing.notify_group_on_escalation = notify_group
        existing.updated_by = updated_by
        return existing
    settings = GroupEscalationSettings(
        group_id=group_id,
        first_response_timeout_minutes=timeout,
        new_contact_reassign_strategy=strategy,
        notify_owner_on_inbound=notify_owner,
        notify_group_on_escalation=notify_group,
        updated_by=updated_by,
    )
    session.add(settings)
    await session.flush()
    return settings


async def _ensure_bot_group_assignment(
    session: AsyncSession,
    *,
    bot_id: int,
    group_id: int,
) -> None:
    result = await session.execute(
        select(BotGroupAssignment).where(
            BotGroupAssignment.bot_id == bot_id,
            BotGroupAssignment.group_id == group_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return
    session.add(BotGroupAssignment(bot_id=bot_id, group_id=group_id))
    await session.flush()


async def _get_or_create_bot(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    department_id: int,
    owner_type: BotOwnerType,
    owner_id: int,
    outbound_url: str,
    inbound_secret: str,
    outbound_secret: str,
) -> Bot:
    result = await session.execute(select(Bot).where(Bot.code == code))
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.department_id != department_id:
            existing.department_id = department_id
        if owner_type == BotOwnerType.GROUP:
            await _ensure_bot_group_assignment(
                session,
                bot_id=existing.id,
                group_id=owner_id,
            )
        return existing
    inbound_enc = await encrypt_secret(session, inbound_secret)
    outbound_enc = await encrypt_secret(session, outbound_secret)
    bot = Bot(
        code=code,
        name=name,
        owner_type=owner_type,
        owner_id=owner_id,
        department_id=department_id,
        inbound_secret_encrypted=inbound_enc,
        outbound_secret_encrypted=outbound_enc,
        outbound_url=outbound_url,
        health_url=None,
        is_active=True,
    )
    session.add(bot)
    await session.flush()
    if owner_type == BotOwnerType.GROUP:
        await _ensure_bot_group_assignment(session, bot_id=bot.id, group_id=owner_id)
    return bot


async def _get_or_create_contact(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    full_name: str,
    phone: str | None,
    status: ContactStatus,
    source: str,
    assigned_department_id: int,
    created_by: int,
) -> Contact:
    result = await session.execute(
        select(Contact).where(Contact.telegram_user_id == telegram_user_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    contact = Contact(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        full_name=full_name,
        phone=phone,
        status=status,
        source=source,
        assigned_department_id=assigned_department_id,
        created_by=created_by,
    )
    session.add(contact)
    await session.flush()
    return contact


async def _get_or_create_assignment(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    owner_user_id: int | None,
    assignment_source: str,
) -> ContactGroupAssignment:
    result = await session.execute(
        select(ContactGroupAssignment).where(
            ContactGroupAssignment.contact_id == contact_id,
            ContactGroupAssignment.group_id == group_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    assignment = ContactGroupAssignment(
        contact_id=contact_id,
        group_id=group_id,
        owner_user_id=owner_user_id,
        assignment_source=assignment_source,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def _get_or_create_chat(
    session: AsyncSession,
    *,
    contact_id: int,
    bot_id: int | None,
    assigned_group_id: int,
    assigned_department_id: int,
    assigned_user_id: int | None,
    status: ChatStatus,
    status_id: int | None,
    last_message_preview: str,
    last_message_at: datetime,
) -> Chat:
    result = await session.execute(
        select(Chat).where(
            Chat.contact_id == contact_id,
            Chat.assigned_group_id == assigned_group_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.bot_id = bot_id
        existing.assigned_department_id = assigned_department_id
        existing.assigned_user_id = assigned_user_id
        existing.status = status
        existing.status_id = status_id
        existing.last_message_preview = last_message_preview
        existing.last_message_at = last_message_at
        return existing
    chat = Chat(
        contact_id=contact_id,
        bot_id=bot_id,
        assigned_group_id=assigned_group_id,
        assigned_department_id=assigned_department_id,
        assigned_user_id=assigned_user_id,
        status=status,
        status_id=status_id,
        last_message_preview=last_message_preview,
        last_message_at=last_message_at,
    )
    session.add(chat)
    await session.flush()
    return chat


async def _get_or_create_message(
    session: AsyncSession,
    *,
    idempotency_key: str,
    chat_id: int,
    lead_id: int | None,
    direction: MessageDirection,
    kind: MessageKind,
    text: str | None,
    sender_user_id: int | None,
) -> ChatMessage:
    result = await session.execute(
        select(ChatMessage).where(ChatMessage.idempotency_key == idempotency_key)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    message = ChatMessage(
        chat_id=chat_id,
        lead_id=lead_id,
        direction=direction,
        kind=kind,
        text=text,
        sender_user_id=sender_user_id,
        idempotency_key=idempotency_key,
    )
    session.add(message)
    await session.flush()
    return message


async def _get_or_create_open_lead(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    bot_id: int | None,
    chat_id: int | None,
    status_id: int,
    title: str,
    closed_at: datetime | None,
) -> Lead:
    if closed_at is None:
        result = await session.execute(
            select(Lead).where(
                Lead.contact_id == contact_id,
                Lead.group_id == group_id,
                Lead.closed_at.is_(None),
            )
        )
    else:
        result = await session.execute(
            select(Lead).where(
                Lead.contact_id == contact_id,
                Lead.group_id == group_id,
                Lead.title == title,
                Lead.closed_at.is_not(None),
            )
        )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.bot_id = bot_id
        existing.chat_id = chat_id
        existing.status_id = status_id
        existing.title = title
        existing.closed_at = closed_at
        return existing
    lead = Lead(
        contact_id=contact_id,
        group_id=group_id,
        bot_id=bot_id,
        chat_id=chat_id,
        status_id=status_id,
        title=title,
        closed_at=closed_at,
    )
    session.add(lead)
    await session.flush()
    return lead


async def _get_or_create_transfer(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    from_user_id: int,
    to_user_id: int,
    requested_by: int,
    state: TransferStatus,
    senior_user_id: int | None,
    force_assigned: bool,
    comment: str | None,
    expires_at: datetime,
) -> ContactGroupTransfer:
    result = await session.execute(
        select(ContactGroupTransfer).where(
            ContactGroupTransfer.contact_id == contact_id,
            ContactGroupTransfer.group_id == group_id,
            ContactGroupTransfer.state == state,
            ContactGroupTransfer.from_user_id == from_user_id,
            ContactGroupTransfer.to_user_id == to_user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    transfer = ContactGroupTransfer(
        contact_id=contact_id,
        group_id=group_id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        requested_by=requested_by,
        state=state,
        senior_user_id=senior_user_id,
        force_assigned=force_assigned,
        comment=comment,
        expires_at=expires_at,
    )
    session.add(transfer)
    await session.flush()
    return transfer


async def seed(session: AsyncSession) -> None:
    admin = await _get_admin(session)
    password_hash = _hash_password(TEST_PASSWORD)

    departments: dict[str, Department] = {}
    for key, name in _DEPARTMENTS.items():
        departments[key] = await _get_or_create_department(
            session, name, created_by=admin.id
        )

    groups: dict[str, Group] = {}
    for key, (group_name, dept_key) in _GROUPS.items():
        dept = departments[dept_key]
        groups[key] = await _get_or_create_group(
            session, group_name, dept.id, created_by=admin.id
        )

    users: dict[str, User] = {}
    for key, spec in _USERS.items():
        group = groups[spec["group"]]
        if spec["role"] == UserRole.SENIOR:
            user_group_id: int | None = None
            user_department_id = group.department_id
        else:
            user_group_id = group.id
            user_department_id = group.department_id
        users[key] = await _get_or_create_user(
            session,
            username=spec["username"],
            email=spec["email"],
            full_name=spec["full_name"],
            role=spec["role"],
            group_id=user_group_id,
            department_id=user_department_id,
            password_hash=password_hash,
            created_by=admin.id,
        )

    for dept_key, head_key in _DEPARTMENT_HEADS.items():
        departments[dept_key].head_user_id = users[head_key].id

    chat_statuses: dict[str, Status] = {}
    for code, label, color, sort_order in _CHAT_STATUSES:
        chat_statuses[code] = await _get_or_create_status(
            session,
            code=code,
            kind=StatusKind.CHAT_LABEL.value,
            label=label,
            color=color,
            sort_order=sort_order,
        )

    lead_statuses: dict[str, Status] = {}
    for code, label, color, sort_order in _LEAD_STATUSES:
        lead_statuses[code] = await _get_or_create_status(
            session,
            code=code,
            kind=StatusKind.LEAD_PIPELINE.value,
            label=label,
            color=color,
            sort_order=sort_order,
        )

    for group_key, spec in _ESCALATION.items():
        await _get_or_create_escalation(
            session,
            group_id=groups[group_key].id,
            timeout=spec["timeout"],
            strategy=spec["strategy"],
            notify_owner=spec["notify_owner"],
            notify_group=spec["notify_group"],
            updated_by=users[spec["updated_by"]].id,
        )

    bot = await _get_or_create_bot(
        session,
        code=_BOT_CODE,
        name="Основной бот",
        department_id=departments["dept_sales"].id,
        owner_type=BotOwnerType.GROUP,
        owner_id=groups["grp_managers"].id,
        outbound_url="https://webhook.site/test-seed-bot",
        inbound_secret="seed_inbound_secret_32chars!!",
        outbound_secret="seed_outbound_secret_32chars!",
    )

    contacts: dict[str, Contact] = {}
    for key, spec in _CONTACTS.items():
        contacts[key] = await _get_or_create_contact(
            session,
            telegram_user_id=spec["telegram_user_id"],
            telegram_username=spec["telegram_username"],
            full_name=spec["full_name"],
            phone=spec["phone"],
            status=spec["status"],
            source=spec["source"],
            assigned_department_id=departments[spec["department"]].id,
            created_by=users[spec["created_by"]].id,
        )

    for contact_key, group_key, owner_key, source in _ASSIGNMENTS:
        owner_id = users[owner_key].id if owner_key is not None else None
        await _get_or_create_assignment(
            session,
            contact_id=contacts[contact_key].id,
            group_id=groups[group_key].id,
            owner_user_id=owner_id,
            assignment_source=source,
        )

    chats: dict[str, Chat] = {}
    now = _utc_now()
    for chat_key, spec in _CHAT_SPECS.items():
        status_id = (
            chat_statuses[spec["status_code"]].id if spec["status_code"] is not None else None
        )
        assigned_user_id = users[spec["user"]].id if spec["user"] is not None else None
        chats[chat_key] = await _get_or_create_chat(
            session,
            contact_id=contacts[spec["contact"]].id,
            bot_id=bot.id if spec["bot"] else None,
            assigned_group_id=groups[spec["group"]].id,
            assigned_department_id=departments[spec["department"]].id,
            assigned_user_id=assigned_user_id,
            status=spec["status"],
            status_id=status_id,
            last_message_preview=spec["preview"],
            last_message_at=now - timedelta(minutes=spec["index"] * 10),
        )

    leads: dict[str, Lead] = {}
    chat_lead_links: list[tuple[str, str]] = []
    for lead_key, spec in _LEAD_SPECS.items():
        closed_at = _utc_now() if spec["closed"] else None
        leads[lead_key] = await _get_or_create_open_lead(
            session,
            contact_id=contacts[spec["contact"]].id,
            group_id=groups[spec["group"]].id,
            bot_id=bot.id if spec["bot"] else None,
            chat_id=chats[spec["chat"]].id,
            status_id=lead_statuses[spec["status_code"]].id,
            title=spec["title"],
            closed_at=closed_at,
        )
        chat_lead_links.append((spec["chat"], lead_key))

    await session.flush()
    for chat_key, lead_key in chat_lead_links:
        chat = chats[chat_key]
        lead_id = leads[lead_key].id
        if chat.current_lead_id != lead_id:
            chat.current_lead_id = lead_id

    for chat_key, messages in _CHAT_MESSAGES.items():
        chat = chats[chat_key]
        lead_id = chat.current_lead_id
        for index, (direction_raw, kind_raw, text, sender_key) in enumerate(messages, start=1):
            direction = _parse_direction(direction_raw)
            kind = _parse_kind(kind_raw)
            sender_user_id = users[sender_key].id if sender_key is not None else None
            await _get_or_create_message(
                session,
                idempotency_key=f"seed:{chat_key}:msg{index}",
                chat_id=chat.id,
                lead_id=lead_id,
                direction=direction,
                kind=kind,
                text=text,
                sender_user_id=sender_user_id,
            )

    await _get_or_create_transfer(
        session,
        contact_id=contacts["c2"].id,
        group_id=groups["grp_managers"].id,
        from_user_id=users["op2"].id,
        to_user_id=users["op1"].id,
        requested_by=users["op2"].id,
        state=TransferStatus.PENDING_RECIPIENT,
        senior_user_id=users["senior1"].id,
        force_assigned=False,
        comment="Передаю клиента — ухожу в отпуск",
        expires_at=_utc_now() + timedelta(hours=24),
    )


async def _print_summary(session: AsyncSession) -> None:
    dept_names = list(_DEPARTMENTS.values())
    group_names = [name for name, _ in _GROUPS.values()]
    user_emails = [spec["email"] for spec in _USERS.values()]
    status_codes = [s[0] for s in _CHAT_STATUSES] + [s[0] for s in _LEAD_STATUSES]
    contact_tg_ids = [spec["telegram_user_id"] for spec in _CONTACTS.values()]

    dept_count = int(
        await session.scalar(
            select(func.count()).select_from(Department).where(Department.name.in_(dept_names))
        )
        or 0
    )
    group_count = int(
        await session.scalar(
            select(func.count()).select_from(Group).where(Group.name.in_(group_names))
        )
        or 0
    )
    user_count = int(
        await session.scalar(
            select(func.count()).select_from(User).where(User.email.in_(user_emails))
        )
        or 0
    )
    status_count = int(
        await session.scalar(
            select(func.count()).select_from(Status).where(Status.code.in_(status_codes))
        )
        or 0
    )
    bot_count = int(
        await session.scalar(
            select(func.count()).select_from(Bot).where(Bot.code == _BOT_CODE)
        )
        or 0
    )
    contact_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Contact)
            .where(Contact.telegram_user_id.in_(contact_tg_ids))
        )
        or 0
    )
    chat_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Chat)
            .join(Contact, Chat.contact_id == Contact.id)
            .where(Contact.telegram_user_id.in_(contact_tg_ids))
        )
        or 0
    )
    msg_count = int(
        await session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.idempotency_key.like("seed:%"))
        )
        or 0
    )
    lead_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Lead)
            .join(Contact, Lead.contact_id == Contact.id)
            .where(Contact.telegram_user_id.in_(contact_tg_ids))
        )
        or 0
    )

    print("=" * 50)
    print("SEED ЗАВЕРШЁН")
    print("=" * 50)
    print(f"Отделов:    {dept_count}")
    print(f"Групп:      {group_count}")
    print(f"Статусов:   {status_count}")
    print(f"Ботов:      {bot_count}")
    print(f"Юзеров:     {user_count}")
    print(f"Контактов:  {contact_count}")
    print(f"Чатов:      {chat_count}")
    print(f"Сообщений:  {msg_count}")
    print(f"Лидов:      {lead_count}")
    print()
    print("ТЕСТОВЫЕ АККАУНТЫ:")
    print("  admin   / ChangeMe!234567  (администратор)")
    print("  senior1 / Test1234!        (старший, Продажи)")
    print("  senior2 / Test1234!        (старший, Поддержка)")
    print("  op1     / Test1234!        (оператор, Менеджеры)")
    print("  op3     / Test1234!        (оператор, Операторы A)")
    print("  op4     / Test1234!        (оператор, Операторы B)")


async def main() -> None:
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            await seed(session)
            await session.commit()
            await _print_summary(session)
        except Exception:
            await session.rollback()
            raise
        finally:
            await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
