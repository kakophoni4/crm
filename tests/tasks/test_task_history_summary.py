from __future__ import annotations

from app.modules.tasks.history import format_task_history_summary


def test_format_create_and_status_summaries() -> None:
    assert "Иван" in format_task_history_summary(
        "task.create",
        {"kind": "create", "assignee_name": "Иван"},
    )
    assert format_task_history_summary(
        "task.status.update",
        {"kind": "complete", "from": "open", "to": "done_pending"},
    ) == "отметил(а) выполнение"
    assert "Петр" in format_task_history_summary(
        "task.update",
        {"kind": "assignee", "from_name": "Петр", "to_name": "Иван"},
    )
    assert "название" in format_task_history_summary(
        "task.update",
        {"kind": "fields", "changes": {"title": {"from": "A", "to": "B"}}},
    )
    assert "связанную задачу" in format_task_history_summary(
        "task.handoff",
        {"kind": "follow_up", "user_name": "Иван", "child_title": "Доработка"},
    )
    assert format_task_history_summary("task.delete", {"kind": "delete"}) == (
        "перенёс(ла) задачу в удалённые"
    )
    assert format_task_history_summary("task.delete", {"kind": "purge"}) == (
        "удалил(а) задачу безвозвратно"
    )
