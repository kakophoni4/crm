from __future__ import annotations

import re
import secrets
import string

CODE_ALPHABET = string.ascii_lowercase
CODE_LENGTH = 16
_BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def generate_referral_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_ref_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.lower().startswith("/start"):
        rest = text[6:].strip()
        if rest.startswith("@"):
            parts = rest.split(None, 1)
            rest = parts[1] if len(parts) > 1 else ""
        text = rest.split()[0] if rest else ""
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in "_-")
    if not cleaned:
        return None
    return cleaned.lower()[:64]


def extract_ref_code(inner: dict[str, object] | None) -> str | None:
    payload = inner or {}
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    dedicated = (
        ("ref_code" in contact, contact.get("ref_code")),
        ("referral_code" in contact, contact.get("referral_code")),
        ("ref_code" in payload, payload.get("ref_code")),
        ("referral_code" in payload, payload.get("referral_code")),
    )
    for present, value in dedicated:
        if present:
            return normalize_ref_code(None if value is None else str(value))
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    text = message.get("text")
    if text is None:
        return None
    raw = str(text).strip()
    if not raw.lower().startswith("/start"):
        return None
    return normalize_ref_code(raw)


def normalize_bot_username(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lstrip("@")
    if not value:
        return None
    if _BOT_USERNAME_RE.fullmatch(value) is None:
        raise ValueError("Некорректный username Telegram-бота")
    return value


def build_referral_url(telegram_username: str | None, code: str) -> str | None:
    username = normalize_bot_username(telegram_username) if telegram_username else None
    if not username or not code:
        return None
    return f"https://t.me/{username}?start={code}"
