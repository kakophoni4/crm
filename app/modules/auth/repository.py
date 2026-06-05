from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.refresh_token import RefreshToken
from app.modules.db.models.user import User
from app.shared.redis import get_redis

_REDIS_REVOKED_PREFIX = "auth:refresh:revoked:"


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_login(self, login_value: str) -> User | None:
        stmt = select(User).where(
            or_(User.username == login_value, User.email == login_value),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def create_refresh_token(
        self,
        user_id: int,
        jti: str,
        expires_at: datetime,
        *,
        refresh_token: str,
    ) -> RefreshToken:
        row = RefreshToken(
            user_id=user_id,
            jti=jti,
            refresh_token_hash=self.hash_refresh_token(refresh_token),
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def revoke_refresh_token(self, jti: str) -> None:
        now = datetime.now(UTC)
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now),
        )

        stmt = select(RefreshToken.expires_at).where(RefreshToken.jti == jti)
        result = await self._session.execute(stmt)
        expires_at = result.scalar_one_or_none()
        if expires_at is not None:
            ttl_seconds = max(int((expires_at - now).total_seconds()), 1)
            redis = get_redis()
            await redis.setex(f"{_REDIS_REVOKED_PREFIX}{jti}", ttl_seconds, b"1")

    async def revoke_all_refresh_tokens_for_user(self, user_id: int) -> None:
        now = datetime.now(UTC)
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now),
        )

    async def is_refresh_revoked(self, jti: str) -> bool:
        redis = get_redis()
        cached = await redis.get(f"{_REDIS_REVOKED_PREFIX}{jti}")
        if cached is not None:
            return True

        stmt = select(RefreshToken.revoked_at).where(RefreshToken.jti == jti)
        result = await self._session.execute(stmt)
        revoked_at = result.scalar_one_or_none()
        return revoked_at is not None
