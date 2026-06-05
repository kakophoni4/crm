from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.schemas import (
    BotCreateRequest,
    BotCreateResponse,
    BotEventAcceptedResponse,
    BotGroupAssignmentsRequest,
    BotHealthResponse,
    BotListResponse,
    BotResponse,
    BotUpdateRequest,
    RotateSecretRequest,
    RotateSecretResponse,
)
from app.modules.bots.service import BotService
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import AuthenticationRequired
from app.shared.metrics import inc_bot_events_ingest
from app.shared.security.permissions import requires_permission

router = APIRouter(tags=["bots"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> BotService:
    return BotService(db)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "127.0.0.1"


@router.get("/api/v1/bots", response_model=BotListResponse)
async def list_bots(
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_READ))],
    service: Annotated[BotService, Depends(_service)],
) -> BotListResponse:
    return await service.list_bots(actor)


@router.get("/api/v1/bots/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_READ))],
    service: Annotated[BotService, Depends(_service)],
) -> BotResponse:
    return await service.get_bot(bot_id, actor)


@router.post("/api/v1/bots", response_model=BotCreateResponse, status_code=201)
async def create_bot(
    body: BotCreateRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.BOTS_MANAGE))],
    service: Annotated[BotService, Depends(_service)],
) -> BotCreateResponse:
    return await service.create_bot(body)


@router.patch("/api/v1/bots/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: int,
    body: BotUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_MANAGE))],
    service: Annotated[BotService, Depends(_service)],
) -> BotResponse:
    return await service.update_bot(bot_id, body, actor)


@router.put("/api/v1/bots/{bot_id}/group-assignments", response_model=BotResponse)
async def set_bot_group_assignments(
    bot_id: int,
    body: BotGroupAssignmentsRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_REASSIGN))],
    service: Annotated[BotService, Depends(_service)],
) -> BotResponse:
    return await service.set_group_assignments(bot_id, body, actor)


@router.post("/api/v1/bots/{bot_id}/rotate-secret", response_model=RotateSecretResponse)
async def rotate_secret(
    bot_id: int,
    body: RotateSecretRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.BOTS_SECRET_ROTATE))],
    service: Annotated[BotService, Depends(_service)],
) -> RotateSecretResponse:
    return await service.rotate_secret(bot_id, body.kind)


@router.delete("/api/v1/bots/{bot_id}", response_model=BotResponse)
async def delete_bot(
    bot_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.BOTS_MANAGE))],
    service: Annotated[BotService, Depends(_service)],
) -> BotResponse:
    return await service.soft_delete(bot_id, actor)


@router.get("/api/v1/bots/{bot_id}/health", response_model=BotHealthResponse)
async def bot_health(
    bot_id: int,
    _actor: Annotated[User, Depends(requires_permission(Permission.BOTS_READ_METRICS))],
    service: Annotated[BotService, Depends(_service)],
) -> BotHealthResponse:
    return await service.check_health(bot_id)


@router.post(
    "/api/v1/bot-events",
    response_model=BotEventAcceptedResponse,
    status_code=202,
)
async def ingest_bot_event(
    request: Request,
    service: Annotated[BotService, Depends(_service)],
) -> BotEventAcceptedResponse:
    body = await request.body()
    bot_code = request.headers.get("x-bot-code", "")
    event_id = request.headers.get("x-event-id", "")
    timestamp = request.headers.get("x-timestamp", "")
    signature = request.headers.get("x-signature", "")

    if not bot_code or not event_id or not timestamp or not signature:
        inc_bot_events_ingest("rejected")
        raise AuthenticationRequired(message="Unauthorized")

    try:
        payload: dict[str, Any] = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        inc_bot_events_ingest("rejected")
        raise AuthenticationRequired(message="Unauthorized") from None

    try:
        status = await service.ingest_event(
            bot_code=bot_code,
            event_id=event_id,
            timestamp=timestamp,
            signature=signature,
            body=body,
            payload=payload,
            client_ip=_client_ip(request),
        )
    except AuthenticationRequired:
        inc_bot_events_ingest("rejected")
        raise

    inc_bot_events_ingest(status)
    return BotEventAcceptedResponse(status=status)  # type: ignore[arg-type]
