from __future__ import annotations

from typing import Any

import httpx

from app.shared.exceptions import AppError
from app.shared.settings import settings

_client: httpx.AsyncClient | None = None


def revision(value: Any) -> Any:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def write(
    method: Any, path: Any, *, body: Any = None, content: Any = None, params: Any = None
) -> Any:
    from sqlalchemy import text

    from app.shared.db import get_engine

    async with get_engine().connect() as lock:
        acquired = await lock.scalar(text("SELECT pg_try_advisory_lock(731819402)"))
        await lock.commit()
        if not acquired:
            raise AppError(
                "ai_admin_busy",
                "Другой администратор изменяет настройки. Обновите состояние и повторите.",
                409,
            )
        try:
            if method == "PUT" and path in ("connection", "catalog"):
                expected = (body or {}).pop("_crm_revision", None)
                _, current = await call("GET", path)
                if not expected or expected != revision(current):
                    raise AppError(
                        "ai_settings_changed",
                        "Настройки изменились. Обновите форму перед сохранением.",
                        409,
                    )
            return await call(method, path, body=body, content=content, params=params)
        finally:
            await lock.execute(text("SELECT pg_advisory_unlock(731819402)"))
            await lock.commit()


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def call(
    method: str,
    path: str,
    *,
    admin: bool = True,
    body: Any = None,
    content: Any = None,
    params: Any = None,
) -> Any:
    global _client
    key = settings.ai_service_admin_key if admin else settings.ai_service_reply_key
    if not key.get_secret_value():
        raise AppError("ai_not_configured", "Ключ подключения ИИ не задан на сервере CRM", 503)
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(35, connect=10), trust_env=False, follow_redirects=False
        )
    try:
        response = await _client.request(
            method,
            settings.ai_service_base_url.rstrip("/") + "/v1/" + path,
            headers={
                "Authorization": "Bearer " + key.get_secret_value(),
                "Content-Type": "application/octet-stream"
                if content is not None
                else "application/json",
            },
            json=body,
            content=content,
            params=params,
        )
    except httpx.HTTPError:
        raise AppError(
            "ai_unreachable",
            (
                "ИИ API не ответил. Состояние операции может быть неопределённым; "
                "проверьте список задач перед повтором."
            ),
            503,
        ) from None
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        code = str(error.get("code", "ai_service_error"))
        message = str(error.get("message", "Ошибка ИИ API"))[:2000]
        for secret in (settings.ai_service_reply_key, settings.ai_service_admin_key):
            if secret.get_secret_value():
                message = message.replace(secret.get_secret_value(), "[скрыто]")
        if response.status_code == 401:
            code, message = (
                "ai_key_invalid",
                "ИИ API отклонил ключ подключения. Сессия CRM остаётся активной.",
            )
        raise AppError(code, message, 502 if response.status_code == 401 else response.status_code)
    if response.status_code == 204:
        return response.status_code, None
    if path == "examples/export":
        return response.status_code, {
            "content": response.text,
            "next_after_id": response.headers.get("X-Next-After-Id"),
        }
    try:
        return response.status_code, response.json()
    except ValueError:
        raise AppError("ai_invalid_response", "ИИ API вернул некорректный ответ", 502) from None
