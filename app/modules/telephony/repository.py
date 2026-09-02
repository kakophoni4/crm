from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.crypto import decrypt_secret, encrypt_secret
from app.modules.db.models.department import Department
from app.modules.db.models.group import Group
from app.modules.db.models.telephony_account import TelephonyAccount
from app.modules.db.models.telephony_call import TelephonyCall
from app.modules.db.models.telephony_extension import TelephonyExtension
from app.modules.db.models.user import User


@dataclass(frozen=True)
class TelephonyAccountRow:
    account: TelephonyAccount
    department_name: str | None
    group_name: str | None
    group_ids: list[int]
    group_names: list[str]


@dataclass(frozen=True)
class TelephonyCallRow:
    call: TelephonyCall
    account_name: str
    user_name: str | None
    department_name: str | None
    group_name: str | None


class TelephonyAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_with_meta(self) -> list[TelephonyAccountRow]:
        result = await self._session.execute(
            text(
                """
                SELECT
                    ta.id,
                    d.name AS department_name,
                    legacy_group.name AS group_name,
                    COALESCE(
                        array_agg(taga.group_id ORDER BY g.name)
                            FILTER (WHERE taga.group_id IS NOT NULL),
                        '{}'
                    ) AS group_ids,
                    COALESCE(
                        array_agg(g.name ORDER BY g.name)
                            FILTER (WHERE g.id IS NOT NULL),
                        '{}'
                    ) AS group_names
                FROM telephony_accounts ta
                JOIN departments d ON d.id = ta.department_id
                LEFT JOIN groups legacy_group ON legacy_group.id = ta.group_id
                LEFT JOIN telephony_account_group_assignments taga ON taga.account_id = ta.id
                LEFT JOIN groups g ON g.id = taga.group_id
                GROUP BY ta.id, d.name, legacy_group.name
                ORDER BY ta.name
                """
            ),
        )
        meta_by_id: dict[int, tuple[str | None, str | None, list[int], list[str]]] = {}
        for row in result.mappings():
            meta_by_id[int(row["id"])] = (
                row["department_name"],
                row["group_name"],
                [int(gid) for gid in (row["group_ids"] or [])],
                [str(name) for name in (row["group_names"] or [])],
            )

        accounts_result = await self._session.execute(
            select(TelephonyAccount).order_by(TelephonyAccount.name),
        )
        accounts = list(accounts_result.scalars().all())
        return [
            TelephonyAccountRow(
                account=account,
                department_name=meta_by_id.get(account.id, (None, None, [], []))[0],
                group_name=meta_by_id.get(account.id, (None, None, [], []))[1],
                group_ids=meta_by_id.get(account.id, (None, None, [], []))[2],
                group_names=meta_by_id.get(account.id, (None, None, [], []))[3],
            )
            for account in accounts
        ]

    async def get(self, account_id: int) -> TelephonyAccount | None:
        return await self._session.get(TelephonyAccount, account_id)

    async def get_with_meta(self, account_id: int) -> TelephonyAccountRow | None:
        rows = await self.list_with_meta()
        for row in rows:
            if row.account.id == account_id:
                return row
        return None

    async def create(
        self,
        *,
        name: str,
        provider: str,
        department_id: int,
        group_id: int | None,
        sip_host: str,
        sip_port: int,
        sip_transport: str,
        sip_username: str,
        sip_password: str,
        outbound_caller_id: str | None,
        pbx_extension_prefix: str | None,
        webrtc_ws_url: str | None,
    ) -> TelephonyAccount:
        account = TelephonyAccount(
            name=name,
            provider=provider,
            department_id=department_id,
            group_id=group_id,
            sip_host=sip_host,
            sip_port=sip_port,
            sip_transport=sip_transport,
            sip_username=sip_username,
            sip_password_encrypted=await encrypt_secret(self._session, sip_password),
            outbound_caller_id=outbound_caller_id,
            pbx_extension_prefix=pbx_extension_prefix,
            webrtc_ws_url=webrtc_ws_url,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def replace_group_assignments(self, account_id: int, group_ids: list[int]) -> None:
        await self._session.execute(
            text("DELETE FROM telephony_account_group_assignments WHERE account_id = :aid"),
            {"aid": account_id},
        )
        for group_id in group_ids:
            await self._session.execute(
                text(
                    """
                    INSERT INTO telephony_account_group_assignments (account_id, group_id)
                    VALUES (:aid, :gid)
                    """
                ),
                {"aid": account_id, "gid": group_id},
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
        result = await self._session.execute(stmt, {"did": department_id, "gids": group_ids})
        return [int(row[0]) for row in result.all()]

    async def set_password(self, account: TelephonyAccount, password: str) -> None:
        account.sip_password_encrypted = await encrypt_secret(self._session, password)
        await self._session.flush()

    async def get_extension(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> TelephonyExtension | None:
        result = await self._session.execute(
            select(TelephonyExtension).where(
                TelephonyExtension.account_id == account_id,
                TelephonyExtension.user_id == user_id,
                TelephonyExtension.is_active.is_(True),
            ),
        )
        return result.scalar_one_or_none()

    async def extension_exists(self, *, account_id: int, extension: str) -> bool:
        result = await self._session.execute(
            select(TelephonyExtension.id).where(
                TelephonyExtension.account_id == account_id,
                TelephonyExtension.extension == extension,
            ),
        )
        return result.scalar_one_or_none() is not None

    async def create_extension(
        self,
        *,
        account_id: int,
        user_id: int,
        extension: str,
        password: str,
        display_name: str | None,
    ) -> TelephonyExtension:
        row = TelephonyExtension(
            account_id=account_id,
            user_id=user_id,
            extension=extension,
            password_encrypted=await encrypt_secret(self._session, password),
            display_name=display_name,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def decrypt_extension_password(self, extension: TelephonyExtension) -> str:
        return await decrypt_secret(self._session, extension.password_encrypted)

    async def create_call(
        self,
        *,
        account_id: int,
        user_id: int,
        department_id: int,
        group_id: int | None,
        phone_number: str,
    ) -> TelephonyCall:
        row = TelephonyCall(
            account_id=account_id,
            user_id=user_id,
            department_id=department_id,
            group_id=group_id,
            direction="outbound",
            phone_number=phone_number,
            status="calling",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_call(self, call_id: int) -> TelephonyCall | None:
        return await self._session.get(TelephonyCall, call_id)

    async def update_call_status(
        self,
        call: TelephonyCall,
        *,
        status: str,
        duration_seconds: int | None,
    ) -> None:
        call.status = status
        if duration_seconds is not None:
            call.duration_seconds = duration_seconds
        await self._session.execute(
            text(
                """
                UPDATE telephony_calls
                SET
                    status = :status,
                    duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                    answered_at = CASE
                        WHEN :status = 'answered' AND answered_at IS NULL THEN now()
                        ELSE answered_at
                    END,
                    ended_at = CASE
                        WHEN :status IN ('completed', 'failed') AND ended_at IS NULL THEN now()
                        ELSE ended_at
                    END,
                    updated_at = now()
                WHERE id = :call_id
                """
            ),
            {
                "call_id": call.id,
                "status": status,
                "duration_seconds": duration_seconds,
            },
        )
        await self._session.flush()

    async def list_calls(
        self,
        *,
        visible_user_ids: set[int] | str,
        department_ids: set[int] | str,
        limit: int,
    ) -> list[TelephonyCallRow]:
        stmt = (
            select(
                TelephonyCall,
                TelephonyAccount.name,
                User.full_name,
                Department.name,
                Group.name,
            )
            .select_from(TelephonyCall)
            .join(TelephonyAccount, TelephonyAccount.id == TelephonyCall.account_id)
            .join(User, User.id == TelephonyCall.user_id)
            .join(Department, Department.id == TelephonyCall.department_id)
            .outerjoin(Group, Group.id == TelephonyCall.group_id)
            .order_by(TelephonyCall.started_at.desc(), TelephonyCall.id.desc())
            .limit(limit)
        )
        if visible_user_ids != "ALL":
            stmt = stmt.where(TelephonyCall.user_id.in_(visible_user_ids))
        if department_ids != "ALL":
            stmt = stmt.where(TelephonyCall.department_id.in_(department_ids))
        result = await self._session.execute(stmt)
        rows: list[TelephonyCallRow] = []
        for call, account_name, user_name, department_name, group_name in result.all():
            rows.append(
                TelephonyCallRow(
                    call=call,
                    account_name=str(account_name),
                    user_name=str(user_name) if user_name is not None else None,
                    department_name=str(department_name) if department_name is not None else None,
                    group_name=str(group_name) if group_name is not None else None,
                )
            )
        return rows

    async def delete_all_calls(self) -> int:
        result = await self._session.execute(delete(TelephonyCall))
        await self._session.flush()
        return int(result.rowcount or 0)
