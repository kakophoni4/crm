from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from app.workers import task_notifications as worker


def result(value):
    r = Mock()
    r.mappings.return_value.first.return_value = value
    r.mappings.return_value.one.return_value = value
    r.scalar.return_value = value
    return r


@pytest.mark.parametrize("kind,expected", [("assigned", "Вам поставлена задача"), ("overdue", "У вас просрочена задача")])
async def test_only_generic_message_is_sent(monkeypatch, kind, expected):
    due = datetime.now(timezone.utc) - timedelta(hours=1)
    row = dict(id=1, task_id=7, user_id=9, kind=kind, delivered_to=[], due_at=due)
    db = AsyncMock()
    db.execute.side_effect = [result(row), result(dict(assignee_id=9, status="open", due_at=due)), result("active"), result(None)]
    context = AsyncMock()
    context.__aenter__.return_value = db
    monkeypatch.setattr(worker, "get_session_factory", lambda: lambda: context)
    monkeypatch.setattr(worker, "get_bot_token", AsyncMock(return_value="test-token"))
    monkeypatch.setattr(worker, "_links_for_user", AsyncMock(return_value=[SimpleNamespace(telegram_user_id=123)]))
    send = AsyncMock()
    monkeypatch.setattr(worker.telegram_api, "send_message", send)
    assert await worker.deliver_one()
    send.assert_awaited_once_with("test-token", chat_id=123, text=expected, parse_mode=None)
    assert db.execute.call_args.args[1]["status"] == "sent"


@pytest.mark.parametrize("change", ["deadline", "assignee", "closed"])
async def test_stale_notification_is_cancelled(monkeypatch, change):
    due = datetime.now(timezone.utc) - timedelta(hours=1)
    row = dict(id=1, task_id=7, user_id=9, kind="overdue", delivered_to=[], due_at=due)
    task = dict(assignee_id=9, status="open", due_at=due)
    if change == "deadline": task["due_at"] = due + timedelta(days=1)
    if change == "assignee": task["assignee_id"] = 10
    if change == "closed": task["status"] = "closed"
    db = AsyncMock()
    db.execute.side_effect = [result(row), result(task), result("active"), result(None)]
    context = AsyncMock()
    context.__aenter__.return_value = db
    monkeypatch.setattr(worker, "get_session_factory", lambda: lambda: context)
    send = AsyncMock()
    monkeypatch.setattr(worker.telegram_api, "send_message", send)
    assert await worker.deliver_one()
    send.assert_not_awaited()
    assert db.execute.call_args.args[1]["status"] == "cancelled"
