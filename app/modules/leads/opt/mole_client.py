from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.shared.exceptions import AppError
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)


class MoleApiError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="mole_api_error", message=message, status=502, details=details)


def _normalize_mole_status(raw: object) -> str:
    text = str(raw or "").strip().upper()
    return text.translate(str.maketrans({"О": "O", "К": "K", "о": "O", "к": "K"}))


async def post_opt_order(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    base = settings.mole_api_base_url.strip().rstrip("/")
    if not base:
        raise MoleApiError(message="Интеграция с 1С не настроена (MOLE_API_BASE_URL)")

    path = settings.mole_api_orders_path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    url = f"{base}{path}"

    auth: tuple[str, str] | None = None
    username = settings.mole_api_username.strip()
    password = settings.mole_api_password
    if username:
        auth = (username, password)

    timeout = httpx.Timeout(settings.mole_api_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, auth=auth)
    except httpx.HTTPError as exc:
        logger.warning("mole_api_transport_error", error=str(exc))
        raise MoleApiError(message="Не удалось связаться с 1С") from exc

    if response.status_code == 401:
        raise MoleApiError(
            message="1С отклонила авторизацию (проверьте MOLE_API_USERNAME / MOLE_API_PASSWORD)",
            details={"http_status": response.status_code},
        )

    try:
        body: dict[str, Any] = response.json()
    except ValueError as exc:
        raise MoleApiError(
            message="1С вернула некорректный ответ",
            details={"http_status": response.status_code, "text": response.text[:500]},
        ) from exc

    if response.status_code >= 400:
        raise MoleApiError(
            message="1С отклонила заявку",
            details={"http_status": response.status_code, "body": body},
        )

    status = _normalize_mole_status(body.get("Статус") or body.get("Status"))
    if status != "OK":
        raise MoleApiError(
            message="1С не подтвердила заявку (Статус != OK)",
            details={"body": body},
        )

    return body
