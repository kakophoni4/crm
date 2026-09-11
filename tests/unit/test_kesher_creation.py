import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from app.modules.users.service import UserService
from app.modules.users.schemas import UserCreateRequest
from app.modules.db.models.enums import UserRole
from app.shared.exceptions import Conflict


def test_migration_allows_kesher_without_relaxing_other_roles():
    path = Path(__file__).parents[2] / "alembic/versions/0119_kesher_user_org.py"
    spec = importlib.util.spec_from_file_location("kesher_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements = []
    with patch.object(module, "op", SimpleNamespace(execute=statements.append)):
        module.upgrade()
    expression = statements[1].split("CHECK (", 1)[1].rsplit(")", 1)[0]
    with sqlite3.connect(":memory:") as db:
        db.execute(f"CREATE TABLE users (role TEXT, department_id INTEGER, group_id INTEGER, CHECK ({expression}))")
        for role in ("admin", "accountant", "chief_accountant", "lawyer", "kesher"):
            db.execute("INSERT INTO users VALUES (?, NULL, NULL)", (role,))
        for row in (("kesher", 1, None), ("kesher", None, 1), ("user", None, None), ("senior", 1, 1)):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("INSERT INTO users VALUES (?, ?, ?)", row)


@pytest.mark.asyncio
@pytest.mark.parametrize("sqlstate,expected", [("23505", Conflict), ("23514", IntegrityError), ("23503", IntegrityError)])
async def test_create_does_not_report_constraint_errors_as_duplicate_login(sqlstate, expected):
    service = UserService(AsyncMock())
    service._ensure_can_create_role = Mock()
    service._resolve_create_assignment = AsyncMock(return_value=([], None))
    original = Exception("database constraint")
    original.sqlstate = sqlstate
    service._repo = SimpleNamespace(add=AsyncMock(side_effect=IntegrityError("INSERT", {}, original)), rollback=AsyncMock())
    body = UserCreateRequest(username="kesher_test", full_name="Кешер", password="ExampleStrong123!", role=UserRole.KESHER)
    with patch("app.modules.users.service.hash_password", return_value="hash"):
        with pytest.raises(expected):
            await service.create_user(SimpleNamespace(id=1), body)
    service._repo.rollback.assert_awaited_once()
