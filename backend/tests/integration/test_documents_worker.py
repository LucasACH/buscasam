"""Integration tests for the worker-facing surface on core/documents (issue #28).

Covers load_candidate, write_indexed_candidate, write_headline, mark_failed.
"""
from __future__ import annotations

import secrets
from datetime import date

import numpy as np
import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.chunk import Chunk, headline_fingerprint
from buscasam.core.extract import IndexableMetadata
from tests.factories import make_document, make_user


async def _make_candidate_version(session, *, owner_id: int, doc_id: int | None = None) -> int:
    if doc_id is None:
        doc_id = await make_document(session, publication_status="draft")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": owner_id},
    )
    sha = secrets.token_bytes(32)
    # 'processing' is the precondition the worker establishes via _begin_indexing
    # before calling write_indexed_candidate / write_headline / mark_failed; the
    # writers are gated on it (ADR-0011 §5), so seed it directly here.
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status) "
                "VALUES (:doc_id, 1, :sha, 'file.pdf', 1024, 'application/pdf', "
                ":uid, 'processing') RETURNING id"
            ),
            {"doc_id": doc_id, "sha": sha, "uid": owner_id},
        )
    ).scalar_one()
    return version_id


async def test_load_candidate_returns_version_metadata(session):
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    cv = await documents.load_candidate(session, version_id)

    assert cv.version_id == version_id
    assert cv.mime == "application/pdf"
    assert cv.title  # documents.titulo
    assert isinstance(cv.sha256, str) and len(cv.sha256) == 64


async def test_write_indexed_candidate_inserts_chunks_and_updates_version(session):
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    body = [
        Chunk(body_text="primer párrafo", is_headline=False, chunk_seq=1),
        Chunk(body_text="segundo párrafo", is_headline=False, chunk_seq=2),
    ]
    headline = Chunk(body_text="Título\n\nResumen", is_headline=True, chunk_seq=0)
    embeds = [np.full(1024, 0.1, dtype=np.float16) for _ in range(len(body) + 1)]
    meta = IndexableMetadata(abstract="Resumen", keywords=["a", "b"], fecha=None)
    fp = headline_fingerprint("Título", "Resumen")

    await documents.write_indexed_candidate(
        session, version_id, body=body, headline=headline, embeds=embeds, meta=meta,
        headline_fingerprint=fp,
    )

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, staged_keywords, "
                "  staged_fecha, headline_fingerprint, indexed_at, "
                "  extract_pipeline_version "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "indexed"
    assert row["staged_abstract"] == "Resumen"
    assert row["staged_keywords"] == ["a", "b"]
    assert row["headline_fingerprint"] == fp
    assert row["indexed_at"] is not None
    # ADR-0007 §12: per-row provenance stamp must be persisted, not 'unknown'.
    assert row["extract_pipeline_version"] != "unknown"

    chunk_rows = (
        await session.execute(
            text(
                "SELECT chunk_seq, is_headline, is_current, version_id "
                "FROM chunks WHERE version_id = :vid ORDER BY chunk_seq"
            ),
            {"vid": version_id},
        )
    ).mappings().all()
    assert len(chunk_rows) == 3
    assert chunk_rows[0]["is_headline"] is True and chunk_rows[0]["chunk_seq"] == 0
    assert all(r["is_current"] is False for r in chunk_rows)
    assert all(r["version_id"] == version_id for r in chunk_rows)


