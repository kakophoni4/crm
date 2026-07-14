from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBotError(RuntimeError):
    def __init__(self, message: str, *, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = response or {}


async def telegram_call(
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    url = _API.format(token=token, method=method)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload or {})
    try:
        data = response.json()
    except Exception as exc:
        raise TelegramBotError(f"Invalid Telegram response ({response.status_code})") from exc
    if not data.get("ok"):
        desc = data.get("description") or response.text
        raise TelegramBotError(str(desc), response=data)
    result = data.get("result")
    return result if isinstance(result, dict) else {"result": result}


async def get_me(token: str) -> dict[str, Any]:
    return await telegram_call(token, "getMe")


async def set_webhook(token: str, url: str, secret_token: str) -> dict[str, Any]:
    return await telegram_call(
        token,
        "setWebhook",
        {
            "url": url,
            "secret_token": secret_token,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        },
    )


async def delete_webhook(token: str) -> dict[str, Any]:
    return await telegram_call(token, "deleteWebhook", {"drop_pending_updates": False})


async def send_message(
    token: str,
    *,
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = "HTML",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await telegram_call(token, "sendMessage", payload)


async def delete_message(token: str, *, chat_id: int, message_id: int) -> None:
    try:
        await telegram_call(
            token,
            "deleteMessage",
            {"chat_id": chat_id, "message_id": message_id},
        )
    except TelegramBotError as exc:
        logger.info(
            "telegram_delete_message_failed",
            chat_id=chat_id,
            message_id=message_id,
            error=str(exc),
        )


async def answer_callback_query(
    token: str,
    *,
    callback_query_id: str,
    text: str | None = None,
) -> None:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        await telegram_call(token, "answerCallbackQuery", payload)
    except TelegramBotError as exc:
        logger.info("telegram_answer_callback_failed", error=str(exc))
