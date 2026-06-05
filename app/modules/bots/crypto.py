from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.settings import get_settings


async def encrypt_secret(session: AsyncSession, secret: str) -> bytes:
    key = get_settings().pgcrypto_key
    result = await session.execute(
        text("SELECT pgp_sym_encrypt(:secret, :key)"),
        {"secret": secret, "key": key},
    )
    value = result.scalar_one()
    if isinstance(value, memoryview):
        return bytes(value)
    return bytes(value)


async def decrypt_secret(session: AsyncSession, encrypted: bytes) -> str:
    key = get_settings().pgcrypto_key
    result = await session.execute(
        text("SELECT pgp_sym_decrypt(:enc, :key)"),
        {"enc": encrypted, "key": key},
    )
    value = result.scalar_one()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
