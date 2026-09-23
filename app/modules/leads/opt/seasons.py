from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends
from pydantic import BaseModel, Field, AwareDatetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db import get_db
from app.shared.exceptions import PermissionDenied, ValidationError
from app.shared.security.permissions import requires_permission
from app.modules.rbac.permissions import Permission
from app.modules.db.models.user import User
from app.modules.db.models.enums import UserRole

class SeasonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    starts_at: AwareDatetime

async def list_seasons(db: AsyncSession):
    result = await db.execute(text("""SELECT id, name, starts_at,
        id = (SELECT id FROM sales_seasons WHERE starts_at <= now() ORDER BY starts_at DESC LIMIT 1) AS is_current,
        starts_at > now() AS is_planned
        FROM sales_seasons ORDER BY starts_at DESC"""))
    return [dict(r) for r in result.mappings()]

def register_routes(router):
    @router.get('/sales-seasons')
    async def get_seasons(
        actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        return await list_seasons(db)

    @router.post('/sales-seasons', status_code=201)
    async def create_season(
        body: SeasonCreate,
        actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
        db: Annotated[AsyncSession, Depends(get_db)],
    ):
        if actor.role != UserRole.ADMIN:
            raise PermissionDenied(message='Сезоны открывает администратор')
        name = body.name.strip()
        if not name:
            raise ValidationError(message='Укажите название сезона')
        # Serialize boundary changes with inserts to avoid inconsistent assignment.
        await db.execute(text('LOCK TABLE lead_opt_orders IN SHARE ROW EXCLUSIVE MODE'))
        await db.execute(text('LOCK TABLE sales_seasons IN EXCLUSIVE MODE'))
        last = (await db.execute(text('SELECT max(starts_at) FROM sales_seasons'))).scalar_one()
        if body.starts_at <= last:
            raise ValidationError(message='Начало нового сезона должно быть позже предыдущего')
        if body.starts_at < datetime.now(timezone.utc):
            raise ValidationError(message='Выберите будущее время начала: существующие заявки останутся в своих сезонах')
        if (await db.execute(text('SELECT 1 FROM sales_seasons WHERE name = :name'), {'name': name})).scalar():
            raise ValidationError(message='Сезон с таким названием уже существует')
        await db.execute(text('INSERT INTO sales_seasons(name, starts_at, created_by) VALUES (:name, :starts, :actor)'),
                         {'name': name, 'starts': body.starts_at, 'actor': actor.id})
        await db.commit()
        return await list_seasons(db)
