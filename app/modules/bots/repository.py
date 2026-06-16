from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.crypto import decrypt_secret, encrypt_secret
from app.modules.db.models.bot import Bot
from app.modules.db.models.bot_event_inbox import BotEventInbox
from app.modules.db.models.bot_outbound_log import BotOutboundLog
from app.modules.db.models.enums import BotChannel, BotOutboundStatus, BotOwnerType


@dataclass(frozen=True)
class BotListRow:
    bot: Bot
    department_name: str | None
    assigned_group_ids: list[int]
    assigned_group_names: list[str]


class BotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_bots_with_meta(self) -> list[BotListRow]:
        result = await self._session.execute(
            text(
                """
                SELECT
                    b.id,
                    d.name AS department_name,
                    COALESCE(
                        array_agg(bga.group_id ORDER BY g.name)
                            FILTER (WHERE bga.group_id IS NOT NULL),
                        '{}'
                    ) AS assigned_group_ids,
                    COALESCE(
                        array_agg(g.name ORDER BY g.name)
                            FILTER (WHERE g.id IS NOT NULL),
                        '{}'
                    ) AS assigned_group_names
                FROM bots b
                LEFT JOIN departments d ON d.id = b.department_id
                LEFT JOIN bot_group_assignments bga ON bga.bot_id = b.id
                LEFT JOIN groups g ON g.id = bga.group_id
                GROUP BY b.id, d.name
                ORDER BY b.code
                """
            ),
        )
        meta_by_id: dict[int, tuple[str | None, list[int], list[str]]] = {}
        for row in result.mappings():
            meta_by_id[int(row["id"])] = (
                row["department_name"],
                [int(gid) for gid in (row["assigned_group_ids"] or [])],
                [str(name) for name in (row["assigned_group_names"] or [])],
            )

        bots = await self.list_bots()
        rows: list[BotListRow] = []
        for bot in bots:
            department_name, group_ids, group_names = meta_by_id.get(
                bot.id,
                (None, [], []),
            )
            rows.append(
                BotListRow(
                    bot=bot,
                    department_name=department_name,
                    assigned_group_ids=group_ids,
                    assigned_group_names=group_names,
                ),
            )
        return rows

    async def list_bots(self) -> list[Bot]:
        result = await self._session.execute(select(Bot).order_by(Bot.code))
        return list(result.scalars().all())

    async def list_active_whatsapp_bots(self) -> list[Bot]:
        result = await self._session.execute(
            select(Bot).where(
                Bot.channel == BotChannel.WHATSAPP,
                Bot.is_active.is_(True),
                Bot.green_instance_id.isnot(None),
                Bot.green_api_token_encrypted.isnot(None),
            ).order_by(Bot.code),
        )
        return list(result.scalars().all())

    async def get_by_id(self, bot_id: int) -> Bot | None:
        return await self._session.get(Bot, bot_id)

    async def get_list_row(self, bot_id: int) -> BotListRow | None:
        bot = await self.get_by_id(bot_id)
        if bot is None:
            return None
        rows = await self.list_bots_with_meta()
        for row in rows:
            if row.bot.id == bot_id:
                return row
        return BotListRow(bot=bot, department_name=None, assigned_group_ids=[], assigned_group_names=[])

    async def get_by_code(self, code: str) -> Bot | None:
        result = await self._session.execute(select(Bot).where(Bot.code == code))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        code: str,
        name: str,
        department_id: int,
        owner_type: BotOwnerType,
        owner_id: int,
        outbound_url: str,
        health_url: str | None,
        ip_allowlist: list[str] | None,
        inbound_secret: str,
        outbound_secret: str,
        channel: BotChannel = BotChannel.TELEGRAM,
        green_api_url: str | None = None,
        green_media_url: str | None = None,
        green_instance_id: str | None = None,
        green_api_token_encrypted: bytes | None = None,
    ) -> Bot:
        inbound_enc = await encrypt_secret(self._session, inbound_secret)
        outbound_enc = await encrypt_secret(self._session, outbound_secret)
        bot = Bot(
            code=code,
            name=name,
            channel=channel,
            department_id=department_id,
            owner_type=owner_type,
            owner_id=owner_id,
            outbound_url=outbound_url,
            health_url=health_url,
            ip_allowlist=ip_allowlist,
            inbound_secret_encrypted=inbound_enc,
            outbound_secret_encrypted=outbound_enc,
            green_api_url=green_api_url,
            green_media_url=green_media_url,
            green_instance_id=green_instance_id,
            green_api_token_encrypted=green_api_token_encrypted,
        )
        self._session.add(bot)
        await self._session.flush()
        return bot

    async def save(self, bot: Bot) -> Bot:
        await self._session.flush()
        return bot

    async def decrypt_inbound_secret(self, bot: Bot) -> str:
        return await decrypt_secret(self._session, bot.inbound_secret_encrypted)

    async def decrypt_outbound_secret(self, bot: Bot) -> str:
        return await decrypt_secret(self._session, bot.outbound_secret_encrypted)

    async def decrypt_green_api_token(self, bot: Bot) -> str:
        if bot.green_api_token_encrypted is None:
            raise ValueError("green api token is not configured")
        return await decrypt_secret(self._session, bot.green_api_token_encrypted)

    async def encrypt_green_api_token(self, token: str) -> bytes:
        return await encrypt_secret(self._session, token)

    async def rotate_secret(self, bot: Bot, kind: str, new_secret: str) -> None:
        encrypted = await encrypt_secret(self._session, new_secret)
        if kind == "inbound":
            bot.inbound_secret_encrypted = encrypted
        else:
            bot.outbound_secret_encrypted = encrypted
        await self._session.flush()

    async def owner_exists(self, owner_type: BotOwnerType, owner_id: int) -> bool:
        table = "departments" if owner_type == BotOwnerType.DEPARTMENT else "groups"
        result = await self._session.execute(
            text(f"SELECT 1 FROM {table} WHERE id = :oid LIMIT 1"),
            {"oid": owner_id},
        )
        return result.scalar_one_or_none() is not None

    async def department_exists(self, department_id: int) -> bool:
        result = await self._session.execute(
            text("SELECT 1 FROM departments WHERE id = :did LIMIT 1"),
            {"did": department_id},
        )
        return result.scalar_one_or_none() is not None

    async def list_assigned_group_ids(self, bot_id: int) -> list[int]:
        result = await self._session.execute(
            text(
                """
                SELECT group_id
                FROM bot_group_assignments
                WHERE bot_id = :bid
                ORDER BY group_id
                """
            ),
            {"bid": bot_id},
        )
        return [int(row[0]) for row in result.all()]

    async def replace_group_assignments(self, bot_id: int, group_ids: list[int]) -> None:
        await self._session.execute(
            text("DELETE FROM bot_group_assignments WHERE bot_id = :bid"),
            {"bid": bot_id},
        )
        for group_id in group_ids:
            await self._session.execute(
                text(
                    """
                    INSERT INTO bot_group_assignments (bot_id, group_id)
                    VALUES (:bid, :gid)
                    """
                ),
                {"bid": bot_id, "gid": group_id},
            )
        await self._session.flush()

    async def groups_in_department(self, group_ids: list[int], department_id: int) -> list[int]:
        if not group_ids:
            return []
        stmt = text(
            """
            SELECT id FROM groups
            WHERE department_id = :did AND id IN :gids
            ORDER BY id
            """
        ).bindparams(bindparam("gids", expanding=True))
        result = await self._session.execute(
            stmt,
            {"did": department_id, "gids": group_ids},
        )
        return [int(row[0]) for row in result.all()]

    async def sync_chats_after_group_assignment(
        self,
        bot_id: int,
        department_id: int,
        group_ids: list[int],
    ) -> None:
        if len(group_ids) == 1:
            group_id = group_ids[0]
            await self._session.execute(
                text(
                    """
                    INSERT INTO contact_group_assignments (
                        contact_id, group_id, owner_user_id, assigned_at, assignment_source
                    )
                    SELECT DISTINCT
                        c.contact_id,
                        :new_gid,
                        old_cga.owner_user_id,
                        now(),
                        'migration'
                    FROM chats c
                    JOIN contact_group_assignments old_cga
                      ON old_cga.contact_id = c.contact_id
                     AND old_cga.group_id = c.assigned_group_id
                     AND old_cga.owner_user_id IS NOT NULL
                    LEFT JOIN contact_group_assignments new_cga
                      ON new_cga.contact_id = c.contact_id
                     AND new_cga.group_id = :new_gid
                    WHERE c.bot_id = :bid
                      AND c.status != 'archived'
                      AND c.assigned_group_id IS DISTINCT FROM :new_gid
                      AND new_cga.id IS NULL
                    ON CONFLICT (contact_id, group_id) DO NOTHING
                    """
                ),
                {"new_gid": group_id, "bid": bot_id},
            )
            await self._session.execute(
                text(
                    """
                    UPDATE chats
                    SET assigned_group_id = :gid,
                        assigned_department_id = :did,
                        updated_at = now()
                    WHERE bot_id = :bid AND status != 'archived'
                    """
                ),
                {"gid": group_id, "did": department_id, "bid": bot_id},
            )
        else:
            await self._session.execute(
                text(
                    """
                    UPDATE chats
                    SET assigned_group_id = NULL,
                        assigned_department_id = :did,
                        updated_at = now()
                    WHERE bot_id = :bid AND status != 'archived'
                    """
                ),
                {"did": department_id, "bid": bot_id},
            )
        await self._session.flush()


class BotEventInboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_event_id(self, event_id: str) -> BotEventInbox | None:
        result = await self._session.execute(
            select(BotEventInbox).where(BotEventInbox.event_id == event_id),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        bot_id: int,
        event_id: str,
        payload: dict[str, Any],
        signature: str,
    ) -> BotEventInbox:
        row = BotEventInbox(
            bot_id=bot_id,
            event_id=event_id,
            payload=payload,
            signature=signature,
            status="received",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_for_processing(self, event_id: str) -> BotEventInbox | None:
        return await self.get_by_event_id(event_id)

    async def mark_processing(self, row: BotEventInbox) -> None:
        row.status = "processing"
        await self._session.flush()

    async def mark_done(self, row: BotEventInbox) -> None:
        row.status = "done"
        row.processed_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_failed(self, row: BotEventInbox, error: str) -> None:
        row.status = "failed"
        row.last_error = error[:2000]
        row.processed_at = datetime.now(UTC)
        await self._session.flush()


class BotOutboundLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, log_id: int) -> BotOutboundLog | None:
        return await self._session.get(BotOutboundLog, log_id)

    async def get_by_request_id(self, request_id: str) -> BotOutboundLog | None:
        result = await self._session.execute(
            select(BotOutboundLog).where(BotOutboundLog.request_id == request_id),
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        bot_id: int,
        request_id: str,
        command: str,
        payload: dict[str, Any],
    ) -> BotOutboundLog:
        row = BotOutboundLog(
            bot_id=bot_id,
            request_id=request_id,
            command=command,
            payload=payload,
            status=BotOutboundStatus.QUEUED,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def save(self, row: BotOutboundLog) -> None:
        await self._session.flush()
