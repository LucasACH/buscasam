"""Unit tests for core/extract per-format dispatch + OCR gate (issue #28).

Tests build minimal real PDF / DOCX / ODT bytes, write them through blob_store,
then call extract(sha256, mime) and assert text + paragraph_breaks.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from odf.opendocument import OpenDocumentText
from odf.text import H, P

from buscasam.core import blob_store
from buscasam.core.extract import (
    ExtractedDoc,
    OCRRequired,
    PDFEncryptionError,
    derive_metadata,
    extract,
    probe_encrypted,
)


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


def _persist_blob(blob_root: Path, payload: bytes) -> str:
    sha256 = hashlib.sha256(payload).hexdigest()
    final = blob_root / sha256[:2] / sha256[2:4] / sha256
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(payload)
    return sha256


def _make_docx(paragraphs: list[str]) -> bytes:
    doc = DocxDocument()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_odt(paragraphs: list[str]) -> bytes:
    odt = OpenDocumentText()
    for p in paragraphs:
        odt.text.addElement(P(text=p))
    buf = BytesIO()
    odt.write(buf)
    return buf.getvalue()


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ODT_MIME = "application/vnd.oasis.opendocument.text"


async def test_extract_docx_returns_text_with_paragraph_breaks(blob_root):
    payload = _make_docx(["Primer párrafo.", "Segundo párrafo."])
    sha = _persist_blob(blob_root, payload)

    doc = await extract(sha, _DOCX_MIME)

    assert "Primer párrafo." in doc.text
    assert "Segundo párrafo." in doc.text
    assert len(doc.paragraph_breaks) >= 2
    assert doc.page_breaks == []
    # paragraph_breaks are ascending byte offsets into text
    assert doc.paragraph_breaks == sorted(doc.paragraph_breaks)
    assert all(0 <= b <= len(doc.text) for b in doc.paragraph_breaks)


async def test_extract_odt_returns_text_with_paragraph_breaks(blob_root):
    payload = _make_odt(["Hola mundo.", "Otra línea."])
    sha = _persist_blob(blob_root, payload)

    doc = await extract(sha, _ODT_MIME)

    assert "Hola mundo." in doc.text
    assert "Otra línea." in doc.text
    assert doc.page_breaks == []


def _make_pdf(paragraphs: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for p in paragraphs:
        pdf.multi_cell(0, 10, p)
        pdf.ln(2)
    return bytes(pdf.output())


async def test_extract_pdf_with_text_layer_returns_text(blob_root):
    paragraphs = [
        "This is a thesis abstract. " * 20,
        "Body of the work. " * 20,
        "Conclusions and references. " * 20,
    ]
    payload = _make_pdf(paragraphs)
    sha = _persist_blob(blob_root, payload)

    doc = await extract(sha, "application/pdf")

    assert "thesis abstract" in doc.text
    assert "Body of the work" in doc.text


def test_probe_encrypted_accepts_plain_pdf():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "hi")
    head = bytes(pdf.output())[:4096]
    probe_encrypted(head)  # should not raise


def test_probe_encrypted_rejects_encrypted_pdf():
    encrypted = b"%PDF-1.4\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n"
    with pytest.raises(PDFEncryptionError):
        probe_encrypted(encrypted)


async def test_extract_pdf_below_threshold_raises_ocr_required(blob_root):
    # Multi-page PDF with very little text → forces avg chars/page < 100.
    from fpdf import FPDF

    pdf = FPDF()
    for _ in range(5):
        pdf.add_page()
        # No actual text on the page — simulates a scanned image.
    payload = bytes(pdf.output())
    sha = _persist_blob(blob_root, payload)

    with pytest.raises(OCRRequired) as exc:
        await extract(sha, "application/pdf")
    assert exc.value.sha256 == sha


def _doc(text: str) -> ExtractedDoc:
    # Build paragraph_breaks at each "\n\n" boundary.
    breaks: list[int] = []
    cursor = 0
    for piece in text.split("\n\n"):
        cursor += len(piece)
        breaks.append(cursor)
        cursor += 2
    return ExtractedDoc(text=text, paragraph_breaks=breaks, page_breaks=[], raw_metadata={})


def test_derive_metadata_extracts_abstract_after_resumen_heading():
    doc = _doc(
        "Tesis de grado\n\n"
        "Resumen\n\n"
        "Este trabajo investiga el ciclo de vida del bosón de Higgs.\n\n"
        "Introducción\n\n"
        "El capítulo siguiente describe la metodología."
    )
    meta = derive_metadata(doc)
    assert "bosón de Higgs" in meta.abstract


def test_derive_metadata_falls_back_to_first_paragraphs_when_no_heading():
    doc = _doc(
        "Primer párrafo del cuerpo del trabajo.\n\n"
        "Segundo párrafo del cuerpo.\n\n"
        "Tercer párrafo."
    )
    meta = derive_metadata(doc)
    assert "Primer párrafo" in meta.abstract


def test_derive_metadata_empty_doc_yields_empty_abstract():
    """ADR-0007 §9: empty extraction is not a failure."""
    doc = ExtractedDoc(text="", paragraph_breaks=[], page_breaks=[], raw_metadata={})
    meta = derive_metadata(doc)
    assert meta.abstract == ""
    assert meta.keywords == []
    assert meta.fecha is None


def test_derive_metadata_picks_recent_plausible_year_near_cover_tokens():
    doc = _doc(
        "Universidad Nacional de San Martín\n\n"
        "Tesis presentada en 2024 para optar al grado.\n\n"
        "Otra cosa de 1850 sin contexto."
    )
    from datetime import date as _date
    meta = derive_metadata(doc)
    assert meta.fecha == _date(2024, 1, 1)


def test_derive_metadata_returns_some_keywords_for_real_text():
    doc = _doc(
        "Este trabajo investiga el desarrollo del aprendizaje automático "
        "aplicado al procesamiento del lenguaje natural.\n\n"
        "El aprendizaje profundo y las redes neuronales convolucionales "
        "son técnicas centrales en el campo del aprendizaje automático."
    )
    meta = derive_metadata(doc)
    assert 0 < len(meta.keywords) <= 10
    assert all(isinstance(k, str) and k for k in meta.keywords)
