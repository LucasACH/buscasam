"""Integration tests for core/documents.get_draft_state + update_draft_metadata (issue #29)."""
from __future__ import annotations

import json
from datetime import date

import httpx
import numpy as np
from sqlalchemy import text

from buscasam.core import chunk as chunkmod
from buscasam.core import documents, jobs
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_user


def _tei_mock() -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        n = len(json.loads(req.read())["inputs"])
        return httpx.Response(200, json=[[0.1] * 1024] * n)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://tei"
    )


def _ctx(uid: int) -> UserCtx:
    return UserCtx(user_id=uid, is_unsam=True, role="estudiante")


async def _seed_candidate(
    session,
    *,
    titulo: str = "Mi tesis",
    index_status: str = "indexed",
    staged_abstract: str | None = "resumen",
    staged_keywords: list[str] | None = None,
    staged_fecha: date | None = None,
    fingerprint_matches: bool = True,
) -> tuple[int, int, int]:
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="draft", titulo=titulo)
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": uid},
    )
    fp = (
        chunkmod.headline_fingerprint(titulo, staged_abstract or "")
        if fingerprint_matches
        else "stale-fingerprint"
    )
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, uploaded_by, "
                " index_status, staged_abstract, staged_keywords, staged_fecha, headline_fingerprint) "
                "VALUES (:doc_id, 1, decode(repeat('00', 32), 'hex'), 'f', 1, "
                " 'application/pdf', :uid, :st, :abs, :kw, :fecha, :fp) RETURNING id"
            ),
            {
                "doc_id": doc_id,
                "uid": uid,
                "st": index_status,
                "abs": staged_abstract,
                "kw": staged_keywords,
                "fecha": staged_fecha,
                "fp": fp,
            },
        )
    ).scalar_one()
    return uid, doc_id, version_id


async def test_get_draft_state_indexed_and_matched_is_publishable(session):
    uid, doc_id, version_id = await _seed_candidate(session, index_status="indexed")

    state = await documents.get_draft_state(session, _ctx(uid), doc_id)

    assert state.index_status == "indexed"
    assert state.publish_gate_reason is None
    assert state.staged_abstract == "resumen"


async def test_get_draft_state_versions_lists_published_excludes_candidate(session):
    """ADR-0011 §4: the editar Versiones list mirrors get_detail — only rows
    that were at some point the public current appear, by 1-based n. A draft's
    own never-published candidate is excluded; previously published rows stay."""
    uid = await make_user(session)
    doc_id = await make_document(session, publication_status="published", titulo="T")
    await session.execute(
        text(
            "INSERT INTO document_authors (doc_id, user_id, display_name, status) "
            "VALUES (:doc_id, :uid, 'Owner', 'owner')"
        ),
        {"doc_id": doc_id, "uid": uid},
    )
    # Two previously published versions + an in-flight candidate (NULL stamp).
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at, headline_fingerprint) VALUES "
            "(:d, 1, decode('11', 'hex'), 'v1.pdf', 1, 'application/pdf', "
            " 'indexed', false, now(), 'fp1'), "
            "(:d, 2, decode('22', 'hex'), 'v2.pdf', 1, 'application/pdf', "
            " 'indexed', true, now(), 'fp2'), "
            "(:d, 3, decode('33', 'hex'), 'candidate.pdf', 1, 'application/pdf', "
            " 'indexed', false, NULL, 'fp3')"
        ),
        {"d": doc_id},
    )

    state = await documents.get_draft_state(session, _ctx(uid), doc_id)

    assert [(v.n, v.original_filename) for v in state.versions] == [
        (1, "v1.pdf"),
        (2, "v2.pdf"),
    ]


async def test_get_draft_state_processing_gates_with_processing(session):
    uid, doc_id, version_id = await _seed_candidate(session, index_status="processing")

    state = await documents.get_draft_state(session, _ctx(uid), doc_id)

    assert state.publish_gate_reason == "processing"


async def test_get_draft_state_failed_gates_with_processing_failed(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, index_status="failed"
    )

    state = await documents.get_draft_state(session, _ctx(uid), doc_id)

    assert state.publish_gate_reason == "processing_failed"


async def _enqueued_task_names(session, version_id: int) -> list[str]:
    rows = (
        await session.execute(
            text(
                "SELECT task_name FROM procrastinate_jobs "
                "WHERE args->>'version_id' = :vid"
            ),
            {"vid": str(version_id)},
        )
    ).scalars().all()
    return list(rows)


