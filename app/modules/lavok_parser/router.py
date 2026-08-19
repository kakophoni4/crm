from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.lavok_parser.schemas import (
    LavokParserIngestJsonRequest,
    LavokParserIngestResponse,
    LavokParserListResponse,
    LavokParserLotOut,
    LavokParserLotPatchRequest,
)
from app.modules.lavok_parser.service import LavokParserService, parse_query_sheet_date
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_permission
from app.shared.db import get_db
from app.shared.exceptions import AuthenticationRequired, PermissionDenied, ValidationError
from app.shared.security.deps import current_user_optional
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings

router = APIRouter(prefix="/api/v1/lavok-parser", tags=["lavok-parser"])


def _service(session: Annotated[AsyncSession, Depends(get_db)]) -> LavokParserService:
    return LavokParserService(session)


async def _require_ingest_access(
    actor: Annotated[User | None, Depends(current_user_optional)],
    x_lavok_ingest_token: Annotated[str | None, Header()] = None,
) -> User | None:
    token = (x_lavok_ingest_token or "").strip()
    expected = (settings.lavok_parser_ingest_token or "").strip()
    if token:
        if not expected:
            raise PermissionDenied(message="Ingest token is not configured")
        if token != expected:
            raise PermissionDenied(message="Invalid ingest token")
        return None
    if actor is None:
        raise AuthenticationRequired(message="Authentication required")
    if not has_permission(actor.role, Permission.PARSER_READ):
        raise PermissionDenied(message="Нет доступа к парсеру")
    return actor


@router.post("/ingest", response_model=LavokParserIngestResponse)
async def ingest_lavok_xlsx(
    _actor: Annotated[User | None, Depends(_require_ingest_access)],
    service: Annotated[LavokParserService, Depends(_service)],
    file: Annotated[UploadFile, File()],
) -> LavokParserIngestResponse:
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise ValidationError(message="Нужен файл .xlsx")
    content = await file.read()
    if not content:
        raise ValidationError(message="Пустой файл")
    return await service.ingest(content)


@router.post("/ingest-json", response_model=LavokParserIngestResponse)
async def ingest_lavok_json(
    _actor: Annotated[User | None, Depends(_require_ingest_access)],
    service: Annotated[LavokParserService, Depends(_service)],
    body: LavokParserIngestJsonRequest,
) -> LavokParserIngestResponse:
    return await service.ingest_json(body)


@router.get("", response_model=LavokParserListResponse)
async def list_lavok_lots(
    _actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LavokParserService, Depends(_service)],
    sheet_date: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    include_deleted: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LavokParserListResponse:
    return await service.list_lots(
        sheet_date=parse_query_sheet_date(sheet_date),
        q=q,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.patch("/{lot_id}", response_model=LavokParserLotOut)
async def patch_lavok_lot(
    lot_id: int,
    body: LavokParserLotPatchRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LavokParserService, Depends(_service)],
) -> LavokParserLotOut:
    return await service.patch_lot(lot_id, body)


@router.delete("/{lot_id}", status_code=204)
async def delete_lavok_lot(
    lot_id: int,
    _actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LavokParserService, Depends(_service)],
) -> None:
    await service.delete_lot(lot_id)
