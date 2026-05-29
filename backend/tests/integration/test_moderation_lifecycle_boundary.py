"""Lifecycle boundary assertions for moderation-hidden documents (issue #79,
module map §report-moderation, ADR-0010 §6).

These lock the invariants that keep moderation-hidden a clean, reversible state
independent of author soft-deletion. The per-surface exclusion is inherited from
the `moderation_hidden_at IS NULL` baked into `core/document_access` predicates;
this slice cross-checks the boundary once and asserts hide ⟂ soft-delete — it
does not re-implement or re-test the exclusion per surface.
"""
from __future__ import annotations

from sqlalchemy import text

from buscasam.core import jobs, search_query
from buscasam.core.auth import UserCtx
from buscasam.core.documents import (
    get_detail,
    get_readable_attachment,
    get_readable_main_file,
    soft_delete,
)
from buscasam.core.document_access import invitado_where
from buscasam.core.moderation import hide
from buscasam.core.related import fetch_related
from buscasam.core.search_query import Filters
from tests.factories import (
    make_chunk,
    make_document,
    make_document_author,
    make_user,
)


def _docente_ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="docente")


async def _add_current_version(session, doc_id: int) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode('aa', 'hex'), 'f.pdf', 1, 'application/pdf', "
            "        'indexed', true, now())"
        ),
        {"d": doc_id},
    )


async def _add_attachment(session, doc_id: int) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime) "
                "VALUES (:d, decode('bb', 'hex'), 'a.pdf', 512, 'application/pdf') "
                "RETURNING id"
            ),
            {"d": doc_id},
        )
    ).scalar_one()


async def test_hidden_document_unreachable_through_every_surface(session):
    """Story 30: a single cross-check that a moderation-hidden document vanishes
    from search, detail, related, download, attachments, and sitemap — the
    surfaces all compose `readable_where`/`invitado_where`, which exclude it."""
    reader = await make_user(session, role="estudiante")
    reader_ctx = UserCtx(user_id=reader, is_unsam=True, role="estudiante")

    # A fully-fleshed publico document — readable on every surface but for the
    # hide: current version (detail/download), attachment, headline chunk.
    hidden = await make_document(session, visibility="publico", titulo="Oculto")
    await _add_current_version(session, hidden)
    att_id = await _add_attachment(session, hidden)
    await make_chunk(session, hidden, is_headline=True, body_text="cuerpo oculto")

    # A readable companion source so `related` would surface `hidden` as a
    # similarity candidate (shared default embedding) but for the hide.
    source = await make_document(session, visibility="publico", titulo="Fuente")
    await make_chunk(session, source, is_headline=True, body_text="cuerpo fuente")

    docente = await make_user(session, role="docente")
    report_id = (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                "VALUES (:d, :u, 'spam') RETURNING id"
            ),
            {"d": hidden, "u": await make_user(session)},
        )
    ).scalar_one()
    await hide(session, _docente_ctx(docente), report_id, "spam")
    await session.commit()

    # search
    results = await search_query.run(
        session, filters=Filters(q="", orden="recientes"), user_ctx=reader_ctx
    )
    assert hidden not in {r.doc_id for r in results.rows}

    # detail
    assert await get_detail(session, hidden, reader_ctx) is None

    # related (candidate exclusion; source itself stays readable)
    related = await fetch_related(
        session, source, reader_ctx, min_semantic_similarity=0.78
    )
    assert related is not None
    assert hidden not in {r.doc_id for r in related}

    # download (current main file)
    assert await get_readable_main_file(session, hidden, reader_ctx) is None

    # attachments
    assert await get_readable_attachment(session, hidden, att_id, reader_ctx) is None

    # sitemap (anonymous publico adapter)
    where = invitado_where("d")
    sitemap_ids = set(
        (await session.execute(text(f"SELECT d.id FROM documents d WHERE {where}")))
        .scalars()
        .all()
    )
    assert hidden not in sitemap_ids


async def test_hiding_starts_no_purge_timer(session):
    """Story 31: hiding sets no `soft_deleted_at` and enqueues no purge — the
    180-día retention sweep keys off `soft_deleted_at`, so a merely-hidden
    document has no purge timer running and the sweep never selects it."""
    docente = await make_user(session, role="docente")
    doc_id = await make_document(session)
    report_id = (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                "VALUES (:d, :u, 'spam') RETURNING id"
            ),
            {"d": doc_id, "u": await make_user(session)},
        )
    ).scalar_one()

    await hide(session, _docente_ctx(docente), report_id, "spam")

    soft_deleted_at = (
        await session.execute(
            text("SELECT soft_deleted_at FROM documents WHERE id = :d"), {"d": doc_id}
        )
    ).scalar_one()
    assert soft_deleted_at is None

    # The retention sweep keys off soft_deleted_at alone — a hidden, never-
    # author-deleted document carries no purge timer and is left untouched.
    await jobs._run_purge_deleted(session)
    survives = (
        await session.execute(
            text("SELECT 1 FROM documents WHERE id = :d"), {"d": doc_id}
        )
    ).first()
    assert survives is not None


async def test_author_can_soft_delete_a_hidden_document(session):
    """Story 32: hiding and author soft-deletion are independent states; an owner
    can still soft-delete a document a Docente has hidden, and both columns
    coexist without conflict."""
    docente = await make_user(session, role="docente")
    owner = await make_user(session, role="estudiante")
    doc_id = await make_document(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    report_id = (
        await session.execute(
            text(
                "INSERT INTO document_reports (doc_id, reporter_user_id, reason) "
                "VALUES (:d, :u, 'spam') RETURNING id"
            ),
            {"d": doc_id, "u": await make_user(session)},
        )
    ).scalar_one()

    await hide(session, _docente_ctx(docente), report_id, "spam")
    await soft_delete(session, UserCtx(user_id=owner, is_unsam=True, role="estudiante"), doc_id)

    row = (
        await session.execute(
            text(
                "SELECT moderation_hidden_at, soft_deleted_at "
                "FROM documents WHERE id = :d"
            ),
            {"d": doc_id},
        )
    ).mappings().one()
    assert row["moderation_hidden_at"] is not None
    assert row["soft_deleted_at"] is not None
