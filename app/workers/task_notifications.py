"""Send only the two generic texts explicitly authorized for staff Telegram."""
import asyncio
import json
from datetime import timezone
from sqlalchemy import text
from app.shared.db import get_session_factory
from app.modules.notifications.service import get_bot_token, _links_for_user
from app.modules.notifications import telegram_api
import structlog
logger = structlog.get_logger(__name__)

NOTIFICATION_TEXT = {'assigned': 'Вам поставлена задача', 'overdue': 'У вас просрочена задача'}

async def enqueue_overdue():
    async with get_session_factory()() as db:
        await db.execute(text("""INSERT INTO task_notification_outbox(task_id,user_id,kind,due_at,event_key)
            SELECT id, assignee_id, 'overdue', due_at,
                'overdue:' || id::text || ':' || assignee_id::text || ':' || extract(epoch FROM due_at)::text
            FROM department_tasks WHERE due_at < now() AND status IN ('new','open')
            ON CONFLICT(event_key) DO NOTHING"""))
        await db.commit()

async def deliver_one():
    async with get_session_factory()() as db:
        row = (await db.execute(text("""SELECT * FROM task_notification_outbox
            WHERE status IN ('pending','waiting','failed') AND next_attempt_at <= now()
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"""))).mappings().first()
        if row is None: return False
        task = (await db.execute(text('SELECT assignee_id,status,due_at FROM department_tasks WHERE id=:id'), {'id':row['task_id']})).mappings().one()
        user_status = (await db.execute(text('SELECT status FROM users WHERE id=:id'), {'id':row['user_id']})).scalar()
        state, error = 'sent', None
        delivered = list(row['delivered_to'] or [])
        deadline = task['due_at']
        if deadline is not None and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        stale = (row['kind'] == 'overdue' and (deadline != row['due_at'] or task['status'] not in ('new','open')))
        if stale or task['assignee_id'] != row['user_id'] or task['status'] in ('closed','deleted') or user_status != 'active':
            state = 'cancelled'
        else:
            token = await get_bot_token(db)
            links = await _links_for_user(db, row['user_id'])
            if not token or not links:
                state, error = 'waiting', 'telegram_not_connected'
            else:
                for link in links:
                    if link.telegram_user_id in delivered: continue
                    try:
                        await telegram_api.send_message(token, chat_id=link.telegram_user_id,
                            text=NOTIFICATION_TEXT[row['kind']], parse_mode=None)
                        delivered.append(link.telegram_user_id)
                    except Exception as exc:
                        state, error = 'failed', type(exc).__name__
                        break
        await db.execute(text("""UPDATE task_notification_outbox SET status=:status,
            error_code=:error, attempts=attempts+1, delivered_to=CAST(:delivered AS jsonb),
            next_attempt_at=now()+interval '5 minutes' WHERE id=:id"""),
            {'status':state, 'error':error, 'delivered':json.dumps(delivered), 'id':row['id']})
        await db.commit()
        return True

async def task_notification_loop():
    while True:
        try:
            await enqueue_overdue()
            for _ in range(20):
                if not await deliver_one(): break
        except Exception as exc:
            logger.warning('task_notification_worker_error', error_type=type(exc).__name__)
        await asyncio.sleep(15)
