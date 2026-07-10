"""HTTP client for sbis-norm FNS requirements API.

Docs: GET/POST /api/sbis/requirements/ …
Auth: X-API-Key or Authorization: Bearer <token> when SBIS_NORM_API_TOKEN is set.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.shared.exceptions import AppError
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)


class SbisNormApiError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code="sbis_norm_api_error",
            message=message,
            status=502,
            details=details,
        )


def _auth_headers() -> dict[str, str]:
    token = get_settings().sbis_norm_api_token.strip()
    if not token:
        return {}
    return {
        "X-API-Key": token,
        "Authorization": f"Bearer {token}",
    }


def _base_url() -> str:
    base = get_settings().sbis_norm_api_base_url.strip().rstrip("/")
    if not base:
        raise SbisNormApiError(message="SBIS_NORM_API_BASE_URL не настроен")
    return base


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    settings = get_settings()
    url = f"{_base_url()}{path}"
    timeout = httpx.Timeout(settings.sbis_norm_api_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=_auth_headers(),
            )
    except httpx.HTTPError as exc:
        logger.warning("sbis_norm_transport_error", method=method, path=path, error=str(exc))
        raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from exc

    if response.status_code == 401:
        raise SbisNormApiError(
            message="sbis-norm отклонил авторизацию (проверьте SBIS_NORM_API_TOKEN)",
            details={"http_status": 401},
        )
    if response.status_code == 404:
        raise SbisNormApiError(
            message="Документ не найден в sbis-norm",
            details={"http_status": 404, "path": path},
        )
    if response.status_code >= 400:
        raise SbisNormApiError(
            message="sbis-norm вернул ошибку",
            details={"http_status": response.status_code, "text": response.text[:500]},
        )

    try:
        return response.json()
    except ValueError as exc:
        raise SbisNormApiError(
            message="sbis-norm вернул некорректный JSON",
            details={"http_status": response.status_code, "text": response.text[:500]},
        ) from exc


async def list_requirements(
    *,
    unsynced: bool = True,
    inn: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    since_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": max(1, min(limit, 500))}
    if unsynced:
        params["unsynced"] = "1"
    if inn:
        params["inn"] = inn
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    if since_id is not None:
        params["since_id"] = since_id
    return await _request("GET", "/api/sbis/requirements/", params=params)


async def get_requirement(requirement_id: int) -> dict[str, Any]:
    return await _request("GET", f"/api/sbis/requirements/{requirement_id}/")


async def mark_synced(ids: list[int]) -> dict[str, Any]:
    if not ids:
        return {"updated": 0, "synced_at": None}
    return await _request(
        "POST",
        "/api/sbis/requirements/mark-synced/",
        json_body={"ids": ids},
    )
