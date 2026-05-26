"""Text extraction and metadata derivation (ADR-0007, module map §core/extract).

Single chokepoint for "PDF/DOCX/ODT → text + offsets" and "text → abstract/
keywords/fecha suggestions". Owns the per-format dispatch, the OCR gate
threshold, the abstract regex, the YAKE configuration, the fecha cover-page
heuristic, and the encrypted-PDF probe.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date

from buscasam.core import blob_store

logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ODT_MIME = "application/vnd.oasis.opendocument.text"

# ADR-0007 §4: PDF OCR gate threshold.
OCR_MIN_CHARS_PER_PAGE = 100


class PDFEncryptionError(Exception):
    pass


class OCRRequired(Exception):
    def __init__(self, sha256: str) -> None:
        self.sha256 = sha256


@dataclass(frozen=True)
class ExtractedDoc:
    text: str
    paragraph_breaks: list[int]
    page_breaks: list[int]
    raw_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class IndexableMetadata:
    abstract: str
    keywords: list[str]
    fecha: date | None


def probe_encrypted(data: bytes) -> None:
    """ADR-0007 §9: raise PDFEncryptionError if `data` is a password-protected PDF.

    Uses pdfminer to detect the encryption dictionary properly. Non-encryption
    parse failures (corrupted, truncated) are deferred to async indexing per
    ADR-0007 §9 and do not surface here.
    """
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfdocument import PDFPasswordIncorrect as _PDFPwd
    from pdfminer.pdfparser import PDFParser

    try:
        PDFDocument(PDFParser(io.BytesIO(data)))
    except _PDFPwd as e:
        raise PDFEncryptionError("PDF is password-protected") from e
    except Exception:
        return


async def _read_blob(sha256: str) -> bytes:
    buf = bytearray()
    async for chunk in blob_store.open_for_send(sha256):
        buf.extend(chunk)
    return bytes(buf)


def _build_doc_from_paragraphs(paragraphs: list[str]) -> ExtractedDoc:
    pieces: list[str] = []
    breaks: list[int] = []
    cursor = 0
    for p in paragraphs:
        if not p.strip():
            continue
        pieces.append(p)
        cursor += len(p)
        breaks.append(cursor)
        pieces.append("\n\n")
        cursor += 2
    text = "".join(pieces).rstrip()
    # Drop the final break if it lands past the rstrip
    breaks = [b for b in breaks if b <= len(text)]
    return ExtractedDoc(text=text, paragraph_breaks=breaks, page_breaks=[], raw_metadata={})


def _extract_docx(data: bytes) -> ExtractedDoc:
    from docx import Document as DocxDocument

    docx = DocxDocument(io.BytesIO(data))
    paragraphs = [p.text for p in docx.paragraphs]
    return _build_doc_from_paragraphs(paragraphs)


def _extract_odt(data: bytes) -> ExtractedDoc:
    from odf.opendocument import load
    from odf.text import H, P
    from odf.teletype import extractText

    odt = load(io.BytesIO(data))
    paragraphs: list[str] = []
    for node in odt.getElementsByType(P) + odt.getElementsByType(H):
        paragraphs.append(extractText(node))
    return _build_doc_from_paragraphs(paragraphs)


def _extract_pdf(data: bytes) -> tuple[ExtractedDoc, int]:
    """Returns (doc, page_count). page_count includes blank pages (for OCR gate)."""
    from pdfminer.high_level import extract_text
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser

    parser = PDFParser(io.BytesIO(data))
    pdfdoc = PDFDocument(parser)
    raw_metadata = (
        getattr(pdfdoc, "info", [{}])[0] if getattr(pdfdoc, "info", None) else {}
    )

    full_text = extract_text(io.BytesIO(data)) or ""
    # pdfminer separates pages with form feed \x0c, trailing one after the last page.
    pages = full_text.split("\x0c")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    page_count = max(1, len(pages))

    pieces: list[str] = []
    paragraph_breaks: list[int] = []
    page_breaks: list[int] = []
    cursor = 0
    for page_idx, page in enumerate(pages):
        for para in page.split("\n\n"):
            stripped = para.strip()
            if not stripped:
                continue
            pieces.append(stripped)
            cursor += len(stripped)
            paragraph_breaks.append(cursor)
            pieces.append("\n\n")
            cursor += 2
        if page_idx < len(pages) - 1:
            page_breaks.append(cursor)

    text = "".join(pieces).rstrip()
    paragraph_breaks = [b for b in paragraph_breaks if b <= len(text)]
    page_breaks = [b for b in page_breaks if 0 < b <= len(text)]

    return (
        ExtractedDoc(
            text=text,
            paragraph_breaks=paragraph_breaks,
            page_breaks=page_breaks,
            raw_metadata=raw_metadata,
        ),
        page_count,
    )


_ABSTRACT_HEADING = re.compile(
    r"^(?:Resumen|Abstract|Summary|Sinopsis)\b",
    re.IGNORECASE | re.MULTILINE,
)
_NEXT_HEADING = re.compile(
    r"^(?:Introducci[oó]n|Cap[ií]tulo|Objetivos|Marco te[oó]rico|Metodolog[ií]a|"
    r"Conclusiones|Referencias|Bibliograf[ií]a|Index|Contenidos?)\b",
    re.IGNORECASE | re.MULTILINE,
)
_ABSTRACT_WORD_CAP = 300

_COVER_TOKENS = re.compile(
    r"\b(tesis|tesina|trabajo|presentado|defendido|publicado)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _truncate_words(s: str, cap: int) -> str:
    parts = s.split()
    if len(parts) <= cap:
        return " ".join(parts)
    return " ".join(parts[:cap])


def _derive_abstract(text: str) -> str:
    if not text.strip():
        return ""
    head = text[: 8000]  # first ~2 pages worth
    m = _ABSTRACT_HEADING.search(head)
    if m:
        body = head[m.end():]
        nxt = _NEXT_HEADING.search(body)
        body = body[: nxt.start()] if nxt else body
        return _truncate_words(body.strip(), _ABSTRACT_WORD_CAP)
    # fallback: first 1-3 paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    return _truncate_words(" ".join(paragraphs[:3]), _ABSTRACT_WORD_CAP)


def _derive_keywords(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        from yake import KeywordExtractor

        kw = KeywordExtractor(lan="es", n=3, dedupLim=0.7, top=8)
        results = kw.extract_keywords(text)
        return [phrase for phrase, _score in results][:10]
    except Exception:
        # YAKE failure must not block indexing (keywords are best-effort
        # suggestions per ADR-0007 §7); log so operators see degraded output.
        logger.warning("yake_failed", exc_info=True)
        return []


_PDF_CREATION_DATE_RE = re.compile(r"^D:(\d{4})")


def _derive_fecha_from_text(text: str) -> date | None:
    head = text[: 8000]
    current_year = date.today().year
    best: int | None = None
    for m in _YEAR_RE.finditer(head):
        year = int(m.group())
        if not (1970 <= year <= current_year + 1):
            continue
        # check cover-token proximity (within 80 chars window before)
        window_start = max(0, m.start() - 80)
        if _COVER_TOKENS.search(head[window_start: m.end()]):
            if best is None or year > best:
                best = year
    return date(best, 1, 1) if best else None


def _derive_fecha_from_metadata(raw_metadata: dict) -> date | None:
    """ADR-0007 §8 step 2: fall back to PDF `/CreationDate` if plausible.

    PDF dates use `D:YYYYMMDDHHmmSS+TZ`; values may be `str` or `bytes`.
    """
    if not raw_metadata:
        return None
    raw = raw_metadata.get("CreationDate") or raw_metadata.get(b"CreationDate")
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("ascii", errors="ignore")
        except Exception:
            return None
    m = _PDF_CREATION_DATE_RE.match(raw)
    if not m:
        return None
    year = int(m.group(1))
    current_year = date.today().year
    if not (1970 <= year <= current_year + 1):
        return None
    return date(year, 1, 1)


def _derive_fecha(doc: ExtractedDoc) -> date | None:
    from_text = _derive_fecha_from_text(doc.text)
    if from_text is not None:
        return from_text
    return _derive_fecha_from_metadata(doc.raw_metadata)


def derive_metadata(doc: ExtractedDoc) -> IndexableMetadata:
    return IndexableMetadata(
        abstract=_derive_abstract(doc.text),
        keywords=_derive_keywords(doc.text),
        fecha=_derive_fecha(doc),
    )


async def extract(sha256: str, mime: str) -> ExtractedDoc:
    data = await _read_blob(sha256)

    if mime == _DOCX_MIME:
        return _extract_docx(data)
    if mime == _ODT_MIME:
        return _extract_odt(data)
    if mime == _PDF_MIME:
        doc, page_count = _extract_pdf(data)
        # ADR-0007 §4: if average chars/page < threshold, OCR is required.
        if len(doc.text) / page_count < OCR_MIN_CHARS_PER_PAGE:
            raise OCRRequired(sha256)
        return doc
    raise ValueError(f"Unsupported mime: {mime}")
