from __future__ import annotations

from typing import Any

import httpx

from app.shared.exceptions import AppError, ValidationError
from app.shared.settings import settings


class SmertnikiUnavailable(AppError):
    def __init__(self, message: str = "Smertniki API is not configured") -> None:
        super().__init__(code="smertniki_unavailable", message=message, status=503)


async def smertniki_request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    base = (settings.smertniki_api_url or "").rstrip("/")
    token = (settings.smertniki_api_token or "").strip()
    if not base or not token:
        raise SmertnikiUnavailable("Smertniki API is not configured")
    url = f"{base}{path}"
    wait = timeout if timeout is not None else settings.smertniki_api_timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=wait) as client:
            response = await client.request(
                method,
                url,
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.RequestError as exc:
        raise SmertnikiUnavailable(f"Не удалось связаться со smertniki: {exc}") from exc

    if response.status_code == 204:
        return None
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text}

    if response.status_code >= 400:
        message = "Ошибка smertniki"
        if isinstance(payload, dict):
            message = str(payload.get("detail") or payload.get("message") or message)
        raise AppError(
            code="smertniki_error",
            message=message,
            status=response.status_code if response.status_code in {400, 404, 409, 422} else 502,
            details={"upstream_status": response.status_code},
        )
    return payload
