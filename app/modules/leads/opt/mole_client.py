from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

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


def _orders_url_and_auth() -> tuple[str, tuple[str, str] | None, float]:
    settings = get_settings()
    base = settings.mole_api_base_url.strip().rstrip("/")
    if not base:
        raise MoleApiError(message="Интеграция с 1С не настроена (MOLE_API_BASE_URL)")

    path = settings.mole_api_orders_path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    url = f"{base}{path.rstrip('/')}"

    auth: tuple[str, str] | None = None
    username = settings.mole_api_username.strip()
    if username:
        auth = (username, settings.mole_api_password)

    return url, auth, float(settings.mole_api_timeout_seconds)


def _error_message_from_plain(text: str, *, http_status: int) -> str:
    cleaned = " ".join(text.strip().split())
    if cleaned:
        return cleaned[:500]
    return f"1С вернула некорректный ответ (HTTP {http_status})"


def _parse_json_or_raise(response: httpx.Response) -> Any:
    if response.status_code == 401:
        raise MoleApiError(
            message="1С отклонила авторизацию (проверьте MOLE_API_USERNAME / MOLE_API_PASSWORD)",
            details={"http_status": response.status_code},
        )
    try:
        return response.json()
    except ValueError as exc:
        text = response.text[:500]
        raise MoleApiError(
            message=_error_message_from_plain(text, http_status=response.status_code),
            details={"http_status": response.status_code, "text": text},
        ) from exc


def _require_ok_status(body: dict[str, Any]) -> dict[str, Any]:
    status = _normalize_mole_status(body.get("Статус") or body.get("Status"))
    if status and status != "OK":
        raise MoleApiError(
            message="1С не подтвердила заявку (Статус != OK)",
            details={"body": body},
        )
    return body


@dataclass
class MoleClient:
    """Reusable HTTP session for a batch of Mole calls (sync)."""

    client: httpx.AsyncClient
    orders_url: str

    async def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | list[Any] | None = None,
    ) -> httpx.Response:
        try:
            return await self.client.request(method, url, json=json_body)
        except httpx.HTTPError as exc:
            logger.warning("mole_api_transport_error", error=str(exc), method=method, url=url)
            raise MoleApiError(message="Не удалось связаться с 1С") from exc


_active_mole: MoleClient | None = None


@asynccontextmanager
async def mole_session() -> AsyncIterator[MoleClient]:
    """Share one httpx client across many Mole calls (avoids reconnect per order)."""
    global _active_mole
    orders_url, auth, timeout_s = _orders_url_and_auth()
    timeout = httpx.Timeout(timeout_s)
    async with httpx.AsyncClient(timeout=timeout, auth=auth) as client:
        session = MoleClient(client=client, orders_url=orders_url)
        prev = _active_mole
        _active_mole = session
        try:
            yield session
        finally:
            _active_mole = prev


async def _request(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | list[Any] | None = None,
) -> httpx.Response:
    if _active_mole is not None:
        return await _active_mole.request(method, url, json_body=json_body)

    _, auth, timeout_s = _orders_url_and_auth()
    timeout = httpx.Timeout(timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, json=json_body, auth=auth)
    except httpx.HTTPError as exc:
        logger.warning("mole_api_transport_error", error=str(exc), method=method, url=url)
        raise MoleApiError(message="Не удалось связаться с 1С") from exc


def _orders_url() -> str:
    if _active_mole is not None:
        return _active_mole.orders_url
    orders_url, _, _ = _orders_url_and_auth()
    return orders_url


async def post_opt_order(payload: dict[str, Any]) -> dict[str, Any]:
    orders_url = _orders_url()
    response = await _request("POST", orders_url, json_body=payload)
    body = _parse_json_or_raise(response)
    if not isinstance(body, dict):
        raise MoleApiError(
            message="1С вернула некорректный ответ",
            details={"http_status": response.status_code, "body": body},
        )
    if response.status_code >= 400:
        raise MoleApiError(
            message="1С отклонила заявку",
            details={"http_status": response.status_code, "body": body},
        )
    return _require_ok_status(body)


async def filter_orders(*, period_iso: str) -> list[dict[str, Any]]:
    """POST /hs/mole/orders/filter — list orders for period (ISO quarter start)."""
    orders_url = _orders_url()
    url = f"{orders_url}/filter"
    response = await _request("POST", url, json_body={"Период": period_iso})
    body = _parse_json_or_raise(response)
    if response.status_code >= 400:
        raise MoleApiError(
            message="1С отклонила фильтр заявок",
            details={"http_status": response.status_code, "body": body},
        )
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    if isinstance(body, dict):
        for key in ("Реестр", "Заявки", "items", "data"):
            nested = body.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
        if body.get("CRMid") or body.get("CrmId"):
            return [body]
    raise MoleApiError(
        message="1С вернула неожиданный формат списка заявок",
        details={"http_status": response.status_code, "body": body},
    )


async def get_order(crm_id: str) -> dict[str, Any]:
    orders_url = _orders_url()
    url = f"{orders_url}/{quote(crm_id, safe='')}"
    response = await _request("GET", url)
    body = _parse_json_or_raise(response)
    if response.status_code >= 400:
        raise MoleApiError(
            message="1С не вернула заявку",
            details={"http_status": response.status_code, "body": body},
        )
    if not isinstance(body, dict):
        raise MoleApiError(
            message="1С вернула некорректный ответ",
            details={"http_status": response.status_code, "body": body},
        )
    return body


async def put_order(crm_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    orders_url = _orders_url()
    url = f"{orders_url}/{quote(crm_id, safe='')}"
    response = await _request("PUT", url, json_body=payload)
    body = _parse_json_or_raise(response)
    if not isinstance(body, dict):
        raise MoleApiError(
            message="1С вернула некорректный ответ",
            details={"http_status": response.status_code, "body": body},
        )
    if response.status_code >= 400:
        raise MoleApiError(
            message="1С отклонила обновление заявки",
            details={"http_status": response.status_code, "body": body},
        )
    if body.get("Статус") or body.get("Status"):
        return _require_ok_status(body)
    return body


async def delete_order(crm_id: str) -> dict[str, Any] | None:
    orders_url = _orders_url()
    url = f"{orders_url}/{quote(crm_id, safe='')}"
    response = await _request("DELETE", url)
    if response.status_code in {204, 404}:
        return None
    if not response.content:
        return None
    body = _parse_json_or_raise(response)
    if response.status_code >= 400:
        raise MoleApiError(
            message="1С отклонила удаление заявки",
            details={"http_status": response.status_code, "body": body},
        )
    return body if isinstance(body, dict) else None
