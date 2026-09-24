"""Global Telegram blocking through the signed bridge outbox; no unblock operation."""
from sqlalchemy import select
from pydantic import BaseModel, Field
from app.modules.chats.repository import ChatRepository
from app.modules.chats.scope import can_view_chat_async
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.contact import Contact
from app.modules.db.models.bot import Bot
from app.modules.db.models.bot_outbound_log import BotOutboundLog
from app.modules.db.models.enums import BotOutboundStatus, AuditAction
from app.modules.bots.repository import BotOutboundLogRepository
from app.modules.audit.service import AuditService
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError
from app.shared.db import schedule_after_commit, get_session_factory
from app.shared.request_id import generate_ulid
from app.workers.bots.queue import enqueue


class BlockContactRequest(BaseModel):
    reason: str = Field(default='', max_length=500)


async def latest_block(db, telegram_id):
    return await db.scalar(select(BotOutboundLog).where(
        BotOutboundLog.command == 'block_contact',
        BotOutboundLog.payload['contact']['telegram_user_id'].astext == str(telegram_id),
    ).order_by(BotOutboundLog.id.desc()).limit(1))


def block_state(row):
    if row is None:
        return {'status': 'none'}
    state = 'blocked' if row.status == BotOutboundStatus.SENT else (
        'failed' if row.status == BotOutboundStatus.FAILED else 'pending')
    return {'status': state, 'requested_at': row.created_at.isoformat(),
            'operator': row.payload.get('operator', {}).get('name'),
            'reason': row.payload.get('reason', '')}


async def block_context(db, actor, chat_id):
    chat = await ChatRepository(db).get_by_id(chat_id)
    ctx = await ScopeLoader(db).load(actor)
    if chat is None or not await can_view_chat_async(db, ctx, chat):
        raise NotFound(message='Chat not found')
    bot = await db.get(Bot, chat.bot_id) if chat.bot_id else None
    contact = await db.get(Contact, chat.contact_id)
    return chat, bot, contact


async def block_status(db, actor, chat_id):
    _, bot, contact = await block_context(db, actor, chat_id)
    if not bot or bot.channel != 'telegram' or not contact or not contact.telegram_user_id:
        return {'status': 'unsupported'}
    return block_state(await latest_block(db, contact.telegram_user_id))


async def queue_block(log_id, bot_id):
    try:
        await enqueue('dispatch_outbound', {'outbound_log_id': log_id, 'bot_id': bot_id})
    except Exception:
        async with get_session_factory()() as db:
            row = await db.get(BotOutboundLog, log_id)
            if row and row.status == BotOutboundStatus.QUEUED:
                row.status = BotOutboundStatus.FAILED
                row.last_error = 'Block command could not be queued'
                await db.commit()


async def request_block(db, actor, chat_id, reason):
    chat, bot, contact = await block_context(db, actor, chat_id)
    if not bot or bot.channel != 'telegram' or not bot.is_active or not contact or not contact.telegram_user_id:
        raise ValidationError(message='Нужен активный Telegram-бот и Telegram ID контакта')
    takeover = await ChatRepository(db).get_active_takeover(chat_id)
    if takeover and takeover.senior_user_id != actor.id:
        raise PermissionDenied(message='Chat is under senior takeover')
    # Serialize repeated clicks and requests from different chats for the same contact.
    await db.scalar(select(Contact).where(Contact.id == contact.id).with_for_update())
    previous = await latest_block(db, contact.telegram_user_id)
    if previous and previous.status != BotOutboundStatus.FAILED:
        return block_state(previous)
    row = await BotOutboundLogRepository(db).create(
        bot_id=bot.id, request_id=generate_ulid(), command='block_contact',
        payload={'contact': {'telegram_user_id': contact.telegram_user_id},
                 'reason': reason.strip(), 'operator': {'id': actor.id, 'name': actor.full_name}},
    )
    await AuditService(db).write(actor_id=actor.id, action=AuditAction.CONTACT_UPDATE,
        entity_type='contact', entity_id=contact.id,
        payload={'action': 'telegram.block.requested', 'chat_id': chat.id,
                 'outbound_log_id': row.id, 'reason': reason.strip(), 'global': True})
    schedule_after_commit(db, lambda: queue_block(row.id, bot.id))
    return block_state(row)
