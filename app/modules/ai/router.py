from __future__ import annotations

import re
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.client import call, revision, write
from app.modules.db.models.ai import AIAudit, AIRequest
from app.modules.db.models.user import User
from app.modules.rbac.role_checks import is_admin
from app.shared.db import get_db
from app.shared.exceptions import AppError, PermissionDenied
from app.shared.security.deps import current_user
from app.shared.settings import settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


async def admin(actor: Annotated[User, Depends(current_user)]) -> User:
    if not is_admin(actor.role):
        raise PermissionDenied(message="Управление ИИ доступно только администратору")
    return actor


Admin = Annotated[User, Depends(admin)]
DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/status")
async def status(actor: Admin) -> Any:
    return {
        "base_url": settings.ai_service_base_url,
        "reply_key_configured": bool(settings.ai_service_reply_key.get_secret_value()),
        "admin_key_configured": bool(settings.ai_service_admin_key.get_secret_value()),
        "auto_replies_enabled": settings.ai_auto_replies_enabled,
    }


def request_out(row: Any) -> Any:
    return {
        "id": row.id,
        "status": row.status,
        "body": {} if row.path == "__prepare_export__" else row.body,
        "result": row.result,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/requests")
async def requests(actor: Admin, db: DB, live: bool = False) -> Any:
    rows = await db.scalars(
        select(AIRequest)
        .where(
            AIRequest.chat_id.is_not(None) if live else AIRequest.chat_id.is_(None),
            AIRequest.path != "__prepare_export__",
        )
        .order_by(AIRequest.created_at.desc())
        .limit(50)
    )
    return {"items": [request_out(row) for row in rows]}


@router.get("/preparations")
async def preparations(actor: Admin, db: DB) -> Any:
    rows = await db.scalars(
        select(AIRequest)
        .where(AIRequest.path == "__prepare_export__")
        .order_by(AIRequest.created_at.desc())
        .limit(10)
    )
    return {"items": [{"id": r.id, "status": r.status} for r in rows]}


@router.get("/requests/{request_id}")
async def get_request(request_id: str, actor: Admin, db: DB) -> Any:
    row = await db.get(AIRequest, request_id)
    if row is None:
        raise AppError("not_found", "Запрос не найден", 404)
    return request_out(row)


@router.get("/journal")
async def journal(actor: Admin, db: DB) -> Any:
    rows = await db.scalars(select(AIAudit).order_by(AIAudit.id.desc()).limit(100))
    return {
        "items": [
            {
                "id": r.id,
                "actor_id": r.actor_id,
                "action": r.action,
                "status": r.status,
                "data": r.data,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


READ = (
    "(capabilities|connection|models|prompts(?:/\\d+)?|catalog|examples"
    "(?:/export)?|datasets(?:/[a-zA-Z0-9_-]+)?|training/status|trainin"
    "g/jobs(?:/[a-zA-Z0-9_-]+(?:/logs)?)?|model-versions|audit)"
)
WRITE = {
    "PUT": r"(connection|catalog)",
    "POST": (
        "(connection/check|prompts(?:/\\d+/activate)?|test/replies|examples"
        "(?:/\\d+/approve)?|datasets(?:/import|/from-approved|/[a-zA-Z0-9_-"
        "]+/approve)?|training/jobs(?:/[a-zA-Z0-9_-]+/cancel)?|model-versi"
        "ons/[a-zA-Z0-9_-]+/(test|approve|activate)|model-activations/[a-z"
        "A-Z0-9_-]+/rollback)"
    ),
    "PATCH": r"examples/\d+",
    "DELETE": r"examples/\d+",
}


@router.api_route("/service/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def service(path: str, request: Request, actor: Admin, db: DB) -> Any:
    method = request.method
    if not re.fullmatch(READ if method == "GET" else WRITE.get(method, r"(?!)"), path):
        raise AppError("not_found", "Операция ИИ не поддерживается", 404)
    limit = 32 * 1024 * 1024 if path in ("datasets", "datasets/import") else 256 * 1024
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise AppError("too_large", "Файл или запрос превышает допустимый размер", 413)
    body = None
    if raw and path != "datasets/import":
        import json

        try:
            body = json.loads(raw)
        except ValueError:
            raise AppError("invalid_json", "Некорректный JSON", 422) from None
        if not isinstance(body, dict):
            raise AppError("invalid_json", "Ожидается объект", 422)
    if method == "POST" and (
        path == "test/replies" or re.fullmatch(r"model-versions/[a-zA-Z0-9_-]+/test", path)
    ):
        body = body or {}
        request_id = "crm-test-" + str(uuid4())
        body["request_id"] = request_id
        body["chat_id"] = "crm-test-" + str(actor.id)
        row = AIRequest(id=request_id, actor_id=actor.id, path=path, body=body)
        db.add(row)
        db.add(
            AIAudit(
                actor_id=actor.id, action=path, status="queued", data={"request_id": request_id}
            )
        )
        await db.commit()
        return JSONResponse({"request_id": request_id, "status": "queued"}, status_code=202)
    audit_id = None
    if method != "GET":
        audit = AIAudit(actor_id=actor.id, action=method + " " + path, data={})
        db.add(audit)
        await db.flush()
        audit_id = audit.id
    await db.commit()  # No transaction while waiting for the external API.
    try:
        if method == "GET":
            code, result = await call(
                method, path, params=dict(request.query_params), admin=path != "capabilities"
            )
            if path in ("connection", "catalog"):
                result = {**result, "_crm_revision": revision(result)}
        else:
            code, result = await write(
                method,
                path,
                body=body,
                content=bytes(raw) if path == "datasets/import" else None,
                params=dict(request.query_params),
            )
    except AppError as exc:
        if audit_id:
            audit_row = await db.get(AIAudit, audit_id)
            assert audit_row is not None
            audit_row.status = "uncertain" if exc.code == "ai_unreachable" else "failed"
            audit_row.data = {"code": exc.code}
            await db.commit()
        raise
    if audit_id:
        audit_row = await db.get(AIAudit, audit_id)
        assert audit_row is not None
        audit_row.status = "succeeded"
        audit_row.data = {
            k: result[k]
            for k in (
                "id",
                "activation_id",
                "previous_model",
                "model",
                "active_prompt_id",
                "version",
            )
            if isinstance(result, dict) and k in result
        }
        await db.commit()
    return JSONResponse(
        result, status_code=200 if code == 204 else code, headers={"Cache-Control": "no-store"}
    )