async def test_write_indexed_replacement_can_reuse_current_version_chunk_sequences(session):
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="published")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc, :uid, 'Owner', 'owner')"
        ),
        {"doc": doc_id, "uid": uid},
    )
    current_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, is_current, index_status) "
                "VALUES (:doc, 1, decode(repeat('01', 32), 'hex'), 'current.pdf', "
                " 1, 'application/pdf', :uid, true, 'indexed') RETURNING id"
            ),
            {"doc": doc_id, "uid": uid},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO chunks "
            "(doc_id, chunk_seq, is_headline, body_text, embedding_model_version, "
            " version_id, is_current) "
            "VALUES (:doc, 0, true, 'Current headline', 'm', :version, true)"
        ),
        {"doc": doc_id, "version": current_id},
    )
    replacement_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status) "
                "VALUES (:doc, 2, decode(repeat('02', 32), 'hex'), 'replacement.pdf', "
                " 1, 'application/pdf', :uid, 'processing') RETURNING id"
            ),
            {"doc": doc_id, "uid": uid},
        )
    ).scalar_one()

    await documents.write_indexed_candidate(
        session,
        replacement_id,
        body=[],
        headline=Chunk(body_text="Replacement headline", is_headline=True, chunk_seq=0),
        embeds=[np.full(1024, 0.2, dtype=np.float16)],
        meta=IndexableMetadata(abstract="replacement", keywords=[], fecha=None),
        headline_fingerprint=headline_fingerprint("test doc", "replacement"),
    )

    chunks = (
        await session.execute(
            text(
                "SELECT version_id, body_text, is_current FROM chunks "
                "WHERE doc_id = :doc AND chunk_seq = 0 ORDER BY version_id"
            ),
            {"doc": doc_id},
        )
    ).mappings().all()
    assert [(r["version_id"], r["is_current"]) for r in chunks] == [
        (current_id, True),
        (replacement_id, False),
    ]


