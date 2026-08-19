from __future__ import annotations

from typing import Any

from app.modules.tasks.types import TASK_TYPE_LABELS, TaskType

TASK_STATUS_LABELS: dict[str, str] = {
    "new": "Новая",
    "open": "В работе",
    "done_pending": "На проверке",
    "closed": "Готово",
}

FIELD_LABELS: dict[str, str] = {
    "title": "название",
    "description": "описание",
    "task_type": "приоритет",
    "due_at": "срок",
    "assignee": "исполнителя",
}

HANDOFF_KIND_LABELS: dict[str, str] = {
    "add": "добавил(а) соисполнителя",
    "transfer": "передал(а) задачу",
    "follow_up": "поставил(а) связанную задачу",
}


def _label_status(value: object) -> str:
    key = str(value or "")
    return TASK_STATUS_LABELS.get(key, key or "—")


def _label_type(value: object) -> str:
    raw = str(value or "")
    try:
        return TASK_TYPE_LABELS.get(TaskType(raw), raw)
    except ValueError:
        return raw or "—"


def _person(payload: dict[str, Any], key: str) -> str:
    name = payload.get(f"{key}_name") or payload.get(key)
    if name:
        return str(name)
    user_id = payload.get(f"{key}_id")
    if user_id:
        return f"user #{user_id}"
    return "—"


def format_task_history_summary(action: str, payload: dict[str, Any] | None) -> str:
    data = payload or {}
    kind = str(data.get("kind") or "")

    if action == "task.create" or kind == "create":
        assignee = _person(data, "assignee")
        return f"создал(а) задачу и назначил(а) на {assignee}"

    if action == "task.delete" or kind == "delete":
        return "закрыл(а) задачу"

    if action == "task.handoff" or kind in HANDOFF_KIND_LABELS:
        verb = HANDOFF_KIND_LABELS.get(kind or str(data.get("action") or ""), "передал(а) задачу")
        target = _person(data, "user") or _person(data, "assignee")
        title = str(data.get("child_title") or "").strip()
        if kind == "follow_up" and title:
            return f"{verb} «{title}» для {target}"
        return f"{verb}: {target}"

    if kind == "files":
        count = data.get("count")
        if isinstance(count, int) and count > 0:
            return f"добавил(а) файлы ({count})"
        return "добавил(а) файлы"

    if kind == "assignee":
        previous = str(data.get("from_name") or data.get("from") or "—")
        nxt = str(data.get("to_name") or data.get("to") or "—")
        return f"сменил(а) исполнителя: {previous} → {nxt}"

    if action == "task.status.update" or kind in {
        "status",
        "acknowledge",
        "complete",
        "confirm",
        "reopen",
        "move",
    }:
        if kind == "acknowledge":
            return "принял(а) задачу в работу"
        if kind == "complete":
            return "отметил(а) выполнение"
        if kind == "confirm":
            return "подтвердил(а) выполнение"
        if kind == "reopen":
            return "вернул(а) задачу в работу"
        previous = _label_status(data.get("from"))
        nxt = _label_status(data.get("to"))
        return f"сменил(а) статус: {previous} → {nxt}"

    changes = data.get("changes")
    if isinstance(changes, dict) and changes:
        labels: list[str] = []
        for field, delta in changes.items():
            label = FIELD_LABELS.get(str(field), str(field))
            if isinstance(delta, dict) and "from" in delta and "to" in delta:
                old = delta.get("from")
                new = delta.get("to")
                if field == "task_type":
                    old = _label_type(old)
                    new = _label_type(new)
                elif field == "due_at":
                    old = old or "без срока"
                    new = new or "без срока"
                labels.append(f"{label}: {old} → {new}")
            else:
                labels.append(label)
        if len(labels) == 1:
            return f"изменил(а) {labels[0]}"
        return "изменил(а) " + ", ".join(labels)

    return "изменил(а) задачу"
