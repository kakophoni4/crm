from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.chats_bridge import (
    IngestResult,
    get_chat_current_lead_id,
    insert_inbound_message,
    insert_outbound_message,
    is_outbound_bot_message,
    update_contact_telegram_fields,
    update_inbound_message_edited,
    upsert_chat_for_bot,
    upsert_contact_from_phone,
    upsert_contact_from_telegram,
)
from app.modules.bots.ownership_bridge import handle_inbound_ownership
from app.modules.bots.repository import BotEventInboxRepository, BotRepository
from app.modules.bots.routing import resolve_bot_routing
from app.modules.contacts.realtime_payloads import contact_group_context
from app.modules.contacts.ownership import (
    clear_pending_inbound,
    ownership_v2_enabled,
    pick_group_among_candidates,
)
from app.modules.contacts.status_automation import apply_auto_contact_status
from app.modules.db.models.bot import Bot
from app.modules.db.models.chat import Chat
from app.modules.db.models.contact import Contact
from app.modules.db.models.department import Department
from app.modules.db.models.enums import BotOwnerType, UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.leads.department_inbox import get_or_create_department_inbox_group
from app.modules.leads.service import LeadService
from app.realtime.chat_scope import chat_event_scope
from app.realtime.events import publish
from app.shared.db import get_session_factory
from app.workers.bots.download_attachment import download_attachment


async def _resolve_ingest_group_id(
    session: Any,
    *,
    routing: Any,
    chat_assigned_group_id: int | None,
    created_by: int,
) -> int:
    """Real bot groups win over synthetic department inbox when any are assigned.

    Sticky: keep the chat on its current group only if that group is still one of
    the bot's assigned groups. Inbox / foreign / missing → pick among candidates
    (prefer groups with available staff). Inbox is used only when the bot has
    zero real groups.
    """
    candidates = [int(gid) for gid in (routing.candidate_group_ids or [])]
    if candidates:
        if chat_assigned_group_id is not None and int(chat_assigned_group_id) in candidates:
            return int(chat_assigned_group_id)
        picked = await pick_group_among_candidates(session, candidates)
        if picked is not None:
            return int(picked)
        return candidates[0]
    if chat_assigned_group_id is not None:
        return int(chat_assigned_group_id)
    return await get_or_create_department_inbox_group(
        session,
        routing.department_id,
        created_by=created_by,
    )


async def _ensure_chat_on_group(
    session: Any,
    *,
    chat_id: int,
    group_id: int,
    department_id: int,
    current_assigned_group_id: int | None,
) -> None:
    if current_assigned_group_id is not None and int(current_assigned_group_id) == int(group_id):
        return
    await session.execute(
        text(
            """
            UPDATE chats
            SET assigned_group_id = :gid,
                assigned_department_id = :did,
                updated_at = now()
            WHERE id = :chat_id
            """
        ),
        {
            "chat_id": chat_id,
            "gid": group_id,
            "did": department_id,
        },
    )

logger = structlog.get_logger(__name__)


