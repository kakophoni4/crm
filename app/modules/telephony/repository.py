from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.crypto import decrypt_secret, encrypt_secret
from app.modules.db.models.department import Department
from app.modules.db.models.group import Group
from app.modules.db.models.telephony_account import TelephonyAccount
from app.modules.db.models.telephony_extension import TelephonyExtension


@dataclass(frozen=True)
class TelephonyAccountRow:
    account: TelephonyAccount
    department_name: str | None
    group_name: str | None


class TelephonyAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_with_meta(self) -> list[TelephonyAccountRow]:
        result = await self._session.execute(
            select(TelephonyAccount, Department.name, Group.name)
            .join(Department, Department.id == TelephonyAccount.department_id)
            .outerjoin(Group, Group.id == TelephonyAccount.group_id)
            .order_by(TelephonyAccount.name),
        )
        return [
            TelephonyAccountRow(
                account=row[0],
                department_name=row[1],
                group_name=row[2],
            )
            for row in result.all()
        ]

    async def get(self, account_id: int) -> TelephonyAccount | None:
        return await self._session.get(TelephonyAccount, account_id)

    async def get_with_meta(self, account_id: int) -> TelephonyAccountRow | None:
        result = await self._session.execute(
            select(TelephonyAccount, Department.name, Group.name)
            .join(Department, Department.id == TelephonyAccount.department_id)
            .outerjoin(Group, Group.id == TelephonyAccount.group_id)
            .where(TelephonyAccount.id == account_id),
        )
        row = result.one_or_none()
        if row is None:
            return None
        return TelephonyAccountRow(account=row[0], department_name=row[1], group_name=row[2])

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
