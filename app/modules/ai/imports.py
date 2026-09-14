# ruff: noqa: RUF001
"""Bounded, local-only preparation of raw CRM exports. Never auto-approves data."""

import gzip
import hashlib
import io
import json
import re
from typing import Annotated, Any

from fastapi import Request
from pydantic import BaseModel, Field

from app.modules.ai.router import DB, Admin, router
from app.shared.exceptions import AppError

MAX_BYTES = 32 * 1024 * 1024


def prepare(raw: bytes, per_chat_limit: int | None = None) -> Any:
    stream = gzip.GzipFile(fileobj=io.BytesIO(raw)) if raw[:2] == b"\x1f\x8b" else io.BytesIO(raw)
    output: list[dict[str, Any]] = []
    total = 0
    warnings: list[str] = []
    preview_bytes = 0
    try:
        for number in range(1, 10002):
            line = stream.readline(MAX_BYTES + 1)
            if not line:
                break
            total += len(line)
            if total > MAX_BYTES or number > 10000:
                raise AppError(
                    "too_large", "Распакованный архив превышает 32 МБ или 10000 строк", 413
                )
            obj = json.loads(line)
            messages = obj.get("messages")
            if not isinstance(messages, list) or not isinstance(obj.get("chat"), dict):
                raise ValueError()
            cid = (
                "anonymous-"
                + hashlib.sha256(str(obj["chat"].get("id", number)).encode()).hexdigest()[:16]
            )
            replacements: dict[str, str] = {}

            def mask(text: Any, replacements: Any = replacements) -> Any:
                def token(match: Any) -> Any:
                    value = match.group(0)
                    if value not in replacements:
                        replacements[value] = f"[ДАННЫЕ_{len(replacements) + 1}]"
                    return replacements[value]

                return re.sub(
                    (
                        "[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}|https?://\\S+|(?<!\\w)@\\w+|(?<!\\w)\\+"
                        "?\\d[\\d ()-]{7,}\\d"
                    ),
                    token,
                    text,
                )

            chat_start = len(output)
            history: list[dict[str, str]] = []
            for m in sorted(
                messages, key=lambda m: (str(m.get("created_at", "")), int(m.get("id", 0)))
            ):
                if m.get("attachments"):
                    warnings.append(f"Строка {number}: содержимое вложений не прочитано")
                text = (m.get("text") or "").strip()
                if not text or text.startswith("/") or m.get("kind") == "system":
                    continue
                text = mask(text)
                inbound = m.get("direction") == "inbound"
                if (
                    not inbound
                    and m.get("sender_user_id")
                    and history
                    and history[-1]["role"] == "user"
                ):
                    preview_bytes += sum(len(x["content"].encode()) for x in history[-50:]) + len(
                        text.encode()
                    )
                    if preview_bytes > 8 * 1024 * 1024:
                        raise AppError(
                            "preview_too_large",
                            "Предпросмотр превышает 8 МБ. Разделите исходный архив.",
                            413,
                        )
                    output.append(
                        {
                            "chat_id": cid,
                            "system": "",
                            "messages": list(history[-50:]),
                            "answer": {"reply": text, "action": "reply", "reason": None},
                        }
                    )
                    if len(output) >= 200:
                        break
                    if len(output) > 10000:
                        raise AppError(
                            "too_large", "Более 10000 вариантов ответов. Разделите архив.", 413
                        )
                history.append({"role": "user" if inbound else "assistant", "content": text})
                if per_chat_limit and len(output) - chat_start >= per_chat_limit:
                    break
            # Return bounded previews, not duplicated full histories for an entire archive.
            if len(output) >= 200:
                warnings.append(
                    "Предпросмотр ограничен первыми 200 вариантами. Разделите архив дл"
                    "я обработки остальных."
                )
                output = output[:200]
                break
    except (ValueError, TypeError, KeyError, AttributeError, OSError, EOFError):
        raise AppError(
            "invalid_export",
            "Не удалось прочитать строку архива. Нужна выгрузка CRM chat/messages в JSONL или GZ.",
            422,
        ) from None
    return {
        "records": output,
        "warnings": list(dict.fromkeys(warnings))[:30],
        "notice": (
            "Email, телефоны, числовые реквизиты и ссылки заменены. ФИО, адрес"
            "а и смысл ответа нужно проверить вручную. Ни один пример не отпра"
            "влен в ИИ."
        ),
    }


