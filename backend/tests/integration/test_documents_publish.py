"""Integration tests for core/documents.publish (module map §core/documents,
issue #30). Exercises the publish transaction through the domain chokepoint."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from buscasam.core import documents, search_query
from buscasam.core.auth import GUEST, UserCtx
from buscasam.core.chunk import headline_fingerprint
from tests.factories import make_document, make_document_author, make_user


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


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


def _doc_ids(results) -> list[int]:
    return [r.doc_id for r in results.rows]

_EMB = "[" + ",".join(["0.1"] * 1024) + "]"


async def _seed_candidate(
    session,
    *,
    owner_user_id: int,
    title: str = "Mi trabajo",
    staged_abstract: str = "Un resumen del trabajo",
    staged_keywords: list[str] | None = None,
    staged_fecha: date | None = date(2024, 3, 1),
    index_status: str = "indexed",
    fingerprint: str | None = None,
) -> tuple[int, int]:
    """Seed a draft document with one owner and an indexed candidate version
    plus its (is_current=false) chunks. Returns (doc_id, version_id)."""
    staged_keywords = staged_keywords if staged_keywords is not None else ["bd", "sql"]
    doc_id = await make_document(
        session, publication_status="draft", titulo=title, abstract=None
    )
    await make_document_author(session, doc_id, user_id=owner_user_id, status="owner")
    fp = fingerprint if fingerprint is not None else headline_fingerprint(
        title, staged_abstract
    )
    version_id = (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, staged_abstract, staged_keywords, "
                " staged_fecha, headline_fingerprint, indexed_at) "
                "VALUES (:doc, 1, decode('00', 'hex'), 'f.pdf', 1, "
                " 'application/pdf', :uid, :st, :abs, :kw, :fec, :fp, now()) "
                "RETURNING id"
            ),
            {
                "doc": doc_id,
                "uid": owner_user_id,
                "st": index_status,
                "abs": staged_abstract,
                "kw": staged_keywords,
                "fec": staged_fecha,
                "fp": fp,
            },
        )
    ).scalar_one()
    for seq, hl, body in (
        (0, True, f"{title}\n\n{staged_abstract}"),
        (1, False, "cuerpo del documento"),
    ):
        await session.execute(
            text(
                "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                " embedding, embedding_model_version, version_id, is_current) "
                "VALUES (:doc, :seq, :hl, :body, cast(:emb as halfvec(1024)), "
                " 'm', :vid, false)"
            ),
            {"doc": doc_id, "seq": seq, "hl": hl, "body": body, "emb": _EMB, "vid": version_id},
        )
    return doc_id, version_id


async def test_publish_flips_current_and_copies_staged(session):
    owner = await make_user(session, role="estudiante")
    doc_id, version_id = await _seed_candidate(
        session,
        owner_user_id=owner,
        title="Mi Tesis",
        staged_abstract="Un resumen",
        staged_keywords=["bd", "sql"],
        staged_fecha=date(2024, 3, 1),
    )
    ctx = UserCtx(user_id=owner, is_unsam=True, role="estudiante")

    await documents.publish(session, ctx, doc_id)

    ver = (
        await session.execute(
            text("SELECT is_current FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert ver is True

    chunk_currents = (
        await session.execute(
            text("SELECT is_current FROM chunks WHERE version_id = :v ORDER BY chunk_seq"),
            {"v": version_id},
        )
    ).scalars().all()
    assert chunk_currents == [True, True]

    doc = (
        await session.execute(
            text(
                "SELECT publication_status, abstract, keywords, fecha, "
                "       published_at IS NOT NULL AS has_published_at "
                "FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
    ).mappings().one()
    assert doc["publication_status"] == "published"
    assert doc["abstract"] == "Un resumen"
    assert doc["keywords"] == ["bd", "sql"]
    assert doc["fecha"] == date(2024, 3, 1)
    assert doc["has_published_at"] is True


async def test_publish_processing_candidate_conflicts_without_mutating(session):
    owner = await make_user(session, role="estudiante")
    doc_id, version_id = await _seed_candidate(
        session, owner_user_id=owner, index_status="processing"
    )
    ctx = UserCtx(user_id=owner, is_unsam=True, role="estudiante")

    with pytest.raises(documents.PublishConflict):
        await documents.publish(session, ctx, doc_id)

    status = (
        await session.execute(
            text("SELECT publication_status FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()
    assert status == "draft"
    current = (
        await session.execute(
            text("SELECT is_current FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()
    assert current is False


async def test_publish_fingerprint_mismatch_conflicts(session):
    owner = await make_user(session, role="estudiante")
    # Stored fingerprint that does not match title + staged_abstract.
    doc_id, _ = await _seed_candidate(
        session, owner_user_id=owner, fingerprint="0" * 32
    )
    ctx = UserCtx(user_id=owner, is_unsam=True, role="estudiante")

    with pytest.raises(documents.PublishConflict):
        await documents.publish(session, ctx, doc_id)


async def test_publish_by_non_owner_is_not_found(session):
    owner = await make_user(session, role="estudiante")
    other = await make_user(session, role="estudiante")
    doc_id, _ = await _seed_candidate(session, owner_user_id=owner)
    other_ctx = UserCtx(user_id=other, is_unsam=True, role="estudiante")

    with pytest.raises(documents.DocumentNotFound):
        await documents.publish(session, other_ctx, doc_id)


async def test_published_publico_visible_to_invitado(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_candidate(session, owner_user_id=owner)
    await documents.publish(session, _ctx(owner), doc_id)

    results = await search_query.run(
        session, filters=search_query.Filters(q="documento"), user_ctx=GUEST
    )
    assert doc_id in _doc_ids(results)


async def test_published_interno_visible_to_estudiante_not_invitado(session):
    owner = await make_user(session)
    doc_id, _ = await _seed_candidate(session, owner_user_id=owner)
    await session.execute(
        text("UPDATE documents SET visibility = 'interno' WHERE id = :id"),
        {"id": doc_id},
    )
    await documents.publish(session, _ctx(owner), doc_id)

    # A different UNSAM reader (not an author) sees the interno document.
    reader = await make_user(session)
    seen = await search_query.run(
        session, filters=search_query.Filters(q="documento"), user_ctx=_ctx(reader)
    )
    assert doc_id in _doc_ids(seen)

    hidden = await search_query.run(
        session, filters=search_query.Filters(q="documento"), user_ctx=GUEST
    )
    assert doc_id not in _doc_ids(hidden)


async def test_patch_title_after_publish_reindexes_and_stays_published(session):
    owner = await make_user(session)
    doc_id, version_id = await _seed_candidate(session, owner_user_id=owner)
    await documents.publish(session, _ctx(owner), doc_id)

    await documents.update_draft_metadata(
        session, _ctx(owner), doc_id, title="Título publicado revisado"
    )

    names = await _enqueued_task_names(session, version_id)
    assert any(n.endswith("refresh_headline") for n in names)

    status = (
        await session.execute(
            text("SELECT publication_status FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()
    assert status == "published"
