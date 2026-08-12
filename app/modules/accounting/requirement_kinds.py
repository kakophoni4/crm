"""Classify sbis-norm requirement-like documents."""

from __future__ import annotations

from typing import Any

DOC_KIND_ACCOUNT_BLOCK = "account_block"


def is_account_block_notice(
    *,
    title: str | None = None,
    filename: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Уведомление о блокировке счёта: факт по компании, без /reply/.

    Признаки: в doc_title есть «блокировке счета» / «блокировка»,
    и/или storage_file_name заканчивается на .stub.
    Файл при этом обычно пустой или отсутствует — ingest без PDF.
    """
    meta = metadata if isinstance(metadata, dict) else {}
    if meta.get("doc_kind") == DOC_KIND_ACCOUNT_BLOCK:
        return True
    name = str(filename or meta.get("storage_file_name") or "").strip().lower()
    if name.endswith(".stub"):
        return True
    text = str(title or "").lower().replace("ё", "е")
    return "блокировк" in text
