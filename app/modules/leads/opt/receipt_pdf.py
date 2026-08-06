"""Parse SBIS KV/IV receipt PDFs (КНД 1166002) for INN / period / name."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

_INN_RE = re.compile(r"\b(\d{10}|\d{12})\b")
_KPP_RE = re.compile(r"\b(\d{9})\b")
# Classic: «квитанция о приеме (Афина).pdf»
# New sbis-norm dumps: «извещение о вводе (Афина) 28-07-2026 8d54e4b7.pdf»
_NAME_PAREN_RE = re.compile(r"\(([^)]+)\)", re.IGNORECASE)
_SUFFIX_DATE_HASH_RE = re.compile(
    r"^(?P<head>.+?\))\s+"
    r"\d{2}[-./]\d{2}[-./]\d{4}"
    r"(?:\s+[0-9a-fA-F]{6,16})?"
    r"(?P<ext>\.pdf)$",
    re.IGNORECASE,
)
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
    is_correction: bool = False


# In PDF: «…1151001, первичный, за 2 квартал…» vs «…корректирующий (1), за 1 квартал…»
_CORRECTION_DOC_RE = re.compile(
    r"корректирующ\w*\s*\(\s*\d+\s*\)",
    re.IGNORECASE,
)
_PRIMARY_DOC_RE = re.compile(r"\bпервичн\w*\b", re.IGNORECASE)
_FILENAME_CORRECTION_RE = re.compile(r"корректир", re.IGNORECASE)


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


def detect_is_correction(filename: str, text: str = "") -> bool:
    """True when document kind is корректирующий (N); false for первичный.

    Number in parentheses may be 1, 2, … — any digit counts as correction.
    Do not treat bare «уточненн…» boilerplate as correction.
    """
    cleaned_name = normalize_receipt_filename(filename)
    if _FILENAME_CORRECTION_RE.search(cleaned_name):
        return True
    blob = (text or "").replace("\u00a0", " ").replace("\u202f", " ")
    if _CORRECTION_DOC_RE.search(blob):
        return True
    if _PRIMARY_DOC_RE.search(blob):
        return False
    return False


def is_generic_supplier_name(name: str | None) -> bool:
    if not name:
        return True
    cleaned = (
        name.strip()
        .casefold()
        .replace("«", "")
        .replace("»", "")
        .replace('"', "")
        .replace("'", "")
    )
    for prefix in ("ооо ", "ао ", "зао ", "пао ", "ип "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned in {"компания", "организация", "фирма", "предприятие", ""}


def normalize_receipt_filename(filename: str) -> str:
    """Strip trailing «DD-MM-YYYY [hash]» so CRM shows clean names."""
    name = filename.strip().replace("\\", "/").split("/")[-1]
    match = _SUFFIX_DATE_HASH_RE.match(name)
    if match is None:
        return name
    return f"{match.group('head')}{match.group('ext')}"


def short_name_from_filename(filename: str) -> str | None:
    cleaned = normalize_receipt_filename(filename)
    match = _NAME_PAREN_RE.search(cleaned)
    if match is None:
        return None
    name = match.group(1).strip()
    return name or None


def period_code_from_text(text: str) -> str | None:
    """Extract OPT period like 2/26 from «2 квартал 2026 год».

    Prefer explicit 20XX so we do not pick VAT rate «22» as the year.
    """
    normalized = (
        text.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\xa0", " ")
    )
    # Allow OCR/pdf gaps: "2 квартал" … "2026"
    patterns = (
        re.compile(
            r"([1-4])\s*к\s*в\s*а\s*р\s*т\s*а\s*л[\s,.\-]{0,20}20\s*(\d{2})\s*(?:г(?:од|ода|\.)?)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"([1-4])\s*квартал[\s,.\-]{0,20}20\s*(\d{2})\s*(?:г(?:од|ода|\.)?)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"отчетн\w*\s+период[^\d]{0,40}([1-4])[^\d]{0,20}20(\d{2})",
            re.IGNORECASE,
        ),
    )
    for pattern in patterns:
        match = pattern.search(normalized)
        if match is None:
            continue
        quarter_s, yy_s = match.groups()
        yy = int(yy_s)
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
    filename = normalize_receipt_filename(filename)
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
        if is_generic_supplier_name(supplier_name):
            supplier_name = short
    elif short:
        supplier_name = short

    period_code = period_code_from_text(text)
    is_correction = detect_is_correction(filename, text)

    return ParsedReceiptPdf(
        supplier_inn=supplier_inn,
        supplier_kpp=supplier_kpp,
        supplier_name=supplier_name,
        period_code=period_code,
        doc_kind=doc_kind,
        parsed_name=short,
        raw_text=text[:4000],
        is_correction=is_correction,
    )
