"""Integration tests for core/documents.soft_delete — the delete leg of the
deletion lifecycle (module map §core/documents, issue #65). Owner-only,
stamp-once, and immediate reader-invisibility through the inherited
soft_deleted_at IS NULL exclusion."""
from __future__ import annotations

from datetime import timedelta

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


async def test_restore_clears_soft_deleted_at_for_owner(session):
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(session, soft_deleted=True)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    assert await _soft_deleted_at(session, doc_id) is not None

    await documents.restore(session, _ctx(owner), doc_id)

    assert await _soft_deleted_at(session, doc_id) is None


async def test_restore_of_live_document_is_not_found(session):
    """A live document has no soft_deleted_at; restorable_where matches zero
    rows → DocumentNotFound (story 12)."""
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(session, soft_deleted=False)
    await make_document_author(session, doc_id, user_id=owner, status="owner")

    with pytest.raises(documents.DocumentNotFound):
        await documents.restore(session, _ctx(owner), doc_id)


async def test_restore_by_non_owner_is_not_found(session):
    """Another user's deleted document and an accepted coautor's both 404 —
    restore is owner-only, no existence leak (story 20)."""
    owner = await make_user(session, role="estudiante")
    coautor = await make_user(session, role="estudiante")
    stranger = await make_user(session, role="estudiante")
    doc_id = await make_document(session, soft_deleted=True)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await make_document_author(session, doc_id, user_id=coautor, status="accepted")

    with pytest.raises(documents.DocumentNotFound):
        await documents.restore(session, _ctx(coautor), doc_id)
    with pytest.raises(documents.DocumentNotFound):
        await documents.restore(session, _ctx(stranger), doc_id)

    assert await _soft_deleted_at(session, doc_id) is not None


async def test_list_deleted_documents_returns_only_callers_own_soft_deleted(session):
    owner = await make_user(session, role="estudiante")
    other = await make_user(session, role="estudiante")

    own_deleted = await make_document(
        session, soft_deleted=True, titulo="Eliminado propio"
    )
    await make_document_author(session, own_deleted, user_id=owner, status="owner")
    # Excluded: caller's live doc, a doc owned by someone else, and a doc where
    # the caller is only an accepted coautor.
    own_live = await make_document(session, soft_deleted=False)
    await make_document_author(session, own_live, user_id=owner, status="owner")
    other_deleted = await make_document(session, soft_deleted=True)
    await make_document_author(session, other_deleted, user_id=other, status="owner")
    coautor_deleted = await make_document(session, soft_deleted=True)
    await make_document_author(session, coautor_deleted, user_id=other, status="owner")
    await make_document_author(session, coautor_deleted, user_id=owner, status="accepted")
    await session.commit()

    rows = await documents.list_deleted_documents(session, _ctx(owner))

    assert [r.id for r in rows] == [own_deleted]
    assert rows[0].title == "Eliminado propio"


async def test_list_deleted_documents_ordered_by_soft_deleted_at_desc(session):
    owner = await make_user(session, role="estudiante")
    older = await make_document(session, soft_deleted=True)
    newer = await make_document(session, soft_deleted=True)
    await make_document_author(session, older, user_id=owner, status="owner")
    await make_document_author(session, newer, user_id=owner, status="owner")
    await session.execute(
        text(
            "UPDATE documents SET soft_deleted_at = now() - interval '5 days' "
            "WHERE id = :id"
        ),
        {"id": older},
    )
    await session.commit()

    rows = await documents.list_deleted_documents(session, _ctx(owner))

    assert [r.id for r in rows] == [newer, older]


async def test_list_deleted_documents_projects_purge_at_180_days(session):
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(session, soft_deleted=True)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await session.commit()

    [row] = await documents.list_deleted_documents(session, _ctx(owner))

    assert row.purge_at - row.soft_deleted_at == timedelta(days=180)


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


async def test_restore_returns_published_document_to_every_reader_surface(session):
    """AC#4 (published side): restore is a true undo — a deleted published
    document reappears in búsqueda, detalle, descarga, relacionados, and the
    conteo under its original visibilidad. Nothing reconstructed: delete only
    hid the row via the inherited exclusion."""
    owner = await make_user(session, role="estudiante")
    target = await make_document(
        session,
        visibility="publico",
        publication_status="published",
        titulo="Trabajo restaurable",
    )
    await make_document_author(session, target, user_id=owner, status="owner")
    await make_chunk(
        session,
        target,
        chunk_seq=0,
        is_headline=True,
        body_text="ornitorrincocuantico tema del trabajo",
        embedding=_vec(1.0),
    )
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

    async def visible_everywhere() -> bool:
        res = await search_query.run(
            session,
            filters=search_query.Filters(q="ornitorrincocuantico"),
            user_ctx=GUEST,
        )
        return (
            target in [r.doc_id for r in res.rows]
            and res.total == 1
            and await documents.get_detail(session, target, GUEST) is not None
            and await documents.get_readable_main_file(session, target, GUEST) is not None
            and target in await related_ids()
        )

    await documents.soft_delete(session, _ctx(owner), target)
    assert not await visible_everywhere()

    await documents.restore(session, _ctx(owner), target)

    assert await visible_everywhere()
    # Original visibilidad preserved (delete/restore never touch it).
    detail = await documents.get_detail(session, target, GUEST)
    assert detail is not None


async def test_restore_returns_draft_with_versions_attachments_coautores_intact(session):
    """AC#4 (draft side): a restored draft returns to Mis trabajos editable with
    version history, attachments, and coautores intact — none were mutated by
    delete/restore (stories 8-11)."""
    owner = await make_user(session, role="estudiante", name="Ada")
    coautor = await make_user(session, role="estudiante", name="Bob")
    doc_id = await make_document(session, publication_status="draft", titulo="t")
    await make_document_author(
        session, doc_id, user_id=owner, status="owner", display_name="Ada"
    )
    await make_document_author(
        session, doc_id, user_id=coautor, status="accepted", display_name="Bob"
    )
    from buscasam.core.chunk import headline_fingerprint

    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, headline_fingerprint, is_current) "
            "VALUES (:d, 1, decode(repeat('00', 32), 'hex'), 'v1.pdf', 1, "
            " 'application/pdf', :uid, 'indexed', :fp, true)"
        ),
        {"d": doc_id, "uid": owner, "fp": headline_fingerprint("t", "")},
    )
    await session.execute(
        text(
            "INSERT INTO document_attachments (doc_id, sha256, original_filename, bytes, mime) "
            "VALUES (:d, decode(:sha, 'hex'), 'datos.csv', 512, 'text/csv')"
        ),
        {"d": doc_id, "sha": "bb" * 32},
    )
    await session.commit()

    before = await documents.get_draft_state(session, _ctx(owner), doc_id)

    await documents.soft_delete(session, _ctx(owner), doc_id)
    own_ids = {d.id for d in await documents.list_own_documents(session, _ctx(owner))}
    assert doc_id not in own_ids  # gone from Mis trabajos while deleted

    await documents.restore(session, _ctx(owner), doc_id)

    own_ids = {d.id for d in await documents.list_own_documents(session, _ctx(owner))}
    assert doc_id in own_ids  # back in Mis trabajos
    after = await documents.get_draft_state(session, _ctx(owner), doc_id)
    assert after.versions == before.versions
    assert after.attachments == before.attachments
    assert after.coauthors == before.coauthors
