"""Text extraction and metadata derivation (ADR-0007, module map §core/extract).

Single chokepoint for "PDF/DOCX/ODT → text + offsets" and "text → abstract/
keywords/fecha suggestions". Owns the per-format dispatch, the OCR gate
threshold, the abstract regex, the YAKE configuration, the fecha cover-page
heuristic, and the encrypted-PDF probe.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date

from buscasam.core import blob_store

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


def probe_encrypted(head_bytes: bytes) -> None:
    """Raises PDFEncryptionError if head_bytes indicate a password-protected PDF."""
    if b"/Encrypt" in head_bytes:
        raise PDFEncryptionError("PDF is password-protected")


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


def _extract_pdf(data: bytes) -> ExtractedDoc:
    from pdfminer.high_level import extract_text
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser

    parser = PDFParser(io.BytesIO(data))
    pdfdoc = PDFDocument(parser)
    page_count = sum(1 for _ in pdfdoc.get_pages()) if hasattr(pdfdoc, "get_pages") else 1
    if page_count == 0:
        page_count = 1

    full_text = extract_text(io.BytesIO(data)) or ""
    # pdfminer separates pages by form feed \x0c; build page_breaks from those.
    page_breaks: list[int] = []
    cursor = 0
    pages = full_text.split("\x0c")
    paragraphs: list[str] = []
    for page_idx, page in enumerate(pages):
        if not page:
            continue
        # paragraphs inside a page split on blank lines
        for para in page.split("\n\n"):
            para = para.strip()
            if para:
                paragraphs.append(para)
        if page_idx < len(pages) - 1:
            # cumulative offset into the assembled text
            pass

    doc = _build_doc_from_paragraphs(paragraphs)

    # Recompute page_breaks against assembled text — best-effort.
    # If pdfminer reports a multi-page document, mark even splits across text.
    if page_count > 1 and doc.text:
        step = max(1, len(doc.text) // page_count)
        page_breaks = [min(len(doc.text), step * (i + 1)) for i in range(page_count - 1)]
    return ExtractedDoc(
        text=doc.text,
        paragraph_breaks=doc.paragraph_breaks,
        page_breaks=page_breaks,
        raw_metadata=getattr(pdfdoc, "info", [{}])[0] if getattr(pdfdoc, "info", None) else {},
    )


def _page_count(data: bytes) -> int:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser

    parser = PDFParser(io.BytesIO(data))
    pdfdoc = PDFDocument(parser)
    return max(1, sum(1 for _ in pdfdoc.get_pages())) if hasattr(pdfdoc, "get_pages") else 1


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
        return []


def _derive_fecha(text: str) -> date | None:
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


def derive_metadata(doc: ExtractedDoc) -> IndexableMetadata:
    return IndexableMetadata(
        abstract=_derive_abstract(doc.text),
        keywords=_derive_keywords(doc.text),
        fecha=_derive_fecha(doc.text),
    )


async def extract(sha256: str, mime: str) -> ExtractedDoc:
    data = await _read_blob(sha256)

    if mime == _DOCX_MIME:
        return _extract_docx(data)
    if mime == _ODT_MIME:
        return _extract_odt(data)
    if mime == _PDF_MIME:
        doc = _extract_pdf(data)
        # ADR-0007 §4: if average chars/page < threshold, OCR is required.
        pages = _page_count(data)
        avg = len(doc.text) / pages
        if avg < OCR_MIN_CHARS_PER_PAGE:
            raise OCRRequired(sha256)
        return doc
    raise ValueError(f"Unsupported mime: {mime}")