async def test_write_indexed_candidate_preserves_staged_fields_edited_during_processing(session):
    """R007: an author who edits staged_* via save-on-blur while the candidate is
    still processing must keep those edits. Extraction fills only still-empty
    columns, so write_indexed_candidate never overwrites an author edit."""
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    # The author landed during processing and saved their own metadata.
    await session.execute(
        text(
            "UPDATE document_versions SET staged_abstract = :a, "
            "  staged_keywords = :k, staged_fecha = :f WHERE id = :vid"
        ),
        {"a": "resumen del autor", "k": ["autor"], "f": date(2021, 5, 1), "vid": version_id},
    )

    meta = IndexableMetadata(
        abstract="resumen del extractor", keywords=["extractor"], fecha=date(2099, 1, 1)
    )
    headline = Chunk(body_text="h", is_headline=True, chunk_seq=0)
    await documents.write_indexed_candidate(
        session, version_id, body=[], headline=headline,
        embeds=[np.full(1024, 0.1, dtype=np.float16)], meta=meta,
        headline_fingerprint=headline_fingerprint("t", "resumen del extractor"),
    )

    row = (
        await session.execute(
            text(
                "SELECT index_status, staged_abstract, staged_keywords, staged_fecha "
                "FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "indexed"
    assert row["staged_abstract"] == "resumen del autor"
    assert row["staged_keywords"] == ["autor"]
    assert row["staged_fecha"] == date(2021, 5, 1)


async def test_mark_failed_sets_failed_status_and_inserts_notification(session):
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    await documents.mark_failed(session, version_id, error="corrupted: PDFSyntaxError")

    row = (
        await session.execute(
            text(
                "SELECT index_status, index_error FROM document_versions WHERE id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    assert row["index_status"] == "failed"
    assert row["index_error"] == "corrupted: PDFSyntaxError"

    notif = (
        await session.execute(
            text(
                "SELECT user_id, event_key, kind FROM notifications "
                "WHERE event_key = :ek"
            ),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).mappings().one()
    assert notif["user_id"] == uid
    assert notif["kind"] == "processing_failed"


async def test_mark_failed_is_idempotent_on_retry(session):
    """ADR-0010 §9: unique (user_id, event_key) anchors producer idempotency."""
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    await documents.mark_failed(session, version_id, error="corrupted: a")
    await documents.mark_failed(session, version_id, error="corrupted: b")

    count = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM notifications "
                "WHERE event_key = :ek"
            ),
            {"ek": f"processing_failed:{version_id}"},
        )
    ).scalar_one()
    assert count == 1


async def test_write_headline_replaces_only_the_headline_chunk(session):
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    body = [Chunk(body_text="body", is_headline=False, chunk_seq=1)]
    headline = Chunk(body_text="Original headline", is_headline=True, chunk_seq=0)
    embeds = [np.full(1024, 0.1, dtype=np.float16) for _ in range(2)]
    meta = IndexableMetadata(abstract="r", keywords=[], fecha=None)
    fp = headline_fingerprint("t", "r")
    await documents.write_indexed_candidate(
        session, version_id, body=body, headline=headline, embeds=embeds, meta=meta,
        headline_fingerprint=fp,
    )

    # Simulate the user edit that the refresh_headline task is reacting to:
    # staged_abstract is updated to 'r2' before the task runs.
    titulo = (
        await session.execute(
            text(
                "UPDATE document_versions SET staged_abstract = 'r2' "
                "WHERE id = :vid "
                "RETURNING (SELECT titulo FROM documents WHERE id = doc_id)"
            ),
            {"vid": version_id},
        )
    ).scalar_one()

    new_headline = Chunk(body_text="Replaced headline", is_headline=True, chunk_seq=0)
    new_fp = headline_fingerprint(titulo, "r2")
    await documents.write_headline(
        session, version_id, new_headline, np.full(1024, 0.2, dtype=np.float16), new_fp,
    )

    headlines = (
        await session.execute(
            text(
                "SELECT body_text FROM chunks "
                "WHERE version_id = :vid AND is_headline ORDER BY id"
            ),
            {"vid": version_id},
        )
    ).scalars().all()
    assert headlines == ["Replaced headline"]

    bodies = (
        await session.execute(
            text(
                "SELECT body_text FROM chunks "
                "WHERE version_id = :vid AND NOT is_headline ORDER BY chunk_seq"
            ),
            {"vid": version_id},
        )
    ).scalars().all()
    assert bodies == ["body"]

    fp_row = (
        await session.execute(
            text("SELECT headline_fingerprint FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert fp_row == new_fp


async def test_write_headline_skips_when_fingerprint_no_longer_matches(session):
    """ADR-0007 §10: a stale refresh_headline must not stomp on newer state."""
    uid = await make_user(session)
    version_id = await _make_candidate_version(session, owner_id=uid)

    body = [Chunk(body_text="body", is_headline=False, chunk_seq=1)]
    headline = Chunk(body_text="Original headline", is_headline=True, chunk_seq=0)
    embeds = [np.full(1024, 0.1, dtype=np.float16) for _ in range(2)]
    meta = IndexableMetadata(abstract="initial", keywords=[], fecha=None)
    titulo = (
        await session.execute(
            text(
                "SELECT d.titulo FROM document_versions v "
                "JOIN documents d ON d.id = v.doc_id WHERE v.id = :id"
            ),
            {"id": version_id},
        )
    ).scalar_one()
    initial_fp = headline_fingerprint(titulo, "initial")
    await documents.write_indexed_candidate(
        session, version_id, body=body, headline=headline, embeds=embeds, meta=meta,
        headline_fingerprint=initial_fp,
    )

    # The task computed its embedding against 'initial', but in the meantime
    # the user edited the abstract again. Stale write must be a no-op.
    await session.execute(
        text("UPDATE document_versions SET staged_abstract = 'newer' WHERE id = :vid"),
        {"vid": version_id},
    )
    stale_headline = Chunk(body_text="STALE headline", is_headline=True, chunk_seq=0)
    stale_fp = headline_fingerprint(titulo, "initial")
    await documents.write_headline(
        session, version_id, stale_headline,
        np.full(1024, 0.2, dtype=np.float16), stale_fp,
    )

    headlines = (
        await session.execute(
            text(
                "SELECT body_text FROM chunks "
                "WHERE version_id = :vid AND is_headline"
            ),
            {"vid": version_id},
        )
    ).scalars().all()
    assert headlines == ["Original headline"]
    fp_row = (
        await session.execute(
            text("SELECT headline_fingerprint FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert fp_row == initial_fp
