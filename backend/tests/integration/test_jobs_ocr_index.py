"""OCR integration test (issue #28). Marked ocr_slow — needs Tesseract.

PRD §"Testing Decisions": one ocr_slow-marked integration test covers the
OCR worker invocation end-to-end.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from buscasam.core import blob_store, jobs
from tests.factories import make_document, make_user


pytestmark = pytest.mark.ocr_slow


@pytest.fixture
def blob_root(tmp_path, monkeypatch):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(blob_store, "BLOB_ROOT", root)
    return root


def _persist_blob(blob_root: Path, payload: bytes) -> tuple[str, bytes]:
    raw = hashlib.sha256(payload).digest()
    sha_hex = raw.hex()
    final = blob_root / sha_hex[:2] / sha_hex[2:4] / sha_hex
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(payload)
    return sha_hex, raw


def _tei_mock() -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        import json
        n = len(json.loads(req.read())["inputs"])
        return httpx.Response(200, json=[[0.1] * 1024] * n)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://tei")


def _has_tesseract_spa_eng() -> bool:
    """Tesseract must have both `spa` and `eng` tessdata installed."""
    try:
        import ocrmypdf  # noqa: F401
    except ImportError:
        return False
    if shutil.which("tesseract") is None:
        return False
    import subprocess
    try:
        out = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5
        )
    except Exception:
        return False
    langs = set(out.stdout.split() + out.stderr.split())
    return "spa" in langs and "eng" in langs


async def test_ocr_index_document_runs_ocrmypdf_and_indexes(session, blob_root, worker_sm):
    """Scanned-image PDF triggers OCRRequired, ocr_index_document OCRs it, indexes."""
    if not _has_tesseract_spa_eng():
        pytest.skip(
            "ocrmypdf + Tesseract spa+eng tessdata not installed (CI runs this slow test)"
        )

    # Build a scanned-image PDF: text rendered to an image, embedded into a PDF.
    from PIL import Image, ImageDraw, ImageFont
    from fpdf import FPDF
    import io as _io

    img = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except OSError:
        font = ImageFont.load_default()
    text_lines = [
        "TESIS DE GRADO",
        "",
        "Resumen",
        "Este trabajo investiga el",
        "aprendizaje automatico aplicado",
        "al procesamiento de imagenes.",
    ]
    y = 100
    for line in text_lines:
        draw.text((100, y), line, fill="black", font=font)
        y += 120

    img_bytes = _io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_path = blob_root / "fixture_scan.png"
    img_path.write_bytes(img_bytes.getvalue())

    pdf = FPDF()
    pdf.add_page()
    pdf.image(str(img_path), x=0, y=0, w=210, h=297)
    payload = bytes(pdf.output())

    sha_hex, sha_bytes = _persist_blob(blob_root, payload)

    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft", titulo="Scanned")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": uid},
    )
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status) "
                "VALUES (:doc_id, 1, :sha, 'scan.pdf', 100, 'application/pdf', "
                ":uid, 'processing') RETURNING id"
            ),
            {"doc_id": doc_id, "sha": sha_bytes, "uid": uid},
        )
    ).scalar_one()

    tei = _tei_mock()
    await jobs._run_ocr_index_document(worker_sm, tei, version_id)
    await tei.aclose()

    status = (
        await session.execute(
            text("SELECT index_status FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert status == "indexed"
