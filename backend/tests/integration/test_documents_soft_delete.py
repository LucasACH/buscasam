"""Integration tests for core/documents.soft_delete — the delete leg of the
deletion lifecycle (module map §core/documents, issue #65). Owner-only,
stamp-once, and immediate reader-invisibility through the inherited
soft_deleted_at IS NULL exclusion."""
from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import text

from buscasam.core import documents, related, search_query
from buscasam.core.auth import GUEST, UserCtx
from tests.factories import make_chunk, make_document, make_document_author, make_user


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


def _vec(seed: float) -> np.ndarray:
    """A unit 1024-vector tilted toward `seed` along dim 0 (test_related precedent)."""
    v = np.full(1024, 0.001, dtype=np.float16)
    v[0] = seed
    norm = np.linalg.norm(v.astype(np.float32))
    return (v.astype(np.float32) / norm).astype(np.float16)


async def _soft_deleted_at(session, doc_id: int):
    return (
        await session.execute(
            text("SELECT soft_deleted_at FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
    ).scalar_one()


async def test_soft_delete_stamps_soft_deleted_at(session):
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")

    assert await _soft_deleted_at(session, doc_id) is None

    await documents.soft_delete(session, _ctx(owner), doc_id)

    assert await _soft_deleted_at(session, doc_id) is not None


async def test_soft_delete_by_non_owner_is_not_found(session):
    owner = await make_user(session, role="estudiante")
    other = await make_user(session, role="estudiante")
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")

    with pytest.raises(documents.DocumentNotFound):
        await documents.soft_delete(session, _ctx(other), doc_id)

    assert await _soft_deleted_at(session, doc_id) is None


async def test_soft_delete_by_accepted_coautor_is_not_found(session):
    """Accepted coautores and strangers are indistinguishable → 404, no leak."""
    owner = await make_user(session, role="estudiante")
    coautor = await make_user(session, role="estudiante")
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=coautor, status="accepted")

    with pytest.raises(documents.DocumentNotFound):
        await documents.soft_delete(session, _ctx(coautor), doc_id)

    assert await _soft_deleted_at(session, doc_id) is None


async def test_soft_delete_unknown_doc_is_not_found(session):
    owner = await make_user(session, role="estudiante")

    with pytest.raises(documents.DocumentNotFound):
        await documents.soft_delete(session, _ctx(owner), 999999)


async def test_soft_delete_is_stamp_once_no_op(session):
    """Re-deleting an already-deleted document never moves the timestamp — the
    180-día window counts from the first deletion (story 13/14)."""
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(session, publication_status="published")
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    # Simulate a prior deletion at a fixed past instant.
    prior = (
        await session.execute(
            text(
                "UPDATE documents SET soft_deleted_at = now() - interval '10 days' "
                "WHERE id = :id RETURNING soft_deleted_at"
            ),
            {"id": doc_id},
        )
    ).scalar_one()

    await documents.soft_delete(session, _ctx(owner), doc_id)

    assert await _soft_deleted_at(session, doc_id) == prior


async def test_soft_delete_moderation_hidden_is_still_deletable(session):
    """The owner gate carries no moderation filter; deleting leaves
    moderation_hidden_at and publication_status untouched (orthogonal lifecycle)."""
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(
        session, publication_status="published", moderation_hidden=True
    )
    await make_document_author(session, doc_id, user_id=owner, status="owner")

    await documents.soft_delete(session, _ctx(owner), doc_id)

    row = (
        await session.execute(
            text(
                "SELECT soft_deleted_at, moderation_hidden_at, publication_status "
                "FROM documents WHERE id = :id"
            ),
            {"id": doc_id},
        )
    ).mappings().one()
    assert row["soft_deleted_at"] is not None
    assert row["moderation_hidden_at"] is not None
    assert row["publication_status"] == "published"


async def test_soft_delete_hides_document_from_every_reader_surface(session):
    """AC#4: after soft_delete the document drops from búsqueda, detalle,
    descarga, relacionados, and the unfiltered conteo. None re-implemented here —
    every surface inherits the soft_deleted_at IS NULL exclusion in readable_where."""
    owner = await make_user(session, role="estudiante")
    target = await make_document(
        session,
        visibility="publico",
        publication_status="published",
        titulo="Trabajo eliminable",
    )
    await make_document_author(session, target, user_id=owner, status="owner")
    await make_chunk(
        session,
        target,
        chunk_seq=0,
        is_headline=True,
        body_text="rinocerontesemantico tema del trabajo",
        embedding=_vec(1.0),
    )
    # A sibling source so `target` surfaces in its relacionados rail.
    source = await make_document(
        session, visibility="publico", publication_status="published", titulo="Fuente"
    )
    await make_chunk(
        session,
        source,
        chunk_seq=0,
        is_headline=True,
        body_text="headline fuente",
        embedding=_vec(1.0),
    )
    await session.commit()

    async def related_ids() -> set[int]:
        rows = await related.fetch_related(
            session, source, GUEST, min_semantic_similarity=0.78
        )
        return {r.doc_id for r in (rows or [])}

    # Visible on all five surfaces before deletion.
    before = await search_query.run(
        session, filters=search_query.Filters(q="rinocerontesemantico"), user_ctx=GUEST
    )
    assert target in [r.doc_id for r in before.rows]  # búsqueda
    assert before.total == 1  # unfiltered conteo
    assert await documents.get_detail(session, target, GUEST) is not None  # detalle
    assert (
        await documents.get_readable_main_file(session, target, GUEST) is not None
    )  # descarga
    assert target in await related_ids()  # relacionados

    await documents.soft_delete(session, _ctx(owner), target)

    # Gone from all five after deletion.
    after = await search_query.run(
        session, filters=search_query.Filters(q="rinocerontesemantico"), user_ctx=GUEST
    )
    assert target not in [r.doc_id for r in after.rows]  # búsqueda
    assert after.total == 0  # unfiltered conteo
    assert await documents.get_detail(session, target, GUEST) is None  # detalle
    assert (
        await documents.get_readable_main_file(session, target, GUEST) is None
    )  # descarga
    assert target not in await related_ids()  # relacionados
