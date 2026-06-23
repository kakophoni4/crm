from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.crypto import decrypt_secret, encrypt_secret
from app.modules.db.models.telephony_account import TelephonyAccount
from app.modules.db.models.telephony_extension import TelephonyExtension


@dataclass(frozen=True)
class TelephonyAccountRow:
    account: TelephonyAccount
    department_name: str | None
    group_name: str | None
    group_ids: list[int]
    group_names: list[str]


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
