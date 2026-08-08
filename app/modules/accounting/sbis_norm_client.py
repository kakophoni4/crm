"""HTTP client for sbis-norm FNS requirements API.

Docs: GET/POST /api/sbis/requirements/ …
Auth: X-API-Key or Authorization: Bearer <token> when SBIS_NORM_API_TOKEN is set.

File download: GET /api/sbis/requirements/<id>/file/ (raw PDF bytes, not file_b64).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.shared.exceptions import AppError
from app.shared.settings import get_settings

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = (1.0, 3.0, 8.0)


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


def _timeout() -> httpx.Timeout:
    """Connect fast, allow slow body (PDF / flaky inter-VPS links)."""
    total = max(float(get_settings().sbis_norm_api_timeout_seconds), 30.0)
    return httpx.Timeout(
        connect=15.0,
        read=total,
        write=30.0,
        pool=15.0,
    )


def _raise_for_status(response: httpx.Response, *, path: str) -> None:
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


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    url = f"{_base_url()}{path}"
    timeout = _timeout()
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=_auth_headers(),
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            logger.warning(
                "sbis_norm_transport_error",
                method=method,
                path=path,
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt + 1 < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS[attempt])
                continue
            raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from exc
        except httpx.HTTPError as exc:
            logger.warning("sbis_norm_transport_error", method=method, path=path, error=str(exc))
            raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from exc

        _raise_for_status(response, path=path)

        try:
            return response.json()
        except ValueError as exc:
            raise SbisNormApiError(
                message="sbis-norm вернул некорректный JSON",
                details={"http_status": response.status_code, "text": response.text[:500]},
            ) from exc

    raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from last_exc


async def _request_bytes(method: str, path: str) -> bytes:
    url = f"{_base_url()}{path}"
    timeout = _timeout()
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=_auth_headers(),
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            logger.warning(
                "sbis_norm_transport_error",
                method=method,
                path=path,
                attempt=attempt + 1,
                error=str(exc),
            )
            if attempt + 1 < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS[attempt])
                continue
            raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from exc
        except httpx.HTTPError as exc:
            logger.warning("sbis_norm_transport_error", method=method, path=path, error=str(exc))
            raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from exc

        _raise_for_status(response, path=path)
        content = response.content
        if not content:
            raise SbisNormApiError(
                message="sbis-norm вернул пустой файл",
                details={"path": path},
            )
        return content

    raise SbisNormApiError(message="Не удалось связаться с sbis-norm") from last_exc


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
    """Light meta JSON (no file_b64 by default)."""
    return await _request("GET", f"/api/sbis/requirements/{requirement_id}/")


async def get_requirement_file(requirement_id: int) -> bytes:
    """Raw PDF bytes from GET …/requirements/<id>/file/."""
    return await _request_bytes("GET", f"/api/sbis/requirements/{requirement_id}/file/")


async def mark_synced(ids: list[int]) -> dict[str, Any]:
    if not ids:
        return {"updated": 0, "synced_at": None}
    return await _request(
        "POST",
        "/api/sbis/requirements/mark-synced/",
        json_body={"ids": ids},
    )


async def reply_requirement(
    requirement_id: int,
    *,
    attachments: list[dict[str, str]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """POST …/requirements/<id>/reply/ — timeout ≥180s for EDS."""
    url = f"{_base_url()}/api/sbis/requirements/{requirement_id}/reply/"
    timeout = httpx.Timeout(connect=15.0, read=180.0, write=60.0, pool=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json={"attachments": attachments, "dry_run": dry_run},
                headers=_auth_headers(),
            )
    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPError) as exc:
        raise SbisNormApiError(message="Не удалось отправить ответ в sbis-norm") from exc
    if response.status_code >= 400:
        detail: dict[str, Any] = {"http_status": response.status_code}
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail["body"] = payload
                err = payload.get("error")
                if isinstance(err, dict) and err.get("message"):
                    raise SbisNormApiError(
                        message=str(err["message"]),
                        details=detail,
                    )
        except ValueError:
            detail["text"] = response.text[:500]
        raise SbisNormApiError(
            message="sbis-norm отклонил ответ на требование",
            details=detail,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise SbisNormApiError(message="sbis-norm вернул некорректный JSON") from exc
    if not isinstance(data, dict):
        raise SbisNormApiError(message="sbis-norm вернул неожиданный ответ")
    return data
