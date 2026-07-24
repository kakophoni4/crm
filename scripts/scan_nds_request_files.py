#!/usr/bin/env python3
"""Scan storage for partner applications and sum CRM «к оплате».

Detection by CONTENT only (not filename):
  - nds_request: Заявка на НДС (стоимость покупки / ИНН продавца)
  - partner_forma: Forma_zayavki (сумма в т.ч. НДС / ИНН организации)

OPT upload format and CRM registry exports are skipped on purpose.
Files named «Раздел-9» are usually FNS books — SKIP is expected unless they
actually contain partner headers.

Sources (deduped by storage_key):
  - uploaded_files
  - group_chat_files
  - message attachments (JSON)

State / resume:
  Results are stored in a JSON state file (storage_key → status) so re-runs
  skip already processed keys. Headers of SKIP files are kept for audit.

Dedup (default on):
  Totals count unique registry LINES across all files:
  (buyer_inn, supplier_inn, document_date, amount).
  Duplicate uploads (Forma_заявки.xls + «запрос».xls) do not inflate к_оплате.

Speed:
  Downloads/parses in parallel (--workers, default 16).
  Obvious FNS book names (Раздел-9 / книга покупок) skip download by default.

Usage on VPS:
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/scan_nds_request_files.py --force --workers 16
  docker exec -e PYTHONUNBUFFERED=1 crm-staging-api \\
    python scripts/scan_nds_request_files.py --resume
  docker exec crm-staging-api python scripts/scan_nds_request_files.py \\
    --contact-like 'пит' --dump-headers
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.modules.db.models.opt_unit import OptUnit  # noqa: E402
from app.modules.leads.opt.nds_request_parser import (  # noqa: E402
    lines_for_pricing,
    parse_nds_request_workbook,
    peek_workbook_headers,
)
from app.modules.leads.opt.parser import ParsedApplication, ParsedApplicationLine  # noqa: E402
from app.modules.leads.opt.pricing import compute_order_pricing  # noqa: E402
from app.shared.db import get_session_factory  # noqa: E402
from app.shared.storage import get_file_storage  # noqa: E402

_DEFAULT_STATE = Path("/tmp/crm_nds_scan_state.json")


@dataclass
class FileHit:
    source: str
    name: str
    storage_key: str | None
    buyer_inn: str
    lines: int
    lines_unique: int
    lines_dup: int
    volume: Decimal
    commission: Decimal
    sheet_name: str | None
    form_kind: str | None


def _line_fingerprint(line: ParsedApplicationLine) -> str:
    """Stable key for one registry row across duplicate files."""
    amount = Decimal(str(line.amount)).quantize(Decimal("0.01"))
    return (
        f"{line.buyer_inn}|{line.supplier_inn}|"
        f"{line.document_date.isoformat()}|{amount}"
    )


def _split_unique_lines(
    lines: list[ParsedApplicationLine],
    seen: set[str],
) -> tuple[list[ParsedApplicationLine], list[str], int]:
    unique: list[ParsedApplicationLine] = []
    keys: list[str] = []
    dup_n = 0
    for line in lines:
        key = _line_fingerprint(line)
        if key in seen:
            dup_n += 1
            continue
        seen.add(key)
        unique.append(line)
        keys.append(key)
    return unique, keys, dup_n


_JUNK_NAME_RE = re.compile(
    r"(раздел[\s_-]*9|книга\s*покупок|книга\s*продаж)",
    re.IGNORECASE,
)


def _is_obvious_junk_name(name: str) -> bool:
    """FNS books — almost never partner forms; skip S3 download."""
    return bool(_JUNK_NAME_RE.search(name.replace("ё", "е")))


@dataclass
class _FetchResult:
    cand: Candidate
    status: str  # error | skip | empty | ready
    reason: str | None = None
    form_kind: str | None = None
    sheet_name: str | None = None
    headers: list[dict[str, object]] = field(default_factory=list)
    application: ParsedApplication | None = None


@dataclass(frozen=True)
class Candidate:
    storage_key: str
    name: str
    source: str
    created_at: str | None = None
    contact_name: str | None = None


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "files": {}}
    if not isinstance(data, dict):
        return {"version": 1, "files": {}}
    files = data.get("files")
    if not isinstance(files, dict):
        data["files"] = {}
    return data


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


async def _load_units() -> dict[str, OptUnit]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        orm_rows = (await session.execute(select(OptUnit))).scalars().all()
        return {str(unit.inn): unit for unit in orm_rows}


def _price(application, units: dict[str, OptUnit]) -> tuple[Decimal, Decimal]:
    volume, commission, _breakdown = compute_order_pricing(
        lines_for_pricing(application),
        units,
    )
    return volume, commission


async def _collect_candidates(
    *,
    limit: int | None,
    contact_like: str | None,
    name_like: str | None,
) -> list[Candidate]:
    """Newest spreadsheets first; optional filters for chat contact / filename."""
    session_factory = get_session_factory()
    found: dict[str, Candidate] = {}
    contact_pat = f"%{contact_like.strip()}%" if contact_like else None
    name_pat = f"%{name_like.strip()}%" if name_like else None

    async with session_factory() as session:
        # group_chat_files — primary source for manager chat forms
        gsql = """
            SELECT
              g.storage_key,
              g.original_name AS name,
              'group_chat_files' AS source,
              g.created_at::text AS created_at,
              COALESCE(ct.full_name, g.sender_display_name, '') AS contact_name
            FROM group_chat_files g
            LEFT JOIN chats c ON c.id = g.chat_id
            LEFT JOIN contacts ct ON ct.id = c.contact_id
            WHERE (
                lower(g.original_name) LIKE '%.xlsx'
                OR lower(g.original_name) LIKE '%.xlsm'
                OR lower(g.original_name) LIKE '%.xls'
                OR g.mime_type ILIKE '%spreadsheet%'
                OR g.mime_type ILIKE '%excel%'
            )
        """
        params: dict[str, object] = {}
        if contact_pat:
            gsql += """
              AND (
                ct.full_name ILIKE :contact_pat
                OR g.sender_display_name ILIKE :contact_pat
              )
            """
            params["contact_pat"] = contact_pat
        if name_pat:
            gsql += " AND g.original_name ILIKE :name_pat"
            params["name_pat"] = name_pat
        gsql += " ORDER BY g.created_at DESC NULLS LAST, g.id DESC"

        for row in (await session.execute(text(gsql), params)).mappings().all():
            key = str(row["storage_key"] or "").strip()
            if not key or key in found:
                continue
            found[key] = Candidate(
                storage_key=key,
                name=str(row["name"] or key),
                source=str(row["source"]),
                created_at=str(row["created_at"] or "") or None,
                contact_name=str(row["contact_name"] or "") or None,
            )

        if not contact_pat:
            # uploaded_files + message attachments (global), newest first
            u_sql = """
                SELECT storage_key, original_name AS name, 'uploaded_files' AS source,
                       created_at::text AS created_at, NULL::text AS contact_name
                FROM uploaded_files
                WHERE (
                    lower(original_name) LIKE '%.xlsx'
                    OR lower(original_name) LIKE '%.xlsm'
                    OR lower(original_name) LIKE '%.xls'
                    OR mime_type ILIKE '%spreadsheet%'
                    OR mime_type ILIKE '%excel%'
                )
            """
            u_params: dict[str, object] = {}
            if name_pat:
                u_sql += " AND original_name ILIKE :name_pat"
                u_params["name_pat"] = name_pat
            u_sql += " ORDER BY created_at DESC NULLS LAST, id DESC"
            for row in (await session.execute(text(u_sql), u_params)).mappings().all():
                key = str(row["storage_key"] or "").strip()
                if not key or key in found:
                    continue
                found[key] = Candidate(
                    storage_key=key,
                    name=str(row["name"] or key),
                    source="uploaded_files",
                    created_at=str(row["created_at"] or "") or None,
                )

            m_sql = """
                SELECT
                  att->>'storage_key' AS storage_key,
                  COALESCE(att->>'filename', att->>'name', 'attachment.xlsx') AS name,
                  'message_attachments' AS source,
                  m.created_at::text AS created_at,
                  NULL::text AS contact_name
                FROM messages m
                CROSS JOIN LATERAL jsonb_array_elements(
                  CASE WHEN jsonb_typeof(m.attachments) = 'array'
                       THEN m.attachments ELSE '[]'::jsonb END
                ) AS att
                WHERE att->>'storage_key' IS NOT NULL
                  AND att->>'storage_key' <> ''
                  AND (
                    lower(COALESCE(att->>'filename', att->>'name', '')) LIKE '%.xlsx'
                    OR lower(COALESCE(att->>'filename', att->>'name', '')) LIKE '%.xlsm'
                    OR lower(COALESCE(att->>'filename', att->>'name', '')) LIKE '%.xls'
                    OR lower(COALESCE(att->>'mime', '')) LIKE '%spreadsheet%'
                    OR lower(COALESCE(att->>'mime', '')) LIKE '%excel%'
                  )
            """
            m_params: dict[str, object] = {}
            if name_pat:
                m_sql += """
                  AND COALESCE(att->>'filename', att->>'name', '') ILIKE :name_pat
                """
                m_params["name_pat"] = name_pat
            m_sql += " ORDER BY m.created_at DESC NULLS LAST, m.id DESC"
            for row in (await session.execute(text(m_sql), m_params)).mappings().all():
                key = str(row["storage_key"] or "").strip()
                if not key or key in found:
                    continue
                found[key] = Candidate(
                    storage_key=key,
                    name=str(row["name"] or key),
                    source="message_attachments",
                    created_at=str(row["created_at"] or "") or None,
                )

    items = list(found.values())
    items.sort(key=lambda c: c.created_at or "", reverse=True)
    if limit is not None:
        items = items[:limit]
    return items


async def _scan_local(path: Path, units: dict[str, OptUnit]) -> list[FileHit]:
    content = path.read_bytes()
    parsed = parse_nds_request_workbook(content)
    if not parsed.matched or parsed.application is None:
        _log(f"[1/1 100%] [local] {path.name!r} → SKIP ({parsed.reason})")
        for row in peek_workbook_headers(content):
            _log(f"  header_peek: {row}")
        return []
    seen: set[str] = set()
    unique, _keys, dup_n = _split_unique_lines(parsed.application.lines, seen)
    app = ParsedApplication(buyer_inn=parsed.application.buyer_inn, lines=unique)
    volume, commission = _price(app, units)
    _log(
        f"[1/1 100%] [local] {path.name!r} → HIT kind={parsed.form_kind} "
        f"buyer={parsed.application.buyer_inn} "
        f"lines={len(unique)}/{len(parsed.application.lines)} "
        f"(dup={dup_n}) volume={_money(volume)} commission={_money(commission)}",
    )
    return [
        FileHit(
            source="local",
            name=path.name,
            storage_key=None,
            buyer_inn=parsed.application.buyer_inn,
            lines=len(parsed.application.lines),
            lines_unique=len(unique),
            lines_dup=dup_n,
            volume=volume,
            commission=commission,
            sheet_name=parsed.sheet_name,
            form_kind=parsed.form_kind,
        ),
    ]


async def _fetch_one(
    *,
    sem: asyncio.Semaphore,
    storage: Any,
    cand: Candidate,
    dump_headers: bool,
    fast_skip_names: bool,
    progress: dict[str, Any],
    total_work: int,
) -> _FetchResult:
    async with sem:
        async with progress["lock"]:
            progress["n"] += 1
            n = progress["n"]
        pct = (100 * n) // max(total_work, 1)
        who = f" contact={cand.contact_name!r}" if cand.contact_name else ""
        prefix = f"[dl {n}/{total_work} ~{pct}%] [{cand.source}] {cand.name!r}{who}"

        if fast_skip_names and _is_obvious_junk_name(cand.name):
            _log(f"{prefix} → SKIP (name_prefilter)")
            return _FetchResult(
                cand=cand,
                status="skip",
                reason="name_prefilter",
            )

        try:
            content, _ctype = await storage.get_bytes(cand.storage_key)
        except Exception as exc:  # noqa: BLE001
            _log(f"{prefix} → DOWNLOAD_FAIL ({exc})")
            return _FetchResult(
                cand=cand,
                status="error",
                reason=f"download_fail: {exc}",
            )

        parsed = await asyncio.to_thread(parse_nds_request_workbook, content)
        if not parsed.matched:
            reason = parsed.reason or "header_not_found"
            headers: list[dict[str, object]] = []
            if dump_headers:
                headers = await asyncio.to_thread(peek_workbook_headers, content)
                _log(f"{prefix} → SKIP ({reason})")
                for row in headers[:3]:
                    _log(f"  headers: {row}")
            else:
                _log(f"{prefix} → SKIP ({reason})")
            return _FetchResult(
                cand=cand,
                status="skip",
                reason=reason,
                headers=headers[:3],
            )

        if parsed.application is None:
            _log(
                f"{prefix} → EMPTY kind={parsed.form_kind} "
                f"sheet={parsed.sheet_name!r} ({parsed.reason})",
            )
            return _FetchResult(
                cand=cand,
                status="empty",
                reason=parsed.reason,
                form_kind=parsed.form_kind,
                sheet_name=parsed.sheet_name,
            )

        _log(
            f"{prefix} → PARSED kind={parsed.form_kind} "
            f"buyer={parsed.application.buyer_inn} "
            f"lines={len(parsed.application.lines)}",
        )
        return _FetchResult(
            cand=cand,
            status="ready",
            form_kind=parsed.form_kind,
            sheet_name=parsed.sheet_name,
            application=parsed.application,
        )


async def _scan_storage(
    *,
    limit: int | None,
    resume: bool,
    force: bool,
    dump_headers: bool,
    state_path: Path,
    contact_like: str | None,
    name_like: str | None,
    dedupe_lines: bool,
    workers: int,
    fast_skip_names: bool,
) -> tuple[list[FileHit], int, int, int, int, int]:
    units = await _load_units()
    candidates = await _collect_candidates(
        limit=limit,
        contact_like=contact_like,
        name_like=name_like,
    )
    storage = get_file_storage()
    state = _load_state(state_path)
    files_state: dict[str, Any] = state.setdefault("files", {})

    hits: list[FileHit] = []
    scanned = 0
    errors = 0
    empty_templates = 0
    skipped = 0
    resumed = 0
    dup_files = 0
    total = len(candidates)
    running_commission = Decimal("0")
    running_volume = Decimal("0")
    seen_lines: set[str] = set()
    candidate_keys = {c.storage_key for c in candidates}

    for sk, meta in files_state.items():
        if not isinstance(meta, dict):
            continue
        if force and sk in candidate_keys:
            continue
        if meta.get("status") not in {"hit", "dup"}:
            continue
        for k in meta.get("line_keys") or []:
            seen_lines.add(str(k))
        if meta.get("status") == "hit" and sk not in candidate_keys:
            try:
                running_commission += Decimal(str(meta.get("commission") or 0))
                running_volume += Decimal(str(meta.get("volume") or 0))
            except Exception:
                pass
    if resume and not force:
        raw_keys = state.get("line_keys")
        if isinstance(raw_keys, list):
            seen_lines.update(str(k) for k in raw_keys if k)

    to_work: list[Candidate] = []
    for cand in candidates:
        prev = files_state.get(cand.storage_key) if isinstance(files_state, dict) else None
        if (
            resume
            and not force
            and isinstance(prev, dict)
            and prev.get("status") in {"hit", "skip", "empty", "error", "dup"}
        ):
            resumed += 1
            if prev.get("status") == "hit":
                try:
                    running_commission += Decimal(str(prev.get("commission") or 0))
                    running_volume += Decimal(str(prev.get("volume") or 0))
                except Exception:
                    pass
            continue
        to_work.append(cand)

    workers = max(1, int(workers))
    _log(
        f"Candidates: {total} | to_scan={len(to_work)} | workers={workers} "
        f"| state={state_path} | resume={resume} force={force} "
        f"dedupe_lines={dedupe_lines} fast_skip_names={fast_skip_names} "
        f"| seed_unique_lines={len(seen_lines)}",
    )
    if contact_like:
        _log(f"Filter contact_like={contact_like!r}")
    if name_like:
        _log(f"Filter name_like={name_like!r}")
    _log("Download/parse parallel; dedup applied in candidate order.")

    sem = asyncio.Semaphore(workers)
    progress: dict[str, Any] = {"n": 0, "lock": asyncio.Lock()}
    fetched = await asyncio.gather(
        *[
            _fetch_one(
                sem=sem,
                storage=storage,
                cand=cand,
                dump_headers=dump_headers,
                fast_skip_names=fast_skip_names,
                progress=progress,
                total_work=len(to_work),
            )
            for cand in to_work
        ],
    )

    # Apply in original candidate order so dedup is deterministic.
    by_key = {fr.cand.storage_key: fr for fr in fetched}
    for cand in to_work:
        fr = by_key[cand.storage_key]
        scanned += 1
        who = f" contact={cand.contact_name!r}" if cand.contact_name else ""
        prefix = (
            f"[sum {scanned}/{len(to_work)}] [{cand.source}] {cand.name!r}{who}"
        )

        if fr.status == "error":
            errors += 1
            files_state[cand.storage_key] = {
                "status": "error",
                "reason": fr.reason,
                "name": cand.name,
                "source": cand.source,
                "scanned_at": _utc_now(),
            }
            continue

        if fr.status == "skip":
            skipped += 1
            files_state[cand.storage_key] = {
                "status": "skip",
                "reason": fr.reason,
                "name": cand.name,
                "source": cand.source,
                "contact_name": cand.contact_name,
                "headers": fr.headers[:3],
                "scanned_at": _utc_now(),
            }
            continue

        if fr.status == "empty":
            empty_templates += 1
            files_state[cand.storage_key] = {
                "status": "empty",
                "reason": fr.reason,
                "form_kind": fr.form_kind,
                "name": cand.name,
                "source": cand.source,
                "scanned_at": _utc_now(),
            }
            continue

        assert fr.application is not None
        raw_n = len(fr.application.lines)
        if dedupe_lines:
            unique, line_keys, dup_n = _split_unique_lines(
                fr.application.lines,
                seen_lines,
            )
        else:
            unique = list(fr.application.lines)
            line_keys = [_line_fingerprint(ln) for ln in unique]
            dup_n = 0
            for k in line_keys:
                seen_lines.add(k)

        if not unique:
            dup_files += 1
            files_state[cand.storage_key] = {
                "status": "dup",
                "form_kind": fr.form_kind,
                "buyer_inn": fr.application.buyer_inn,
                "lines": raw_n,
                "lines_unique": 0,
                "lines_dup": dup_n,
                "volume": "0",
                "commission": "0",
                "line_keys": [],
                "name": cand.name,
                "source": cand.source,
                "contact_name": cand.contact_name,
                "sheet": fr.sheet_name,
                "scanned_at": _utc_now(),
            }
            _log(
                f"{prefix} → DUP kind={fr.form_kind} "
                f"buyer={fr.application.buyer_inn} lines={raw_n} "
                f"| unique_к_оплате={_money(running_commission)}",
            )
            continue

        app = ParsedApplication(
            buyer_inn=fr.application.buyer_inn,
            lines=unique,
        )
        volume, commission = _price(app, units)
        running_commission += commission
        running_volume += volume
        hits.append(
            FileHit(
                source=cand.source,
                name=cand.name,
                storage_key=cand.storage_key,
                buyer_inn=fr.application.buyer_inn,
                lines=raw_n,
                lines_unique=len(unique),
                lines_dup=dup_n,
                volume=volume,
                commission=commission,
                sheet_name=fr.sheet_name,
                form_kind=fr.form_kind,
            ),
        )
        files_state[cand.storage_key] = {
            "status": "hit",
            "form_kind": fr.form_kind,
            "buyer_inn": fr.application.buyer_inn,
            "lines": raw_n,
            "lines_unique": len(unique),
            "lines_dup": dup_n,
            "volume": str(volume),
            "commission": str(commission),
            "line_keys": line_keys,
            "name": cand.name,
            "source": cand.source,
            "contact_name": cand.contact_name,
            "sheet": fr.sheet_name,
            "scanned_at": _utc_now(),
        }
        _log(
            f"{prefix} → HIT kind={fr.form_kind} "
            f"buyer={fr.application.buyer_inn} "
            f"lines={len(unique)}/{raw_n} (dup={dup_n}) "
            f"volume={_money(volume)} commission={_money(commission)} "
            f"| unique_к_оплате={_money(running_commission)} "
            f"(hits={len(hits)} dup_files={dup_files} empty={empty_templates} "
            f"skip={skipped} resume_skip={resumed} err={errors})",
        )

        if scanned % 50 == 0:
            state["files"] = files_state
            state["updated_at"] = _utc_now()
            _save_state(state_path, state)

    all_line_keys: set[str] = set()
    global_commission = Decimal("0")
    global_volume = Decimal("0")
    for meta in files_state.values():
        if not isinstance(meta, dict):
            continue
        for k in meta.get("line_keys") or []:
            all_line_keys.add(str(k))
        if meta.get("status") == "hit":
            try:
                global_commission += Decimal(str(meta.get("commission") or 0))
                global_volume += Decimal(str(meta.get("volume") or 0))
            except Exception:
                pass

    state["files"] = files_state
    state["line_keys"] = sorted(all_line_keys)
    state["unique_volume"] = str(global_volume)
    state["unique_commission"] = str(global_commission)
    state["updated_at"] = _utc_now()
    _save_state(state_path, state)
    _log(
        f"State saved: {state_path} "
        f"(files={len(files_state)} unique_lines={len(all_line_keys)})",
    )
    _log(
        f"UNIQUE TOTALS (all state hits): volume={_money(global_volume)} "
        f"к_оплате={_money(global_commission)} lines={len(all_line_keys)}",
    )
    return hits, scanned, errors, empty_templates, resumed, dup_files


async def _run(
    *,
    local_file: str | None,
    limit: int | None,
    resume: bool,
    force: bool,
    dump_headers: bool,
    state_file: str,
    contact_like: str | None,
    name_like: str | None,
    show_state_summary: bool,
    dedupe_lines: bool,
    workers: int,
    fast_skip_names: bool,
) -> int:
    state_path = Path(state_file)
    units = await _load_units()
    empty_templates = 0
    resumed = 0
    dup_files = 0
    if local_file:
        hits = await _scan_local(Path(local_file), units)
        scanned = 1
        errors = 0
    else:
        hits, scanned, errors, empty_templates, resumed, dup_files = await _scan_storage(
            limit=limit,
            resume=resume,
            force=force,
            dump_headers=dump_headers,
            state_path=state_path,
            contact_like=contact_like,
            name_like=name_like,
            dedupe_lines=dedupe_lines,
            workers=workers,
            fast_skip_names=fast_skip_names,
        )

    if show_state_summary and state_path.exists():
        st = _load_state(state_path)
        files = st.get("files") or {}
        by_status: dict[str, int] = {}
        skip_reasons: dict[str, int] = {}
        for meta in files.values():
            if not isinstance(meta, dict):
                continue
            status = str(meta.get("status") or "?")
            by_status[status] = by_status.get(status, 0) + 1
            if status == "skip":
                reason = str(meta.get("reason") or "?")
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        _log("")
        _log("=== STATE SUMMARY ===")
        _log(f"state_file: {state_path}")
        for k, v in sorted(by_status.items()):
            _log(f"  {k}: {v}")
        uniq_c = st.get("unique_commission")
        uniq_v = st.get("unique_volume")
        uniq_n = len(st.get("line_keys") or [])
        if uniq_c is not None:
            _log(
                f"unique_registry: lines={uniq_n} "
                f"volume={_money(Decimal(str(uniq_v or 0)))} "
                f"к_оплате={_money(Decimal(str(uniq_c or 0)))}",
            )
        if skip_reasons:
            _log("skip reasons:")
            for k, v in sorted(skip_reasons.items(), key=lambda x: -x[1])[:15]:
                _log(f"  {k}: {v}")
        near = []
        for meta in files.values():
            if not isinstance(meta, dict) or meta.get("status") != "skip":
                continue
            for h in meta.get("headers") or []:
                blob = str(h.get("blob") or "")
                if "инн" in blob and ("сумма" in blob or "стоимость" in blob):
                    near.append((meta.get("name"), h))
                    break
        if near:
            _log("SKIP but header mentions ИНН+сумма (review):")
            for name, h in near[:20]:
                _log(f"  - {name}: {h.get('headers')}")

    _log("")
    _log("=== SUMMARY (unique registry lines) ===")
    _log(f"scanned_new: {scanned}")
    _log(f"resume_skipped: {resumed}")
    _log(f"files_with_new_lines (this run): {len(hits)}")
    _log(f"files_all_duplicate: {dup_files}")
    _log(f"empty_templates: {empty_templates}")
    _log(f"download_errors: {errors}")
    total_volume = sum((h.volume for h in hits), Decimal("0"))
    total_commission = sum((h.commission for h in hits), Decimal("0"))
    total_uniq_lines = sum((h.lines_unique for h in hits), 0)
    total_raw_lines = sum((h.lines for h in hits), 0)
    _log(
        f"new_unique_lines (this run): {total_uniq_lines} "
        f"(raw in those files: {total_raw_lines})",
    )
    _log(f"unique_volume (this run): {_money(total_volume)} ₽")
    _log(f"unique_к_оплате (this run): {_money(total_commission)} ₽")
    if hits:
        _log("")
        _log("per file (new unique lines only):")
        for hit in hits:
            _log(
                f"  - [{hit.source}] kind={hit.form_kind} buyer={hit.buyer_inn} "
                f"lines={hit.lines_unique}/{hit.lines} (dup={hit.lines_dup}) "
                f"volume={_money(hit.volume)} "
                f"к_оплате={_money(hit.commission)} | {hit.name}",
            )
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Scan ЗАПРОС НДС / Forma files in storage by CONTENT",
    )
    parser.add_argument("--local-file", help="Parse a single local xlsx instead of storage")
    parser.add_argument("--limit", type=int, default=None, help="Max spreadsheet candidates")
    parser.add_argument(
        "--state-file",
        default=str(_DEFAULT_STATE),
        help=f"JSON state path (default {_DEFAULT_STATE})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip storage_keys already recorded in state-file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rescan even if key exists in state-file",
    )
    parser.add_argument(
        "--dump-headers",
        action="store_true",
        help="Print first header-like row for every SKIP",
    )
    parser.add_argument(
        "--contact-like",
        default=None,
        help="Only group_chat_files for contact/sender ILIKE %%value%% (e.g. пит)",
    )
    parser.add_argument(
        "--name-like",
        default=None,
        help="Only filenames ILIKE %%value%%",
    )
    parser.add_argument(
        "--state-summary",
        action="store_true",
        help="Print aggregated state stats after run",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable line-level dedup (sum every file as-is)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Parallel S3 download/parse workers (default 16)",
    )
    parser.add_argument(
        "--no-fast-skip-names",
        action="store_true",
        help="Do not skip Раздел-9 / книга покупок by filename before download",
    )
    parser.add_argument(
        "--verbose-skip",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            _run(
                local_file=args.local_file,
                limit=args.limit,
                resume=args.resume,
                force=args.force,
                dump_headers=args.dump_headers or bool(args.verbose_skip),
                state_file=args.state_file,
                contact_like=args.contact_like,
                name_like=args.name_like,
                show_state_summary=args.state_summary or True,
                dedupe_lines=not args.no_dedupe,
                workers=args.workers,
                fast_skip_names=not args.no_fast_skip_names,
            ),
        ),
    )


if __name__ == "__main__":
    main()
