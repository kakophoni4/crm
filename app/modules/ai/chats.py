# ruff: noqa: RUF001
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.modules.ai.delivery import allowed
from app.modules.ai.router import DB
from app.modules.ai.router import router as admin_router
from app.modules.chats.service import ChatService
from app.modules.db.models.ai import AIAudit, AIChatState, AIRequest
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import MessageDirection, MessageKind
from app.modules.db.models.staff_notification_event import (
    StaffNotificationEvent,
    StaffNotificationKind,
    StaffNotificationStatus,
)
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings

router = APIRouter(prefix="/api/v1/ai/chats", tags=["ai-chats"])
Actor = Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))]


class ModeBody(BaseModel):
    mode: Literal["OFF", "ASSISTANT", "MANAGER"]
    fallback_enabled: bool = False


@router.get("/{chat_id}")
async def state(chat_id: int, actor: Actor, db: DB) -> Any:
    detail = await ChatService(db).get_chat(actor, chat_id)
    row = await db.get(AIChatState, chat_id)
    return {
        "mode": row.mode if row else "OFF",
        "revision": row.revision if row else 0,
        "data": row.data if row else {},
        "global_enabled": settings.ai_auto_replies_enabled,
        "manager": detail.get("card_owner_name"),
    }


@router.put("/{chat_id}")
async def set_mode(chat_id: int, body: ModeBody, actor: Actor, db: DB) -> Any:
    await ChatService(db).get_chat(actor, chat_id)
    # Lock the chat also when its AI state does not exist yet.
    await db.scalar(select(Chat).where(Chat.id == chat_id).with_for_update())
    row = await db.scalar(
        select(AIChatState).where(AIChatState.chat_id == chat_id).with_for_update()
    )
    if row is None:
        row = AIChatState(chat_id=chat_id, updated_by=actor.id, revision=0, data={})
        db.add(row)
    row.mode, row.updated_by, row.revision = body.mode, actor.id, row.revision + 1
    data = dict(row.data)
    data.update(
        fallback_enabled=body.fallback_enabled if body.mode != "OFF" else False,
        pending_request_id=None,
        error=None,
    )
    if body.mode in ("OFF", "ASSISTANT"):
        data.update(
            first_unanswered_at=None,
            fallback_done=False,
            fallback_failed=False,
            notified=False,
            handled_revision=None,
        )
    if body.mode != "OFF":
        latest = await db.scalar(
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id, ChatMessage.kind != MessageKind.SYSTEM)
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )
        if latest and latest.direction == MessageDirection.INBOUND:
            data["last_inbound_id"] = latest.id
            data["first_unanswered_at"] = (
                data.get("first_unanswered_at") or datetime.now(UTC).isoformat()
            )
    row.data = data
    if body.mode == "MANAGER":
        await notify_manager(
            db, await db.get(Chat, chat_id), row, "Сотрудник передал разговор менеджеру"
        )
    db.add(
        AIAudit(
            actor_id=actor.id,
            action="chat.mode",
            status="succeeded",
            data={"chat_id": chat_id, "mode": body.mode, "revision": row.revision},
        )
    )
    await db.commit()
    await publish_notices(db)
    return await state(chat_id, actor, db)


async def notify_manager(db: Any, chat: Any, state: Any, reason: Any) -> None:
    data = dict(state.data)
    if data.get("notified"):
        return
    assignment = await db.scalar(
        select(ContactGroupAssignment).where(
            ContactGroupAssignment.contact_id == chat.contact_id,
            ContactGroupAssignment.group_id == chat.assigned_group_id,
        )
    )
    # A group-scoped event remains in the existing department queue when there is no owner.
    event = StaffNotificationEvent(
        kind=StaffNotificationKind.INBOUND_MESSAGE,
        status=StaffNotificationStatus.SENT,
        contact_id=chat.contact_id,
        chat_id=chat.id,
        group_id=chat.assigned_group_id,
        department_id=chat.assigned_department_id,
        target_user_id=assignment.owner_user_id if assignment else None,
        body_text="ИИ передал разговор сотруднику: "
        + str(reason or "Нужен ответ менеджера")[:1000],
    )
    db.add(event)
    await db.flush()
    data["notified"] = True
    data["notice_id"] = event.id
    state.data = data
    db.info.setdefault("ai_notices", []).append(
        {
            "id": event.id,
            "chat_id": chat.id,
            "contact_id": chat.contact_id,
            "reason": reason,
            "scope": {"user_id": event.target_user_id}
            if event.target_user_id
            else {"group_id": chat.assigned_group_id}
            if chat.assigned_group_id
            else {"department_id": chat.assigned_department_id},
        }
    )


