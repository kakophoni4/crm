"""Parse SBIS KV/IV receipt PDFs (КНД 1166002) for INN / period / name."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

_INN_RE = re.compile(r"\b(\d{10}|\d{12})\b")
_KPP_RE = re.compile(r"\b(\d{9})\b")
_PERIOD_RE_FULL = re.compile(
    r"(?:за\s+)?([1-4])\s*квартал[,.\s]+20(\d{2})\s*(?:год|г\.?)?",
    re.IGNORECASE,
)
_PERIOD_RE_SHORT = re.compile(
    r"(?:за\s+)?([1-4])\s*квартал[,.\s]+(\d{2})\s*(?:год|г\.?)",
    re.IGNORECASE,
)
_NAME_PAREN_RE = re.compile(r"\(([^)]+)\)\s*\.pdf$", re.IGNORECASE)
_OOO_NAME_RE = re.compile(
    r'(?:Общество\s+с\s+ограниченной\s+ответственностью|ООО)\s*[«"“]?([^»"”\n]+)[»"”]?',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedReceiptPdf:
    supplier_inn: str | None
    supplier_kpp: str | None
    supplier_name: str | None
    period_code: str | None
    doc_kind: str  # receipt | notice
    parsed_name: str | None
    raw_text: str


def detect_doc_kind(filename: str) -> str:
    lower = filename.casefold()
    if "извещение" in lower or "iv" in lower.split():
        return "notice"
    if "квитанция" in lower or "kv" in lower.split():
        return "receipt"
    if "ввод" in lower:
        return "notice"
    if "прием" in lower or "приём" in lower:
        return "receipt"
    return "receipt"


def short_name_from_filename(filename: str) -> str | None:
    match = _NAME_PAREN_RE.search(filename.strip())
    if match is None:
        return None
    name = match.group(1).strip()
    return name or None


def period_code_from_text(text: str) -> str | None:
    """Extract OPT period like 2/26 from «2 квартал 2026 год».

    Prefer explicit 20XX so we do not pick VAT rate «22» as the year.
    """
    for pattern in (_PERIOD_RE_FULL, _PERIOD_RE_SHORT):
        match = pattern.search(text)
        if match is None:
            continue
        quarter_s, yy_s = match.groups()
        yy = int(yy_s)
        # Business window: 2020–2035
        if yy < 20 or yy > 35:
            continue
        return f"{int(quarter_s)}/{yy_s}"
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pypdf is required to parse receipt PDFs") from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def parse_receipt_pdf(pdf_bytes: bytes, *, filename: str) -> ParsedReceiptPdf:
    text = extract_pdf_text(pdf_bytes) if pdf_bytes.startswith(b"%PDF") else ""
    doc_kind = detect_doc_kind(filename)
    short = short_name_from_filename(filename)

    supplier_inn: str | None = None
    supplier_kpp: str | None = None
    # Prefer INN near "ИНН" label when present.
    inn_labeled = re.search(r"ИНН[^\d]{0,20}(\d{10}|\d{12})", text, re.IGNORECASE)
    if inn_labeled:
        supplier_inn = inn_labeled.group(1)
    else:
        inns = _INN_RE.findall(text)
        # Skip tax-authority codes that look like 4-digit; take first 10/12 digit.
        for candidate in inns:
            if len(candidate) in (10, 12):
                supplier_inn = candidate
                break

    kpp_labeled = re.search(r"КПП[^\d]{0,20}(\d{9})", text, re.IGNORECASE)
    if kpp_labeled:
        supplier_kpp = kpp_labeled.group(1)
    elif supplier_inn:
        # First 9-digit after INN often is KPP.
        after = text.find(supplier_inn)
        if after >= 0:
            kpps = _KPP_RE.findall(text[after : after + 80])
            if kpps:
                supplier_kpp = kpps[0]

    name_match = _OOO_NAME_RE.search(text)
    supplier_name = name_match.group(1).strip() if name_match else None
    if supplier_name:
        supplier_name = f'ООО "{supplier_name.strip()}"'
    elif short:
        supplier_name = short

    period_code = period_code_from_text(text)

    return ParsedReceiptPdf(
        supplier_inn=supplier_inn,
        supplier_kpp=supplier_kpp,
        supplier_name=supplier_name,
        period_code=period_code,
        doc_kind=doc_kind,
        parsed_name=short,
        raw_text=text[:4000],
    )