async def test_update_title_enqueues_reindex_and_gates_reindexing(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, titulo="Viejo título", staged_abstract="abs"
    )
    ctx = _ctx(uid)

    await documents.update_draft_metadata(session, ctx, doc_id, title="Nuevo título")

    titulo = (
        await session.execute(
            text("SELECT titulo FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).scalar_one()
    assert titulo == "Nuevo título"

    names = await _enqueued_task_names(session, version_id)
    assert any(n.endswith("refresh_headline") for n in names)

    # stored fingerprint is now stale against the new title → reindex gate
    state = await documents.get_draft_state(session, ctx, doc_id)
    assert state.publish_gate_reason == "reindexing_headline"


async def test_update_title_while_processing_does_not_enqueue(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, titulo="Viejo título", index_status="processing"
    )
    ctx = _ctx(uid)

    await documents.update_draft_metadata(session, ctx, doc_id, title="Nuevo título")

    # index_document owns the headline while processing; a concurrent refresh
    # would write a duplicate is_headline chunk.
    names = await _enqueued_task_names(session, version_id)
    assert not any(n.endswith("refresh_headline") for n in names)


async def test_update_title_unchanged_does_not_enqueue(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, titulo="Mismo título", index_status="indexed"
    )
    ctx = _ctx(uid)

    await documents.update_draft_metadata(session, ctx, doc_id, title="Mismo título")

    names = await _enqueued_task_names(session, version_id)
    assert not any(n.endswith("refresh_headline") for n in names)


async def test_update_abstract_enqueues_reindex_and_gates_reindexing(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, staged_abstract="viejo resumen", index_status="indexed"
    )
    ctx = _ctx(uid)

    await documents.update_draft_metadata(
        session, ctx, doc_id, abstract="nuevo resumen"
    )

    staged = (
        await session.execute(
            text("SELECT staged_abstract FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert staged == "nuevo resumen"

    names = await _enqueued_task_names(session, version_id)
    assert any(n.endswith("refresh_headline") for n in names)

    state = await documents.get_draft_state(session, ctx, doc_id)
    assert state.publish_gate_reason == "reindexing_headline"


async def test_update_fecha_null_clears_and_absent_leaves(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, staged_fecha=date(2020, 1, 1), index_status="indexed"
    )
    ctx = _ctx(uid)

    async def _staged_fecha():
        return (
            await session.execute(
                text("SELECT staged_fecha FROM document_versions WHERE id = :id"),
                {"id": version_id},
            )
        ).scalar_one()

    # absent (default sentinel) leaves the stored value untouched
    await documents.update_draft_metadata(session, ctx, doc_id, keywords=["x"])
    assert await _staged_fecha() == date(2020, 1, 1)

    # explicit null clears it
    await documents.update_draft_metadata(session, ctx, doc_id, fecha=None)
    assert await _staged_fecha() is None


async def test_update_keywords_only_does_not_enqueue_reindex(session):
    uid, doc_id, version_id = await _seed_candidate(session, index_status="indexed")
    ctx = _ctx(uid)

    await documents.update_draft_metadata(
        session, ctx, doc_id, keywords=["redes", "grafos"]
    )

    staged = (
        await session.execute(
            text("SELECT staged_keywords FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert staged == ["redes", "grafos"]

    names = await _enqueued_task_names(session, version_id)
    assert not any(n.endswith("refresh_headline") for n in names)

    # no headline change → still publishable
    state = await documents.get_draft_state(session, ctx, doc_id)
    assert state.publish_gate_reason is None


async def test_update_on_failed_candidate_persists_and_stays_failed(session):
    uid, doc_id, version_id = await _seed_candidate(session, index_status="failed")
    ctx = _ctx(uid)

    await documents.update_draft_metadata(
        session, ctx, doc_id, abstract="resumen corregido"
    )

    staged = (
        await session.execute(
            text("SELECT staged_abstract FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert staged == "resumen corregido"

    state = await documents.get_draft_state(session, ctx, doc_id)
    assert state.publish_gate_reason == "processing_failed"


async def test_title_edited_during_processing_self_enqueues_reindex(session):
    """R006: a título PATCH inside the index window leaves write_indexed_candidate
    stamping a fingerprint from the pre-edit title. It must detect the drift and
    enqueue a refresh, or the publish gate sticks on reindexing_headline forever."""
    from buscasam.core.extract import IndexableMetadata

    uid, doc_id, version_id = await _seed_candidate(
        session,
        titulo="Título editado",  # the racing PATCH already committed this
        index_status="processing",
        staged_abstract=None,
    )
    ctx = _ctx(uid)

    # The indexer embedded its headline against the pre-edit title.
    old_title = "Título original"
    await documents.write_indexed_candidate(
        session,
        version_id,
        body=[],
        headline=chunkmod.headline_chunk(old_title, "abs"),
        embeds=[np.zeros(1024)],
        meta=IndexableMetadata(abstract="abs", keywords=[], fecha=None),
        headline_fingerprint=chunkmod.headline_fingerprint(old_title, "abs"),
    )

    names = await _enqueued_task_names(session, version_id)
    assert any(n.endswith("refresh_headline") for n in names)

    mid = await documents.get_draft_state(session, ctx, doc_id)
    assert mid.publish_gate_reason == "reindexing_headline"

    tei = _tei_mock()
    await jobs._run_refresh_headline(session, tei, version_id)
    await tei.aclose()

    after = await documents.get_draft_state(session, ctx, doc_id)
    assert after.publish_gate_reason is None


async def test_reindex_round_trip_clears_the_gate(session):
    uid, doc_id, version_id = await _seed_candidate(
        session, titulo="Viejo título", staged_abstract="abs", index_status="indexed"
    )
    ctx = _ctx(uid)

    await documents.update_draft_metadata(session, ctx, doc_id, title="Nuevo título")
    mid = await documents.get_draft_state(session, ctx, doc_id)
    assert mid.publish_gate_reason == "reindexing_headline"

    tei = _tei_mock()
    await jobs._run_refresh_headline(session, tei, version_id)
    await tei.aclose()

    after = await documents.get_draft_state(session, ctx, doc_id)
    assert after.publish_gate_reason is None