async def publish_notices(db: Any) -> None:
    from app.realtime.events import publish

    for notice in db.info.pop("ai_notices", []):
        scope = notice.pop("scope")
        if all(v is None for v in scope.values()):
            continue
        await publish("chat.ai.handoff", notice, scope=scope)


@admin_router.get("/notices")
async def notices(actor: Actor, db: DB) -> Any:
    rows = await db.scalars(
        select(StaffNotificationEvent)
        .where(
            StaffNotificationEvent.body_text.startswith("ИИ передал разговор"),
            StaffNotificationEvent.status == StaffNotificationStatus.SENT,
        )
        .order_by(StaffNotificationEvent.id.desc())
        .limit(100)
    )
    output = []
    from app.shared.exceptions import AppError

    for event in rows:
        if event.chat_id is None:
            continue
        if event.target_user_id and event.target_user_id != actor.id:
            continue
        try:
            await ChatService(db).get_chat(actor, event.chat_id)
        except AppError:
            continue
        output.append(
            {
                "id": event.id,
                "chat_id": event.chat_id,
                "reason": event.body_text,
                "created_at": event.created_at.isoformat(),
            }
        )
    return {"items": output}


async def scan_chats() -> None:
    if not settings.ai_auto_replies_enabled:
        return
    from app.shared.db import get_session_factory

    async with get_session_factory()() as db:
        queued = await db.scalar(
            select(func.count())
            .select_from(AIRequest)
            .where(AIRequest.status.in_(["queued", "running"]))
        )
        queued = queued or 0
        if queued >= 8:
            return
        rows = list(
            await db.scalars(
                select(AIChatState)
                .where(
                    AIChatState.mode != "OFF",
                    AIChatState.data["first_unanswered_at"].astext.is_not(None),
                )
                .order_by(AIChatState.chat_id)
                .with_for_update(skip_locked=True)
            )
        )
        for state in rows:
            chat = await db.get(Chat, state.chat_id)
            data = dict(state.data)
            if chat is None or not await allowed(db, chat):
                continue
            if (
                not data.get("first_unanswered_at")
                or data.get("handled_revision") == state.revision
            ):
                continue
            pending = (
                await db.get(AIRequest, data["pending_request_id"])
                if data.get("pending_request_id")
                else None
            )
            if pending and pending.status in ("queued", "running", "succeeded"):
                continue
            elapsed = (
                datetime.now(UTC) - datetime.fromisoformat(data["first_unanswered_at"])
            ).total_seconds()
            if state.mode == "MANAGER" and (
                not data.get("fallback_enabled")
                or data.get("fallback_done")
                or data.get("fallback_failed")
                or elapsed < 900
            ):
                continue
            recent = list(
                await db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.chat_id == chat.id, ChatMessage.kind != MessageKind.SYSTEM)
                    .order_by(ChatMessage.id.desc())
                    .limit(50)
                )
            )
            recent.reverse()
            if not recent or recent[-1].direction != MessageDirection.INBOUND:
                continue
            if not (recent[-1].text or "").strip():
                state.mode = "MANAGER"
                await notify_manager(db, chat, state, "Вложение требует просмотра человеком")
                state.data = {**state.data, "handled_revision": state.revision}
                continue
            # Debounce from newest message, while the fallback deadline stays on first inbound.
            newest_at = (
                recent[-1].created_at.replace(tzinfo=UTC)
                if recent[-1].created_at.tzinfo is None
                else recent[-1].created_at
            )
            if (datetime.now(UTC) - newest_at).total_seconds() < 2:
                continue
            messages = [
                {
                    "role": "user" if m.direction == MessageDirection.INBOUND else "assistant",
                    "content": m.text,
                }
                for m in recent
                if (m.text or "").strip()
            ]
            rid = "crm-chat-" + str(uuid4())
            body = {
                "request_id": rid,
                "chat_id": str(chat.id),
                "messages": messages,
                "mode": "fallback" if state.mode == "MANAGER" else "assistant",
                "context": {"manager_notified": bool(data.get("notified"))},
            }
            db.add(
                AIRequest(
                    id=rid,
                    actor_id=state.updated_by,
                    chat_id=chat.id,
                    path="replies",
                    body=body,
                    meta={"revision": state.revision, "trigger_message_id": recent[-1].id},
                )
            )
            state.data = {**data, "pending_request_id": rid, "handled_revision": state.revision}
            queued += 1
            if queued >= 8:
                break
        await db.commit()
        await publish_notices(db)


