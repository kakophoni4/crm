"""CRM-facing file checks; execution lives alongside the parser's Telegram session."""
# ruff: noqa: RUF001

from __future__ import annotations

import re
from typing import Annotated, Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.exceptions import AppError, ValidationError
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings

router = APIRouter(prefix="/api/v1/lavok-parser/checks", tags=["company-checks"])
Actor = Annotated[User, Depends(requires_permission(Permission.PARSER_READ))]
MAX_UPLOAD = 20 * 1024 * 1024
MAX_RESULT = 100 * 1024 * 1024
CHUNK = 16 * 1024


class CheckJob(BaseModel):
    id: str
    filename: str
    status: str
    created_at: str
    updated_at: str
    total: int
    completed: int
    checks_done: int
    checks_total: int
    failed_checks: int
    rejected_rows: int
    duplicates: int
    input_rows: int
    progress: float
    current_inn: str | None = None
    source_label: str = ""
    error: str | None = None
    result_ready: bool = False


class CheckJobs(BaseModel):
    items: list[CheckJob]


def base_url() -> str:
    configured = (settings.lavok_parser_checks_url or "").strip()
    if configured:
        parsed = urlsplit(configured)
    else:
        parsed = urlsplit((settings.lavok_parser_pull_url or "").strip())
        parsed = parsed._replace(path="/lavok/checks", query="", fragment="")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AppError("checks_not_configured", "Сервер проверки компаний не настроен", 503)
    if not settings.lavok_parser_ingest_token:
        raise AppError("checks_not_configured", "Не настроен доступ к серверу проверки", 503)
    return urlunsplit(parsed).rstrip("/")


def job_path(job_id: str, suffix: str = "") -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValidationError(message="Некорректный номер задания")
    return f"/{job_id}{suffix}"


def headers(actor: User) -> dict[str, str]:
    return {
        "X-Lavok-Ingest-Token": settings.lavok_parser_ingest_token,
        "X-Lavok-Owner": f"crm-user:{actor.id}",
    }


def upstream_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    message = "Сервер проверки отклонил запрос"
    try:
        body = response.json()
        if isinstance(body.get("error"), str):
            message = body["error"][:500]
    except (ValueError, AttributeError):
        pass
    # Parser access failures concern server configuration, not the CRM user's login.
    status = response.status_code if response.status_code in {404, 409, 413, 422} else 502
    raise AppError("company_check_error", message, status)


async def request(actor: User, method: str, path: str = "", **kwargs: Any) -> Any:
    url = base_url() + path
    extra_headers = kwargs.pop("headers", {})
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=90) as client:
            response = await client.request(
                method, url, headers={**headers(actor), **extra_headers}, **kwargs
            )
    except httpx.RequestError as exc:
        raise AppError(
            "checks_unavailable",
            "Сервер проверки недоступен. Проверьте его запуск и соединение",
            503,
        ) from exc
    upstream_error(response)
    try:
        return response.json()
    except ValueError as exc:
        raise AppError(
            "checks_bad_response", "Сервер проверки вернул некорректный ответ", 502
        ) from exc


@router.post("", response_model=CheckJob, status_code=202)
async def create_check(actor: Actor, file: Annotated[UploadFile, File()]) -> Any:
    filename = file.filename or "companies.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise ValidationError(message="Нужен файл .xlsx")
    content = await file.read(MAX_UPLOAD + 1)
    if not content or len(content) > MAX_UPLOAD:
        raise ValidationError(message="Нужен непустой файл размером до 20 МБ")
    return await request(
        actor,
        "POST",
        content=content,
        headers={
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "X-Lavok-Filename": quote(filename, safe=""),
        },
    )


@router.get("", response_model=CheckJobs)
async def list_checks(actor: Actor) -> Any:
    return await request(actor, "GET")


@router.get("/{job_id}", response_model=CheckJob)
async def get_check(job_id: str, actor: Actor) -> Any:
    return await request(actor, "GET", job_path(job_id))


@router.post("/{job_id}/cancel", response_model=CheckJob)
async def cancel_check(job_id: str, actor: Actor) -> Any:
    return await request(actor, "POST", job_path(job_id, "/cancel"))


@router.post("/{job_id}/resume", response_model=CheckJob)
async def resume_check(job_id: str, actor: Actor) -> Any:
    return await request(actor, "POST", job_path(job_id, "/resume"))


async def fetch_result(actor: User, job_id: str) -> bytes:
    url = base_url() + job_path(job_id, "/result.xlsx")
    chunks = []
    offset = 0
    total = None
    etag = None
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=60) as client:
            while total is None or offset < total:
                end = offset + CHUNK - 1
                response = None
                for attempt in range(3):
                    try:
                        response = await client.get(
                            url, headers={**headers(actor), "Range": f"bytes={offset}-{end}"}
                        )
                        break
                    except httpx.RequestError:
                        if attempt == 2:
                            raise
                assert response is not None
                upstream_error(response)
                match = re.fullmatch(
                    r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
                )
                if response.status_code != 206 or not match:
                    raise AppError(
                        "checks_bad_range",
                        "Сервер проверки не поддерживает загрузку частями: обновите раздачу",
                        502,
                    )
                start, stop, size = map(int, match.groups())
                if (
                    start != offset
                    or stop >= size
                    or stop > end
                    or size > MAX_RESULT
                    or len(response.content) != stop - start + 1
                ):
                    raise AppError(
                        "checks_bad_range", "Некорректный размер результата проверки", 502
                    )
                if total is not None and (total != size or etag != response.headers.get("ETag")):
                    raise AppError(
                        "checks_changed",
                        "Результат изменился во время скачивания. Повторите загрузку",
                        409,
                    )
                total = size
                etag = response.headers.get("ETag")
                chunks.append(response.content)
                offset = stop + 1
    except httpx.RequestError as exc:
        raise AppError(
            "checks_unavailable", "Не удалось скачать результат с сервера проверки", 503
        ) from exc
    return b"".join(chunks)


@router.get("/{job_id}/result.xlsx")
async def download_check(job_id: str, actor: Actor) -> Response:
    content = await fetch_result(actor, job_id)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="company_checks_{job_id[:8]}.xlsx"'},
    )
