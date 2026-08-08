"""Срок ответа по требованию ФНС: PDF-текст + рабочие дни от даты получения."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO

# «В течение 5 рабочих дней со дня получения…»
_WORKING_DAYS_RE = re.compile(
    r"в\s+течение\s+(\d{1,2})\s+рабоч\w*\s+дн",
    re.IGNORECASE,
)
# Явная дата вида 30.07.2026 / 2026-07-30 рядом со «срок»
_EXPLICIT_DUE_RE = re.compile(
    r"(?:срок(?:\s+ответа|\s+представления|\s+исполнения)?|представить\s+не\s+позднее)"
    r"[^\d]{0,40}"
    r"(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_DATE_TOKEN_RE = re.compile(r"\b(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2})\b")

DEFAULT_RESPONSE_WORKING_DAYS = 5


@dataclass(frozen=True)
class ParsedRequirementDeadline:
    response_due_date: date | None
    working_days: int | None
    source: str  # sbis | pdf_date | pdf_working_days | default_working_days | none
    raw_excerpt: str | None = None


def add_working_days(start: date, days: int) -> date:
    """Прибавить N рабочих дней (пн–пт), отсчёт со следующего календарного дня."""
    if days <= 0:
        return start
    cur = start
    left = days
    while left > 0:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            left -= 1
    return cur


def parse_date_value(raw: str | None) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    if " " in s:
        s = s.split(" ", 1)[0].strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            token = s[:8] if fmt == "%Y%m%d" else s[:10]
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def extract_pdf_text(pdf_bytes: bytes, *, max_pages: int = 8) -> str:
    if not pdf_bytes.startswith(b"%PDF"):
        return ""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return ""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        return ""
    chunks: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def _normalize_text(text: str) -> str:
    return (
        (text or "")
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u00b4", "")
        .replace("⁴", "")
        .replace("⁵", "")
        .replace("⁶", "")
        .replace("⁷", "")
    )


def parse_working_days_from_text(text: str) -> int | None:
    blob = _normalize_text(text)
    match = _WORKING_DAYS_RE.search(blob)
    if not match:
        return None
    try:
        days = int(match.group(1))
    except ValueError:
        return None
    if 1 <= days <= 30:
        return days
    return None


def parse_explicit_due_from_text(text: str) -> date | None:
    blob = _normalize_text(text)
    match = _EXPLICIT_DUE_RE.search(blob)
    if match:
        return parse_date_value(match.group(1))
    # Fallback: первая дата после слова «срок» в окне 80 символов
    for m in re.finditer(r"срок", blob, flags=re.IGNORECASE):
        window = blob[m.start() : m.start() + 80]
        token = _DATE_TOKEN_RE.search(window)
        if token:
            return parse_date_value(token.group(1))
    return None


def resolve_response_due_date(
    *,
    existing: date | None,
    received_on: date | None,
    pdf_bytes: bytes | None = None,
    pdf_text: str | None = None,
    default_working_days: int = DEFAULT_RESPONSE_WORKING_DAYS,
) -> ParsedRequirementDeadline:
    """Приоритет: СБИС → явная дата в PDF → N раб.дней из PDF → default 5 раб.дней."""
    if existing is not None:
        return ParsedRequirementDeadline(
            response_due_date=existing,
            working_days=None,
            source="sbis",
        )

    text = pdf_text if pdf_text is not None else (
        extract_pdf_text(pdf_bytes) if pdf_bytes else ""
    )
    explicit = parse_explicit_due_from_text(text) if text else None
    if explicit is not None:
        return ParsedRequirementDeadline(
            response_due_date=explicit,
            working_days=None,
            source="pdf_date",
            raw_excerpt=text[:240] if text else None,
        )

    working_days = parse_working_days_from_text(text) if text else None
    source = "pdf_working_days" if working_days is not None else "default_working_days"
    days = working_days if working_days is not None else default_working_days
    if received_on is None:
        return ParsedRequirementDeadline(
            response_due_date=None,
            working_days=days,
            source="none",
            raw_excerpt=text[:240] if text else None,
        )
    return ParsedRequirementDeadline(
        response_due_date=add_working_days(received_on, days),
        working_days=days,
        source=source,
        raw_excerpt=text[:240] if text else None,
    )