async def apply_results() -> None:
    from app.modules.db.models.bot_outbound_log import BotOutboundLog
    from app.shared.db import get_session_factory

    async with get_session_factory()() as db:
        rows = list(
            await db.scalars(
                select(AIRequest)
                .where(
                    AIRequest.chat_id.is_not(None), AIRequest.status.in_(["succeeded", "failed"])
                )
                .with_for_update(skip_locked=True)
                .limit(50)
            )
        )
        for row in rows:
            state = await db.scalar(
                select(AIChatState).where(AIChatState.chat_id == row.chat_id).with_for_update()
            )
            chat = await db.get(Chat, row.chat_id)
            if (
                chat is None
                or not state
                or not settings.ai_auto_replies_enabled
                or state.mode == "OFF"
                or state.revision != row.meta["revision"]
                or not await allowed(db, chat)
            ):
                row.status = "obsolete"
                continue
            contact = await db.get(Contact, chat.contact_id)
            result = row.result or {}
            if row.status == "failed" or result.get("action") not in (
                "reply",
                "handoff",
                "no_reply",
            ):
                state.mode = "MANAGER"
                await notify_manager(db, chat, state, "Не удалось получить корректный ответ ИИ")
                state.data = {
                    **state.data,
                    "fallback_failed": row.body["mode"] == "fallback",
                    "error": row.error or {"message": "Некорректный ответ ИИ"},
                }
                row.status = "handled_error"
                continue
            if result["action"] == "handoff":
                state.mode = "MANAGER"
                await notify_manager(db, chat, state, result.get("reason"))
            reply = (result.get("reply") or "").strip()
            if result["action"] == "no_reply" or not reply:
                row.status = "no_reply"
                continue
            if not contact or not contact.telegram_user_id or not chat.bot_id:
                row.status = "handled_error"
                await notify_manager(
                    db, chat, state, "Канал не поддерживает автоматическую отправку"
                )
                continue
            message = ChatMessage(
                chat_id=chat.id,
                lead_id=chat.current_lead_id,
                direction=MessageDirection.OUTBOUND,
                kind=MessageKind.TEXT,
                text=reply,
                attachments=[],
                idempotency_key=row.id,
            )
            db.add(message)
            await db.flush()
            outbox = BotOutboundLog(
                bot_id=chat.bot_id,
                request_id=row.id,
                command="send_message",
                payload={
                    "internal_id": message.id,
                    "contact": {"telegram_user_id": contact.telegram_user_id},
                    "message": {"text": reply},
                    "attachments": [],
                    "ai_request_id": row.id,
                },
            )
            db.add(outbox)
            row.status = "outbox"
            row.meta = {**row.meta, "message_id": message.id}
            chat.last_message_preview, chat.last_message_at = (
                reply[:200],
                datetime.now(UTC).replace(tzinfo=None),
            )
            if row.body["mode"] == "fallback":
                state.data = {**state.data, "fallback_done": True}
        await db.commit()
        await publish_notices(db)


async def dispatch_pending() -> None:
    from app.modules.db.models.bot_outbound_log import BotOutboundLog
    from app.modules.db.models.enums import BotOutboundStatus
    from app.shared.db import get_session_factory
    from app.workers.bots.dispatch_outbound import dispatch_outbound_command

    async with get_session_factory()() as db:
        ids = list(
            await db.scalars(
                select(BotOutboundLog.id)
                .where(
                    BotOutboundLog.request_id.like("crm-chat-%"),
                    BotOutboundLog.status == BotOutboundStatus.QUEUED,
                )
                .limit(8)
            )
        )
    for log_id in ids:
        from sqlalchemy import text

        from app.shared.db import get_engine

        async with get_engine().connect() as lock:
            key = "ai-outbox:" + str(log_id)
            acquired = await lock.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key,0))"), {"key": key}
            )
            await lock.commit()
            if not acquired:
                continue
            try:
                await dispatch_outbound_command("dispatch_outbound", {"outbound_log_id": log_id})
            finally:
                await lock.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key,0))"), {"key": key}
                )
                await lock.commit()
