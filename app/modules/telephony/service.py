from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.department import Department
from app.modules.db.models.enums import UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, visible_department_ids, visible_group_ids
from app.modules.telephony.repository import TelephonyAccountRepository, TelephonyAccountRow
from app.modules.telephony.schemas import (
    TelephonyAccountCreateRequest,
    TelephonyAccountListResponse,
    TelephonyAccountResponse,
    TelephonyAccountUpdateRequest,
    TelephonyWebrtcConfigResponse,
)
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _to_response(row: TelephonyAccountRow) -> TelephonyAccountResponse:
    account = row.account
    return TelephonyAccountResponse(
        id=account.id,
        name=account.name,
        provider=account.provider,
        department_id=account.department_id,
        department_name=row.department_name,
        group_id=account.group_id,
        group_name=row.group_name,
        sip_host=account.sip_host,
        sip_port=account.sip_port,
        sip_transport=account.sip_transport,
        sip_username=account.sip_username,
        has_sip_password=bool(account.sip_password_encrypted),
        outbound_caller_id=account.outbound_caller_id,
        pbx_extension_prefix=account.pbx_extension_prefix,
        webrtc_ws_url=account.webrtc_ws_url,
        is_active=account.is_active,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _sip_domain(account_host: str) -> str:
    return account_host.split(":", 1)[0]


class TelephonyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TelephonyAccountRepository(session)

    async def _scope(self, actor: User) -> tuple[set[int] | str, set[int] | str]:
        ctx = await ScopeLoader(self._session).load(actor)
        return visible_department_ids(ctx), visible_group_ids(ctx)

    async def _ensure_department_visible(self, actor: User, department_id: int) -> None:
        departments, _groups = await self._scope(actor)
        if departments == SCOPE_ALL:
            return
        if department_id not in set(departments):
            raise NotFound(message="Telephony account not found")

    async def _ensure_group_visible(self, actor: User, group_id: int | None) -> None:
        if group_id is None:
            return
        _departments, groups = await self._scope(actor)
        if groups == SCOPE_ALL:
            return
        if group_id not in set(groups):
            raise NotFound(message="Telephony account not found")

    async def _ensure_manager(self, actor: User, department_id: int) -> None:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            return
        if role == UserRole.SENIOR and actor.department_id == department_id:
            return
        raise PermissionDenied(message="Insufficient permissions")

    async def _validate_department(self, department_id: int) -> None:
        exists = await self._session.get(Department, department_id)
        if exists is None:
            raise ValidationError(message="department_id not found")

    async def _validate_group(self, department_id: int, group_id: int | None) -> None:
        if group_id is None:
            return
        result = await self._session.execute(
            select(Group.department_id).where(Group.id == group_id),
        )
        group_department_id = result.scalar_one_or_none()
        if group_department_id is None:
            raise ValidationError(message="group_id not found")
        if int(group_department_id) != department_id:
            raise ValidationError(message="group_id must belong to account department")

    async def list_accounts(self, actor: User) -> TelephonyAccountListResponse:
        departments, groups = await self._scope(actor)
        rows = await self._repo.list_with_meta()
        if departments != SCOPE_ALL:
            dept_set = set(departments)
            rows = [row for row in rows if row.account.department_id in dept_set]
        if groups != SCOPE_ALL:
            group_set = set(groups)
            rows = [
                row
                for row in rows
                if row.account.group_id is None or row.account.group_id in group_set
            ]
        return TelephonyAccountListResponse(items=[_to_response(row) for row in rows])

    async def get_account(self, account_id: int, actor: User) -> TelephonyAccountResponse:
        row = await self._repo.get_with_meta(account_id)
        if row is None:
            raise NotFound(message="Telephony account not found")
        await self._ensure_department_visible(actor, row.account.department_id)
        await self._ensure_group_visible(actor, row.account.group_id)
        return _to_response(row)

    async def create_account(
        self,
        actor: User,
        body: TelephonyAccountCreateRequest,
    ) -> TelephonyAccountResponse:
        await self._ensure_manager(actor, body.department_id)
        await self._validate_department(body.department_id)
        await self._validate_group(body.department_id, body.group_id)
        account = await self._repo.create(
            name=body.name.strip(),
            provider=body.provider.strip().lower(),
            department_id=body.department_id,
            group_id=body.group_id,
            sip_host=body.sip_host.strip(),
            sip_port=body.sip_port,
            sip_transport=body.sip_transport.lower(),
            sip_username=body.sip_username.strip(),
            sip_password=body.sip_password,
            outbound_caller_id=_clean(body.outbound_caller_id),
            pbx_extension_prefix=_clean(body.pbx_extension_prefix),
            webrtc_ws_url=_clean(body.webrtc_ws_url),
        )
        await self._session.commit()
        row = await self._repo.get_with_meta(account.id)
        assert row is not None
        return _to_response(row)

    async def update_account(
        self,
        account_id: int,
        actor: User,
        body: TelephonyAccountUpdateRequest,
    ) -> TelephonyAccountResponse:
        account = await self._repo.get(account_id)
        if account is None:
            raise NotFound(message="Telephony account not found")
        await self._ensure_manager(actor, account.department_id)

        if body.group_id is not None:
            await self._validate_group(account.department_id, body.group_id)
            account.group_id = body.group_id
        if body.name is not None:
            account.name = body.name.strip()
        if body.sip_host is not None:
            account.sip_host = body.sip_host.strip()
        if body.sip_port is not None:
            account.sip_port = body.sip_port
        if body.sip_transport is not None:
            account.sip_transport = body.sip_transport.lower()
        if body.sip_username is not None:
            account.sip_username = body.sip_username.strip()
        if body.sip_password is not None:
            await self._repo.set_password(account, body.sip_password)
        if body.outbound_caller_id is not None:
            account.outbound_caller_id = _clean(body.outbound_caller_id)
        if body.pbx_extension_prefix is not None:
            account.pbx_extension_prefix = _clean(body.pbx_extension_prefix)
        if body.webrtc_ws_url is not None:
            account.webrtc_ws_url = _clean(body.webrtc_ws_url)
        if body.is_active is not None:
            account.is_active = body.is_active

        await self._session.flush()
        await self._session.commit()
        row = await self._repo.get_with_meta(account.id)
        assert row is not None
        return _to_response(row)

    async def deactivate_account(
        self,
        account_id: int,
        actor: User,
    ) -> TelephonyAccountResponse:
        account = await self._repo.get(account_id)
        if account is None:
            raise NotFound(message="Telephony account not found")
        await self._ensure_manager(actor, account.department_id)
        account.is_active = False
        await self._session.commit()
        row = await self._repo.get_with_meta(account.id)
        assert row is not None
        return _to_response(row)

    async def get_webrtc_config(
        self,
        account_id: int,
        actor: User,
    ) -> TelephonyWebrtcConfigResponse:
        row = await self._repo.get_with_meta(account_id)
        if row is None or not row.account.is_active:
            raise NotFound(message="Telephony account not found")
        account = row.account
        await self._ensure_department_visible(actor, account.department_id)
        await self._ensure_group_visible(actor, account.group_id)

        extension = await self._repo.get_extension(account_id=account.id, user_id=actor.id)
        extension_created = False
        if extension is None:
            extension_value = await self._next_extension(
                account.id,
                actor.id,
                account.pbx_extension_prefix,
            )
            extension_password = secrets.token_urlsafe(24)
            display_name = actor.full_name or actor.username or actor.email
            extension = await self._repo.create_extension(
                account_id=account.id,
                user_id=actor.id,
                extension=extension_value,
                password=extension_password,
                display_name=display_name,
            )
            await self._session.commit()
            extension_created = True
        else:
            extension_password = await self._repo.decrypt_extension_password(extension)

        domain = _sip_domain(account.sip_host)
        return TelephonyWebrtcConfigResponse(
            account_id=account.id,
            account_name=account.name,
            extension=extension.extension,
            extension_password=extension_password,
            extension_created=extension_created,
            display_name=extension.display_name,
            sip_uri=f"sip:{extension.extension}@{domain}",
            ws_url=account.webrtc_ws_url or "ws://127.0.0.1:8088/ws",
            outbound_caller_id=account.outbound_caller_id,
            ice_servers=[],
        )

    async def _next_extension(
        self,
        account_id: int,
        user_id: int,
        prefix: str | None,
    ) -> str:
        clean_prefix = "".join(ch for ch in (prefix or "7") if ch.isdigit()) or "7"
        base = f"{clean_prefix}{user_id:04d}"
        if not await self._repo.extension_exists(account_id=account_id, extension=base):
            return base
        for suffix in range(1, 100):
            candidate = f"{base}{suffix:02d}"
            if not await self._repo.extension_exists(account_id=account_id, extension=candidate):
                return candidate
        raise ValidationError(message="Could not allocate telephony extension")
