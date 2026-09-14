"""Accounting edits the shared shop record, scoped by unit assignment."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import SecretStr, Field
from app.modules.bots.crypto import encrypt_secret, decrypt_secret
from app.modules.db.models.enums import UserRole
from app.shared.exceptions import PermissionDenied
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.service import AccountingService
from app.modules.db.models.lawyer_director import LawyerShop
from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.user import User
from app.modules.lawyer_registry.schemas import LawyerShopOut, LawyerShopPatchRequest
from app.modules.lawyer_registry.service import LawyerRegistryService
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import NotFound, ValidationError
from app.shared.security.permissions import requires_permission


router = APIRouter(prefix="/api/v1/accounting", tags=["accounting"])


async def require_sbis_access(db: AsyncSession, actor: User, unit_id: int) -> None:
    if actor.role == UserRole.ADMIN:
        return
    if actor.role not in (UserRole.ACCOUNTANT, UserRole.CHIEF_ACCOUNTANT):
        raise PermissionDenied(message="Нет доступа к паролю СБИС")
    from app.modules.db.models.opt_accountant_unit_assignment import OptAccountantUnitAssignment
    assigned = await db.scalar(select(OptAccountantUnitAssignment.id).where(
        OptAccountantUnitAssignment.unit_id == unit_id,
        OptAccountantUnitAssignment.user_id == actor.id,
    ))
    if assigned is None:
        raise PermissionDenied(message="Пароль СБИС доступен только назначенному бухгалтеру и администратору")


class AccountingShopPatch(LawyerShopPatchRequest):
    dirovod: str | None = None
    sbis_password: SecretStr | None = Field(default=None, max_length=512)


async def scoped_unit(db: AsyncSession, actor: User, unit_id: int, *, lock: bool = False) -> OptUnit:
    service = AccountingService(db)
    visible = await service._visible_supplier_inns(actor, active_only=False)
    unit = await db.get(OptUnit, unit_id, with_for_update=lock)
    if unit is None or (visible is not None and unit.inn not in visible):
        raise NotFound(message="Лавка не найдена")
    return unit


@router.get("/units/{unit_id}/card", response_model=LawyerShopOut | None)
async def get_shop_card(
    unit_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerShopOut | None:
    unit = await scoped_unit(db, actor, unit_id)
    service = LawyerRegistryService(db)
    shop = await service._repo.get_shop_by_inn(unit.inn)
    if shop is None:
        return None
    director = await service._repo.get_director(shop.director_id) if shop.director_id else None
    return service._shop_out(shop, director.full_name if director else None).model_copy(update={"dirovod": director.dirovod if director else None})


@router.patch("/units/{unit_id}/card", response_model=LawyerShopOut)
async def patch_shop_card(
    unit_id: int,
    body: AccountingShopPatch,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerShopOut:
    unit = await scoped_unit(db, actor, unit_id, lock=True)
    data = body.model_dump(exclude_unset=True)
    update_password = "sbis_password" in data
    password = data.pop("sbis_password", None)
    if update_password:
        await require_sbis_access(db, actor, unit_id)
    update_dirovod = "dirovod" in data
    dirovod = data.pop("dirovod", None)
    shop_body = LawyerShopPatchRequest(**data)
    if set(data) & {"kind", "director_id", "planned_payout", "pinned", "hidden", "accountant"}:
        raise ValidationError(message="Эти поля изменяются в соответствующем разделе")
    if "name" in data and not str(data["name"] or "").strip():
        raise ValidationError(message="Укажите название лавки")
    service = LawyerRegistryService(db)
    shop = (await db.execute(select(LawyerShop).where(LawyerShop.inn == unit.inn).with_for_update())).scalar_one_or_none()
    if shop is None:
        # Creating a shared card does not enable sales or submit anything externally.
        director_name = data.pop("director_name", None)
        director = await service._ensure_director(director_name, actor_id=actor.id)
        shop = LawyerShop(inn=unit.inn, name=unit.name or unit.inn, kind="new", source="manual", created_by=actor.id)
        shop.director_id = director.id if director else None
        for key, value in data.items():
            setattr(shop, key, value)
        db.add(shop)
        await db.flush()
        shop_body = LawyerShopPatchRequest()
    result = await service.patch_shop(actor, shop.id, shop_body)
    director = await service._repo.get_director(shop.director_id) if shop.director_id else None
    if update_dirovod:
        if director is None and dirovod:
            raise ValidationError(message="Сначала укажите директора")
        if director is not None:
            director.dirovod = dirovod
    if update_password:
        secret = password.get_secret_value() if password is not None else ""
        shop.sbis_password_encrypted = await encrypt_secret(db, secret) if secret else None
    await db.commit()
    return result.model_copy(update={"dirovod": director.dirovod if director else None})


@router.post("/units/{unit_id}/sbis-password/reveal")
async def reveal_sbis_password(
    unit_id: int,
    response: Response,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await require_sbis_access(db, actor, unit_id)
    unit = await scoped_unit(db, actor, unit_id)
    shop = await db.scalar(select(LawyerShop).where(LawyerShop.inn == unit.inn))
    response.headers["Cache-Control"] = "no-store"
    return {"password": await decrypt_secret(db, shop.sbis_password_encrypted) if shop and shop.sbis_password_encrypted else None}