@router.post("/prepare-export")
async def prepare_export(request: Request, actor: Admin, db: DB) -> Any:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise AppError("too_large", "Максимум 32 МБ", 413)
    import base64
    from uuid import uuid4

    from app.modules.db.models.ai import AIRequest

    rid = "crm-prepare-" + str(uuid4())
    db.add(
        AIRequest(
            id=rid,
            actor_id=actor.id,
            path="__prepare_export__",
            body={"archive": base64.b64encode(raw).decode("ascii")},
        )
    )
    await db.commit()
    return {"request_id": rid, "status": "queued"}


@router.get("/source-chats")
async def source_chats(actor: Admin, db: DB, offset: int = 0, query: str = "") -> Any:
    from sqlalchemy import or_, select

    from app.modules.db.models.chat import Chat
    from app.modules.db.models.contact import Contact

    if offset < 0 or len(query) > 200:
        raise AppError("invalid_filter", "Некорректный поиск", 422)
    statement = (
        select(Chat.id, Contact.full_name, Chat.last_message_at)
        .join(Contact, Contact.id == Chat.contact_id)
        .where(Chat.last_message_at.is_not(None))
    )
    if query.strip():
        clauses = [Contact.full_name.contains(query.strip(), autoescape=True)]
        if query.strip().isascii() and query.strip().isdigit() and int(query.strip()) < 2**63:
            clauses.append(Chat.id == int(query.strip()))
        statement = statement.where(or_(*clauses))
    rows = (
        await db.execute(
            statement.order_by(Chat.last_message_at.desc(), Chat.id.desc()).offset(offset).limit(31)
        )
    ).all()
    return {
        "items": [
            {"id": r.id, "name": r.full_name, "last_message_at": r.last_message_at.isoformat()}
            for r in rows[:30]
        ],
        "has_more": len(rows) > 30,
    }


class SourceChatsInput(BaseModel):
    chat_ids: list[Annotated[int, Field(gt=0, lt=2**63)]] = Field(min_length=1, max_length=20)


@router.post("/prepare-chats")
async def prepare_chats(body: SourceChatsInput, actor: Admin, db: DB) -> Any:
    import base64
    from uuid import uuid4

    from sqlalchemy import select

    from app.modules.db.models.ai import AIAudit, AIRequest
    from app.modules.db.models.chat_message import ChatMessage
    from app.modules.db.models.enums import MessageKind

    lines, size = [], 0
    for cid in dict.fromkeys(body.chat_ids):
        rows = (
            await db.execute(
                select(
                    ChatMessage.id,
                    ChatMessage.created_at,
                    ChatMessage.text,
                    ChatMessage.direction,
                    ChatMessage.sender_user_id,
                )
                .where(ChatMessage.chat_id == cid, ChatMessage.kind != MessageKind.SYSTEM)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(500)
            )
        ).all()
        messages = [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "text": r.text,
                "direction": r.direction.value,
                "sender_user_id": r.sender_user_id,
            }
            for r in reversed(rows)
        ]
        line = json.dumps({"chat": {"id": cid}, "messages": messages}, ensure_ascii=False)
        size += len(line.encode()) + 1
        if size > MAX_BYTES:
            raise AppError("too_large", "Слишком много текста. Выберите меньше диалогов.", 413)
        lines.append(line)
    rid = "crm-prepare-" + str(uuid4())
    db.add(
        AIRequest(
            id=rid,
            actor_id=actor.id,
            path="__prepare_export__",
            body={
                "archive": base64.b64encode("\n".join(lines).encode()).decode("ascii"),
                "per_chat_limit": 10,
            },
        )
    )
    db.add(
        AIAudit(
            actor_id=actor.id,
            action="prepare-chats",
            status="queued",
            data={"request_id": rid, "chat_ids": list(dict.fromkeys(body.chat_ids))},
        )
    )
    await db.commit()
    return {"request_id": rid, "status": "queued"}