async def _inbound_realtime_payload(
    session: AsyncSession,
    *,
    chat_id: int,
    contact_id: int,
    base: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(base)
    contact = await session.get(Contact, contact_id)
    if contact is not None:
        full_name = str(contact.full_name or "").strip()
        if full_name:
            payload["contact_full_name"] = full_name
            payload["contact_name"] = full_name
    chat = await session.get(Chat, chat_id)
    if chat is not None and chat.assigned_group_id is not None:
        group_ctx = await contact_group_context(
            session,
            contact_id,
            chat.assigned_group_id,
            include_chat_id=False,
        )
        for key in ("contact_full_name", "contact_name", "group_name"):
            value = group_ctx.get(key)
            if value and key not in payload:
                payload[key] = value
    return payload


async def process_bot_event(_job_type: str, payload: dict[str, Any]) -> None:
    event_id = str(payload.get("event_id", ""))
    if not event_id:
        return

    session_factory = get_session_factory()
    async with session_factory() as session:
        inbox_repo = BotEventInboxRepository(session)
        row = await inbox_repo.get_for_processing(event_id)
        if row is None:
            return
        if row.status == "done":
            return
        if row.status == "processing":
            return

        await inbox_repo.mark_processing(row)
        await session.commit()

        try:
            bot_repo = BotRepository(session)
            bot = await bot_repo.get_by_id(row.bot_id)
            if bot is None:
                raise RuntimeError("bot not found")

            envelope = row.payload
            event_type = str(envelope.get("event", ""))
            inner = envelope.get("payload") or {}

            if event_type == "message.received":
                result = await _handle_message_received(session, bot, envelope, inner)
                is_bot_outbound = is_outbound_bot_message(inner.get("message") or {})
                event_name = (
                    "chat.message.outbound.requested" if is_bot_outbound else "chat.message.inbound"
                )
                attachment_indices = (
                    list(result.attachment_indices) if not result.duplicate else []
                )
                publish_payload = {
                    "chat_id": result.chat_id,
                    "message_id": result.message_id,
                    "contact_id": result.contact_id,
                    "bot_code": bot.code,
                }
                if result.text_preview:
                    publish_payload["text_preview"] = result.text_preview
            elif event_type == "call.received":
                result = await _handle_call_received(session, bot, envelope, inner)
                call_scope = await chat_event_scope(session, result.chat_id)
                await publish(
                    "chat.call.inbound",
                    {
                        "chat_id": result.chat_id,
                        "message_id": result.message_id,
                        "contact_id": result.contact_id,
                        "bot_code": bot.code,
                    },
                    scope=call_scope or None,
                )
            elif event_type == "message.edited":
                await _handle_message_edited(session, bot, inner)
            elif event_type == "contact.updated":
                contact = inner
                await update_contact_telegram_fields(
                    session,
                    telegram_user_id=int(contact["telegram_user_id"]),
                    telegram_username=contact.get("telegram_username"),
                    first_name=contact.get("first_name"),
                    last_name=contact.get("last_name"),
                )
            else:
                logger.info("bot_event_ignored", event_type=event_type, event_id=event_id)

            await inbox_repo.mark_done(row)
            await session.commit()

            if event_type == "message.received":
                # Publish immediately so operators see text without waiting for file download.
                chat_scope = await chat_event_scope(session, result.chat_id)
                publish_payload = await _inbound_realtime_payload(
                    session,
                    chat_id=result.chat_id,
                    contact_id=result.contact_id,
                    base=publish_payload,
                )
                await publish(event_name, publish_payload, scope=chat_scope or None)
                for idx in attachment_indices:
                    await download_attachment(
                        "download_attachment",
                        {
                            "message_id": publish_payload["message_id"],
                            "attachment_index": idx,
                        },
                    )
        except Exception as exc:
            await session.rollback()
            async with session_factory() as fail_session:
                fail_row = await BotEventInboxRepository(fail_session).get_for_processing(event_id)
                if fail_row is not None:
                    await BotEventInboxRepository(fail_session).mark_failed(fail_row, str(exc))
                    await fail_session.commit()
            logger.exception("process_bot_event_failed", event_id=event_id)
            raise


async def _resolve_created_by(session: AsyncSession, bot: Bot) -> int:
    head: int | None = None
    routing = await resolve_bot_routing(session, bot)
    if routing.owner_type == BotOwnerType.GROUP:
        result = await session.execute(
            select(Department.head_user_id)
            .join(Group, Group.department_id == Department.id)
            .where(Group.id == routing.owner_id),
        )
        head = result.scalar_one_or_none()
    else:
        result = await session.execute(
            select(Department.head_user_id).where(Department.id == routing.department_id),
        )
        head = result.scalar_one_or_none()

    if head is not None:
        return int(head)

    admin_row = await session.execute(
        select(User.id).where(User.role == UserRole.ADMIN).order_by(User.id).limit(1),
    )
    admin_id = admin_row.scalar_one_or_none()
    if admin_id is None:
        raise RuntimeError("no admin user found in database")
    return int(admin_id)


async def _handle_message_received(
    session: Any,
    bot: Bot,
    envelope: dict[str, Any],
    inner: dict[str, Any],
) -> IngestResult:
    contact_data = inner["contact"]
    message_data = inner["message"]
    if is_outbound_bot_message(message_data):
        return await _handle_bot_outbound_message(session, bot, envelope, inner)

    created_by = await _resolve_created_by(session, bot)

    contact_id = await upsert_contact_from_telegram(
        session,
        telegram_user_id=int(contact_data["telegram_user_id"]),
        telegram_username=contact_data.get("telegram_username"),
        first_name=contact_data.get("first_name"),
        last_name=contact_data.get("last_name"),
        created_by=created_by,
    )
    routing = await resolve_bot_routing(session, bot)
    chat_result = await upsert_chat_for_bot(
        session,
        contact_id=contact_id,
        bot_id=bot.id,
        owner_type=routing.owner_type,
        owner_id=routing.owner_id,
        candidate_group_ids=routing.candidate_group_ids,
    )
    chat_id = chat_result.chat_id
    contact_row = await session.get(Contact, contact_id)
    if contact_row is not None:
        await apply_auto_contact_status(session, contact_row, bot_id=bot.id)
    lead_id: int | None = None
    group_id = await _resolve_ingest_group_id(
        session,
        routing=routing,
        chat_assigned_group_id=chat_result.assigned_group_id,
        created_by=created_by,
    )
    await _ensure_chat_on_group(
        session,
        chat_id=chat_id,
        group_id=group_id,
        department_id=routing.department_id,
        current_assigned_group_id=chat_result.assigned_group_id,
    )

    lead = await LeadService(session).ensure_open_lead(
        contact_id=contact_id,
        group_id=group_id,
        bot_id=bot.id,
        chat_id=chat_id,
    )
    lead_id = lead.id
    await handle_inbound_ownership(
        session,
        contact_id=contact_id,
        group_id=group_id,
        chat_id=chat_id,
        message_preview=str(message_data.get("text") or "")[:300] or None,
    )
    return await insert_inbound_message(
        session,
        chat_id=chat_id,
        lead_id=lead_id,
        text_body=message_data.get("text"),
        external_message_id=str(message_data["external_id"]),
        external_event_id=str(envelope.get("event_id", "")),
        attachments=list(message_data.get("attachments") or []),
        reply_to_external_id=message_data.get("reply_to_external_id"),
    )


def _call_text(call_data: dict[str, Any]) -> str:
    direction = str(call_data.get("direction") or "inbound")
    status = str(call_data.get("status") or "received")
    duration = call_data.get("duration_seconds")
    parts = [f"Bitcall {direction} call", f"status: {status}"]
    if duration is not None:
        parts.append(f"duration: {duration}s")
    if call_data.get("recording_url"):
        parts.append("recording attached")
    return "; ".join(parts)


async def _handle_call_received(
    session: Any,
    bot: Bot,
    envelope: dict[str, Any],
    inner: dict[str, Any],
) -> IngestResult:
    contact_data = inner["contact"]
    call_data = inner["call"]
    phone = str(contact_data.get("phone") or "").strip()
    if not phone:
        raise RuntimeError("Bitcall contact phone is required")

    created_by = await _resolve_created_by(session, bot)
    full_name = contact_data.get("full_name")
    if not full_name:
        full_name = " ".join(
            part for part in (contact_data.get("first_name"), contact_data.get("last_name")) if part
        )
    contact_id = await upsert_contact_from_phone(
        session,
        phone=phone,
        full_name=full_name,
        created_by=created_by,
    )
    routing = await resolve_bot_routing(session, bot)
    chat_result = await upsert_chat_for_bot(
        session,
        contact_id=contact_id,
        bot_id=bot.id,
        owner_type=routing.owner_type,
        owner_id=routing.owner_id,
        candidate_group_ids=routing.candidate_group_ids,
    )
    chat_id = chat_result.chat_id
    contact_row = await session.get(Contact, contact_id)
    if contact_row is not None:
        await apply_auto_contact_status(session, contact_row, bot_id=bot.id)
    group_id = await _resolve_ingest_group_id(
        session,
        routing=routing,
        chat_assigned_group_id=chat_result.assigned_group_id,
        created_by=created_by,
    )
    await _ensure_chat_on_group(
        session,
        chat_id=chat_id,
        group_id=group_id,
        department_id=routing.department_id,
        current_assigned_group_id=chat_result.assigned_group_id,
    )

    lead = await LeadService(session).ensure_open_lead(
        contact_id=contact_id,
        group_id=group_id,
        bot_id=bot.id,
        chat_id=chat_id,
    )
    await handle_inbound_ownership(
        session,
        contact_id=contact_id,
        group_id=group_id,
        chat_id=chat_id,
    )
    attachments: list[dict[str, Any]] = []
    if call_data.get("recording_url"):
        attachments.append(
            {
                "type": "voice",
                "url": call_data.get("recording_url"),
                "mime": call_data.get("recording_mime") or "audio/mpeg",
                "filename": call_data.get("recording_filename") or "bitcall-recording.mp3",
            },
        )
    return await insert_inbound_message(
        session,
        chat_id=chat_id,
        lead_id=lead.id,
        text_body=_call_text(call_data),
        external_message_id=str(call_data["external_id"]),
        external_event_id=str(envelope.get("event_id", "")),
        attachments=attachments,
        reply_to_external_id=None,
    )


async def _handle_bot_outbound_message(
    session: Any,
    bot: Bot,
    envelope: dict[str, Any],
    inner: dict[str, Any],
) -> IngestResult:
    contact_data = inner["contact"]
    message_data = inner["message"]
    created_by = await _resolve_created_by(session, bot)

    contact_id = await upsert_contact_from_telegram(
        session,
        telegram_user_id=int(contact_data["telegram_user_id"]),
        telegram_username=contact_data.get("telegram_username"),
        first_name=contact_data.get("first_name"),
        last_name=contact_data.get("last_name"),
        created_by=created_by,
    )
    routing = await resolve_bot_routing(session, bot)
    chat_result = await upsert_chat_for_bot(
        session,
        contact_id=contact_id,
        bot_id=bot.id,
        owner_type=routing.owner_type,
        owner_id=routing.owner_id,
        candidate_group_ids=routing.candidate_group_ids,
    )
    chat_id = chat_result.chat_id
    group_id = await _resolve_ingest_group_id(
        session,
        routing=routing,
        chat_assigned_group_id=chat_result.assigned_group_id,
        created_by=created_by,
    )
    await _ensure_chat_on_group(
        session,
        chat_id=chat_id,
        group_id=group_id,
        department_id=routing.department_id,
        current_assigned_group_id=chat_result.assigned_group_id,
    )
    lead_id = await get_chat_current_lead_id(session, chat_id)
    result = await insert_outbound_message(
        session,
        chat_id=chat_id,
        lead_id=lead_id,
        text_body=message_data.get("text"),
        external_message_id=str(message_data["external_id"]),
        external_event_id=str(envelope.get("event_id", "")),
        attachments=list(message_data.get("attachments") or []),
        reply_to_external_id=message_data.get("reply_to_external_id"),
    )
    if not result.duplicate and ownership_v2_enabled():
        await clear_pending_inbound(session, contact_id, group_id)
    return result


async def _handle_message_edited(session: Any, bot: Bot, inner: dict[str, Any]) -> None:
    message_data = inner.get("message") or inner
    await update_inbound_message_edited(
        session,
        bot_id=bot.id,
        external_message_id=str(message_data["external_id"]),
        text_body=message_data.get("text"),
    )
