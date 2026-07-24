#!/usr/bin/env python3
"""Audit NDS scan gaps: which SKIPs look like missed partner applications.

Reads /tmp/crm_nds_scan_state.json (or --state-file), lists suspicious SKIP/EMPTY
by filename, optionally re-downloads and peeks headers (--repeek).

Usage:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/audit_nds_scan_gaps.py
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/audit_nds_scan_gaps.py --repeek --limit 80
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.leads.opt.nds_request_parser import (  # noqa: E402
    parse_nds_request_workbook,
    peek_workbook_headers,
)
from app.shared.storage import get_file_storage  # noqa: E402

_DEFAULT_STATE = Path("/tmp/crm_nds_scan_state.json")

_SUSPICIOUS_NAME = re.compile(
    r"(заявк|forma|форм[аы]|реестр|запрос|nds|ндс|партнер|партнёр)",
    re.IGNORECASE,
)
_JUNK_NAME = re.compile(
    r"(раздел[\s_-]*[89]|книга\s*покупок|книга\s*продаж|сверк|конкурент|"
    r"каталог|имуществ|архив|\bарх\b)",
    re.IGNORECASE,
)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _classify_headers(headers: list[dict[str, Any]]) -> str:
    blob = " ".join(str(h.get("blob") or "") for h in headers).lower()
    cells = " ".join(
        " ".join(str(x) for x in (h.get("headers") or [])) for h in headers
    ).lower()
    text = f"{blob} {cells}"
    if not text.strip():
        return "no_headers"
    if "сумма без ндс" in text and ("№ документа" in text or "номер документа" in text):
        return "crm_registry_export"
    if "инн" in text and (
        "сумма покупок" in text
        or "сумма сделок" in text
        or "стоимость покупки" in text
        or "сумма (в т.ч" in text
        or "сумма в т.ч" in text
    ):
        return "LIKELY_PARTNER_MISSED"
    if "инн" in text and "сумма" in text:
        return "inn_plus_sum_review"
    if "инн" in text:
        return "has_inn_only"
    return "other"


async def _repeek(keys: list[tuple[str, dict[str, Any]]], *, limit: int) -> None:
    storage = get_file_storage()
    _log("")
    _log(f"=== REPEEK up to {limit} suspicious SKIP/EMPTY ===")
    classes: Counter[str] = Counter()
    missed: list[tuple[str, str, str]] = []
    n = 0
    for key, meta in keys:
        if n >= limit:
            break
        name = str(meta.get("name") or key)
        if _JUNK_NAME.search(name.replace("ё", "е")):
            continue
        if not _SUSPICIOUS_NAME.search(name.replace("ё", "е")):
            continue
        n += 1
        prefix = f"[{n}/{limit}] {name!r}"
        try:
            content, _ = await storage.get_bytes(key)
        except Exception as exc:  # noqa: BLE001
            _log(f"{prefix} → download_fail ({exc})")
            classes["download_fail"] += 1
            continue
        parsed = parse_nds_request_workbook(content)
        if parsed.matched:
            lines = len(parsed.application.lines) if parsed.application else 0
            _log(
                f"{prefix} → NOW_MATCHES kind={parsed.form_kind} "
                f"lines={lines} reason={parsed.reason}",
            )
            classes["now_matches_parser"] += 1
            missed.append((name, "now_matches_parser", str(parsed.form_kind)))
            continue
        headers = peek_workbook_headers(content)
        kind = _classify_headers(headers)
        classes[kind] += 1
        sample = (headers[0].get("headers") if headers else None) or headers
        _log(f"{prefix} → {kind} | {sample}")
        if kind in {"LIKELY_PARTNER_MISSED", "inn_plus_sum_review"}:
            missed.append((name, kind, str(sample)))

    _log("")
    _log("repeek class counts:")
    for k, v in classes.most_common():
        _log(f"  {k}: {v}")
    if missed:
        _log("")
        _log("NEED REVIEW (possible missed partner forms):")
        for name, kind, detail in missed[:40]:
            _log(f"  - [{kind}] {name}")
            _log(f"      {detail}")


async def _run(*, state_file: str, repeek: bool, limit: int) -> int:
    path = Path(state_file)
    if not path.exists():
        _log(f"state missing: {path}")
        return 1
    st = _load_state(path)
    files: dict[str, Any] = st.get("files") or {}
    by_status: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    hit_source: Counter[str] = Counter()
    suspicious_skip: list[tuple[str, dict[str, Any]]] = []
    junk_skip = 0
    empty_named: list[str] = []

    for key, meta in files.items():
        if not isinstance(meta, dict):
            continue
        status = str(meta.get("status") or "?")
        by_status[status] += 1
        src = str(meta.get("source") or "?")
        by_source[f"{status}:{src}"] += 1
        name = str(meta.get("name") or "")
        if status == "hit":
            hit_source[src] += 1
        if status == "skip":
            reason = str(meta.get("reason") or "?")
            by_reason[reason] += 1
            if _JUNK_NAME.search(name.replace("ё", "е")):
                junk_skip += 1
            elif _SUSPICIOUS_NAME.search(name.replace("ё", "е")):
                suspicious_skip.append((key, meta))
        if status == "empty" and _SUSPICIOUS_NAME.search(name.replace("ё", "е")):
            empty_named.append(name)

    _log("=== COVERAGE FROM STATE ===")
    _log(f"state: {path}")
    _log(f"updated_at: {st.get('updated_at')}")
    _log(f"unique_к_оплате: {st.get('unique_commission')}")
    _log(f"unique_volume: {st.get('unique_volume')}")
    _log(f"unique_lines: {len(st.get('line_keys') or [])}")
    _log("")
    _log("by status:")
    for k, v in by_status.most_common():
        _log(f"  {k}: {v}")
    _log("hits by source:")
    for k, v in hit_source.most_common():
        _log(f"  {k}: {v}")
    _log("skip reasons:")
    for k, v in by_reason.most_common():
        _log(f"  {k}: {v}")
    _log("")
    _log(
        "What THIS scan counts: partner Excel forms in "
        "group_chat_files + uploaded_files + message attachments "
        "(.xls/.xlsx) with known headers "
        "(Заявка на НДС / Forma / park zapros).",
    )
    _log(
        "Intentionally NOT counted: CRM registry exports, FNS Раздел-9, "
        "empty templates, PDF/DOC, duplicates of already counted lines.",
    )
    _log("")
    _log(f"SKIP with junk-like names: {junk_skip} (ok to ignore)")
    _log(f"SKIP with application-like names: {len(suspicious_skip)} ← audit these")
    _log(f"EMPTY with application-like names: {len(empty_named)}")

    _log("")
    _log("=== SUSPICIOUS SKIP (filename looks like заявка/форма/реестр) ===")
    for _key, meta in sorted(
        suspicious_skip,
        key=lambda x: str(x[1].get("name") or ""),
    )[:60]:
        _log(
            f"  - [{meta.get('reason')}] contact={meta.get('contact_name')!r} "
            f"| {meta.get('name')}",
        )
    if len(suspicious_skip) > 60:
        _log(f"  ... +{len(suspicious_skip) - 60} more")

    if empty_named:
        _log("")
        _log("=== EMPTY templates (header matched, no rows) sample ===")
        for name in sorted(set(empty_named))[:30]:
            _log(f"  - {name}")

    if repeek:
        await _repeek(suspicious_skip, limit=limit)
    else:
        _log("")
        _log(
            "Next: re-download suspicious SKIPs and classify headers:",
        )
        _log(
            "  python scripts/audit_nds_scan_gaps.py --repeek --limit 80",
        )
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Audit NDS scan coverage gaps")
    p.add_argument("--state-file", default=str(_DEFAULT_STATE))
    p.add_argument(
        "--repeek",
        action="store_true",
        help="Re-download suspicious SKIP files and classify headers",
    )
    p.add_argument("--limit", type=int, default=80, help="Max files to repeek")
    args = p.parse_args()
    raise SystemExit(
        asyncio.run(
            _run(state_file=args.state_file, repeek=args.repeek, limit=args.limit),
        ),
    )


if __name__ == "__main__":
    main()
