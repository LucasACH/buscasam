"""Text extraction and metadata derivation (ADR-0007, module map §core/extract).

Single chokepoint for "PDF/DOCX/ODT → text + offsets" and "text → abstract/
keywords/fecha suggestions". Owns the per-format dispatch, the OCR gate
threshold, the abstract regex, the YAKE configuration, the fecha cover-page
heuristic, and the encrypted-PDF probe.
"""
from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

import httpx

from buscasam.core import blob_store
from buscasam.settings import settings

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
_LLM_TEXT_CHAR_CAP = 12000
_KEYWORD_CAP = 10
_KEYWORD_BLOCKLIST = {
    "este trabajo",
    "el presente trabajo",
    "presente trabajo",
    "presente informe",
    "este informe",
    "trabajo práctico",
    "trabajo practico",
    "la presente investigación",
    "presente investigación",
    "presente investigacion",
    "este documento",
    "el objetivo",
    "objetivo general",
    "universidad nacional",
    "universidad nacional de san martín",
    "universidad nacional de san martin",
    "san martín",
    "san martin",
}
_METADATA_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "abstract": {"type": "string"},
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": _KEYWORD_CAP,
        },
    },
    "required": ["abstract", "keywords"],
    "additionalProperties": False,
}
_PORTUGUESE_MARKERS = re.compile(
    r"\b(este documento descreve|previs[aã]o|s[eé]ries temporais|redes neurais|"
    r"m[eé]dia|avalia[cç][aã]o|utilizando|t[eé]cnicas estoc[aá]sticas|"
    r"j[aá]|por outro lado|informa[cç][oõ]es|aprendizagem)\b",
    re.IGNORECASE,
)

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


def _normalize_phrase(s: str) -> str:
    cleaned = re.sub(r"\s+", " ", s).strip(" \t\r\n.,;:()[]{}\"'")
    return cleaned


def _clean_keywords(keywords: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in keywords:
        phrase = _normalize_phrase(str(raw))
        key = phrase.casefold()
        if (
            not phrase
            or key in seen
            or key in _KEYWORD_BLOCKLIST
            or any(noise in key for noise in _KEYWORD_BLOCKLIST)
        ):
            continue
        if len(phrase.split()) > 5:
            continue
        seen.add(key)
        cleaned.append(phrase)
        if len(cleaned) >= _KEYWORD_CAP:
            break
    return cleaned


def _derive_abstract(text: str) -> str:
    if not text.strip():
        return ""
    head = text[: 8000]  # first ~2 pages worth
    explicit = _derive_explicit_abstract(head)
    if explicit is not None:
        return explicit
    # fallback: first 1-3 paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    return _truncate_words(" ".join(paragraphs[:3]), _ABSTRACT_WORD_CAP)


def _derive_explicit_abstract(head: str) -> str | None:
    m = _ABSTRACT_HEADING.search(head)
    if not m:
        return None
    body = head[m.end():]
    nxt = _NEXT_HEADING.search(body)
    body = body[: nxt.start()] if nxt else body
    return _truncate_words(body.strip(), _ABSTRACT_WORD_CAP)


def _derive_keywords(text: str) -> list[str]:
    if not text.strip():
        return []
    try:
        from yake import KeywordExtractor

        kw = KeywordExtractor(lan="es", n=3, dedupLim=0.7, top=8)
        results = kw.extract_keywords(text)
        return _clean_keywords([phrase for phrase, _score in results])
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


@dataclass(frozen=True)
class _LlmMetadata:
    abstract: str
    keywords: list[str]


def _metadata_prompt(doc: ExtractedDoc, fallback: IndexableMetadata) -> str:
    return (
        "Sos un asistente local para limpiar metadatos académicos.\n"
        "Devolvé solo JSON válido con esta forma exacta: "
        '{"abstract": "string", "keywords": ["string"]}.\n'
        "Reglas: abstract en español, máximo 300 palabras; keywords 3 a 10, "
        "frases académicas específicas, sin nombres de plantilla institucional.\n"
        "Idioma obligatorio: español. No uses portugués ni inglés. Traduce "
        "términos del texto fuente al español cuando haga falta.\n"
        "No inventes datos que no estén en el texto.\n\n"
        f"Abstract heurístico:\n{fallback.abstract}\n\n"
        f"Keywords candidatas:\n{', '.join(fallback.keywords)}\n\n"
        "Texto extraído entre delimitadores. No copies JSON, código ni tablas "
        "desde el texto fuente.\n"
        "<texto>\n"
        f"{doc.text[:_LLM_TEXT_CHAR_CAP]}\n"
        "</texto>"
    )


def _parse_llm_metadata(raw: str) -> _LlmMetadata:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("metadata LLM returned invalid JSON") from e
    if not isinstance(payload, dict):
        raise ValueError("metadata LLM returned non-object JSON")
    abstract = payload.get("abstract")
    keywords = payload.get("keywords")
    if not isinstance(abstract, str) or not isinstance(keywords, list):
        raise ValueError("metadata LLM returned invalid schema")
    if not all(isinstance(k, str) for k in keywords):
        raise ValueError("metadata LLM returned invalid keyword schema")
    return _LlmMetadata(
        abstract=_truncate_words(abstract.strip(), _ABSTRACT_WORD_CAP),
        keywords=_clean_keywords(keywords),
    )


def _looks_portuguese(value: str) -> bool:
    return bool(_PORTUGUESE_MARKERS.search(value))


async def _call_metadata_llm(
    client: httpx.AsyncClient, doc: ExtractedDoc, fallback: IndexableMetadata
) -> _LlmMetadata:
    response = await client.post(
        "/api/generate",
        json={
            "model": settings.metadata_llm_model,
            "prompt": _metadata_prompt(doc, fallback),
            "stream": False,
            "format": _METADATA_LLM_SCHEMA,
        },
        timeout=settings.metadata_llm_timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    raw = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(raw, str):
        raise ValueError("metadata LLM response missing response string")
    return _parse_llm_metadata(raw)


async def suggest_metadata(
    doc: ExtractedDoc, client: httpx.AsyncClient | None = None
) -> IndexableMetadata:
    """Best-effort staged metadata path.

    Heuristics always produce the fallback. The local LLM may clean up fallback
    output, but any timeout/outage/malformed output is non-fatal.
    """
    fallback = derive_metadata(doc)
    if not settings.metadata_llm_enabled:
        return fallback

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(base_url=settings.metadata_llm_url)
    try:
        llm = await _call_metadata_llm(client, doc, fallback)
    except (httpx.TimeoutException, httpx.HTTPError, ValueError):
        logger.warning("metadata_llm_failed", exc_info=True)
        return fallback
    finally:
        if owns_client:
            await client.aclose()

    explicit = _derive_explicit_abstract(doc.text[:8000])
    abstract = explicit if explicit is not None else llm.abstract or fallback.abstract
    keywords = _clean_keywords(llm.keywords) or fallback.keywords
    if _looks_portuguese(" ".join([abstract, *keywords])):
        logger.warning("metadata_llm_non_spanish")
        return fallback
    return IndexableMetadata(abstract=abstract, keywords=keywords, fecha=fallback.fecha)


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
