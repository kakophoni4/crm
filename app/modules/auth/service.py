from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    AuthUserSummary,
    LoginResponse,
    MeResponse,
    TokenPairResponse,
)
from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.user import User
from app.modules.rbac import ROLE_PERMISSIONS
from app.shared.exceptions import AppError, AuthenticationRequired
from app.shared.security.jwt import decode_token, encode_access, encode_refresh
from app.shared.security.passwords import verify_password
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

_INVALID_CREDENTIALS_MESSAGE = "Invalid username or password"


def mask_email_for_log(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    masked_local = "***" if len(local) <= 2 else f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AuthRepository(session)
        self._settings = get_settings()

    def _user_summary(self, user: User) -> AuthUserSummary:
        role = user.role if isinstance(user.role, UserRole) else UserRole(str(user.role))
        return AuthUserSummary(
            id=user.id,
            email=str(user.email),
            full_name=user.full_name,
            role=role,
        )

    def _expires_at(self, *, refresh: bool) -> datetime:
        ttl = (
            self._settings.jwt_refresh_ttl_seconds
            if refresh
            else self._settings.jwt_access_ttl_seconds
        )
        return datetime.now(UTC) + timedelta(seconds=ttl)

    async def _issue_tokens(self, user: User) -> tuple[str, str, str]:
        jti = str(uuid.uuid4())
        role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        access = encode_access(user.id, role, jti)
        refresh = encode_refresh(user.id, jti)
        await self._repo.create_refresh_token(
            user.id,
            jti,
            self._expires_at(refresh=True),
            refresh_token=refresh,
        )
        return access, refresh, jti

    async def login(self, username: str, password: str) -> LoginResponse:
        login_value = username.strip().lower()
        user = await self._repo.get_user_by_login(login_value)
        if user is None or not verify_password(password, user.password_hash):
            logger.warning(
                "auth_login_failed",
                login=mask_email_for_log(login_value),
            )
            raise AppError(
                code="invalid_credentials",
                message=_INVALID_CREDENTIALS_MESSAGE,
                status=401,
            )

        if user.status != UserStatus.ACTIVE:
            logger.warning(
                "auth_login_failed",
                login=mask_email_for_log(login_value),
                reason="inactive",
            )
            raise AppError(
                code="invalid_credentials",
                message=_INVALID_CREDENTIALS_MESSAGE,
                status=401,
            )

        access, refresh, _jti = await self._issue_tokens(user)
        await self._session.commit()

        logger.info("auth_login_success", user_id=user.id)
        return LoginResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.jwt_access_ttl_seconds,
            user=self._user_summary(user),
        )

    async def refresh(self, refresh_token: str) -> TokenPairResponse:
        payload = decode_token(refresh_token)
        if payload.get("typ") != "refresh":
            raise AppError(
                code="token_invalid",
                message="Invalid refresh token",
                status=401,
            )

        jti = str(payload["jti"])
        if await self._repo.is_refresh_revoked(jti):
            raise AppError(
                code="token_invalid",
                message="Refresh token has been revoked",
                status=401,
            )

        try:
            user_id = int(str(payload["sub"]))
        except (TypeError, ValueError) as exc:
            raise AppError(
                code="token_invalid",
                message="Invalid refresh token",
                status=401,
            ) from exc

        user = await self._repo.get_user_by_id(user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise AuthenticationRequired(message="Authentication required")

        await self._repo.revoke_refresh_token(jti)
        access, new_refresh, _new_jti = await self._issue_tokens(user)
        await self._session.commit()

        return TokenPairResponse(
            access_token=access,
            refresh_token=new_refresh,
            expires_in=self._settings.jwt_access_ttl_seconds,
        )

    async def logout(self, refresh_token: str) -> None:
        payload = decode_token(refresh_token)
        if payload.get("typ") != "refresh":
            raise AppError(
                code="token_invalid",
                message="Invalid refresh token",
                status=401,
            )

        await self._repo.revoke_refresh_token(str(payload["jti"]))
        await self._session.commit()
        logger.info("auth_logout", jti=str(payload["jti"]))

    async def me(self, user_id: int) -> MeResponse:
        user = await self._repo.get_user_by_id(user_id)
        if user is None:
            raise AuthenticationRequired(message="Authentication required")

        role = user.role if isinstance(user.role, UserRole) else UserRole(str(user.role))
        permissions = sorted(p.value for p in ROLE_PERMISSIONS[role])
        return MeResponse(
            id=user.id,
            email=str(user.email),
            full_name=user.full_name,
            role=role,
            department_id=user.department_id,
            group_id=user.group_id,
            presence=user.presence,
            permissions=permissions,
        )
