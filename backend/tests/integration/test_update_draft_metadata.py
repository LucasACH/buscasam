"""Integration tests for core/documents.update_draft_metadata edit-during-candidate
fan-out (issue #60, module map version-replacement §core/documents)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

from buscasam.core import chunk as chunkmod
from buscasam.core import documents
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_document_author, make_user


def _ctx(uid: int) -> UserCtx:
    return UserCtx(user_id=uid, is_unsam=True, role="estudiante")


async def _enqueued_refresh_version_ids(session) -> set[int]:
    rows = (
        await session.execute(
            text(
                "SELECT (args->>'version_id')::int AS vid FROM procrastinate_jobs "
                "WHERE task_name LIKE '%refresh_headline'"
            )
        )
    ).scalars().all()
    return set(rows)


async def _insert_version(
    session,
    doc_id: int,
    uid: int,
    *,
    version_no: int,
    is_current: bool,
    first_published: bool,
    titulo: str,
    index_status: str = "indexed",
    staged_abstract: str | None = None,
    staged_keywords: list[str] | None = None,
    staged_fecha: date | None = None,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " uploaded_by, index_status, is_current, "
                " first_published_at, staged_abstract, staged_keywords, "
                " staged_fecha, headline_fingerprint) "
                "VALUES (:doc, :vno, decode(repeat(:sha, 32), 'hex'), 'f.pdf', 1, "
                " 'application/pdf', :uid, :st, :cur, "
                " CASE WHEN :fp_set THEN now() ELSE NULL END, :abs, :kw, :fec, :fp) "
                "RETURNING id"
            ),
            {
                "doc": doc_id,
                "vno": version_no,
                "sha": f"{version_no:02d}",
                "uid": uid,
                "st": index_status,
                "cur": is_current,
                "fp_set": first_published,
                "abs": staged_abstract,
                "kw": staged_keywords,
                "fec": staged_fecha,
                "fp": chunkmod.headline_fingerprint(titulo, staged_abstract or ""),
            },
        )
    ).scalar_one()


async def _seed_published_with_candidate(
    session,
    *,
    titulo: str = "Título original",
    published_abstract: str = "resumen publicado",
    candidate_abstract: str = "resumen candidato",
    candidate_status: str = "indexed",
) -> tuple[int, int, int, int]:
    """A published document (version 1 current) plus a never-published candidate
    (version 2). Returns (uid, doc_id, published_version_id, candidate_version_id)."""
    uid = await make_user(session)
    doc_id = await make_document(
        session, publication_status="published", titulo=titulo
    )
    await make_document_author(session, doc_id, user_id=uid, status="owner")
    published_id = await _insert_version(
        session, doc_id, uid, version_no=1, is_current=True, first_published=True,
        titulo=titulo, staged_abstract=published_abstract,
    )
    candidate_id = await _insert_version(
        session, doc_id, uid, version_no=2, is_current=False, first_published=False,
        titulo=titulo, index_status=candidate_status,
        staged_abstract=candidate_abstract,
    )
    return uid, doc_id, published_id, candidate_id


async def test_title_edit_fans_refresh_to_published_and_candidate(session):
    uid, doc_id, published_id, candidate_id = await _seed_published_with_candidate(
        session
    )

    await documents.update_draft_metadata(
        session, _ctx(uid), doc_id, title="Título nuevo"
    )

    titulo = (
        await session.execute(
            text("SELECT titulo FROM documents WHERE id = :id"), {"id": doc_id}
        )
    ).scalar_one()
    assert titulo == "Título nuevo"

    assert {published_id, candidate_id} <= await _enqueued_refresh_version_ids(session)


async def _staged_abstract(session, version_id: int) -> str | None:
    return (
        await session.execute(
            text("SELECT staged_abstract FROM document_versions WHERE id = :id"),
            {"id": version_id},
        )
    ).scalar_one()


async def test_discarded_candidate_excluded_from_fan_out(session):
    uid, doc_id, published_id, discarded_id = await _seed_published_with_candidate(
        session,
        candidate_abstract="resumen descartado",
        candidate_status="discarded",
    )

    await documents.update_draft_metadata(
        session, _ctx(uid), doc_id, abstract="resumen corregido"
    )

    # The discarded row's staged_* must not move and it gets no reindex.
    assert await _staged_abstract(session, discarded_id) == "resumen descartado"
    refreshed = await _enqueued_refresh_version_ids(session)
    assert discarded_id not in refreshed
    # The published version still receives the write-through + reindex.
    assert await _staged_abstract(session, published_id) == "resumen corregido"
    assert published_id in refreshed


async def test_abstract_edit_fans_to_both_versions(session):
    uid, doc_id, published_id, candidate_id = await _seed_published_with_candidate(
        session,
        published_abstract="resumen publicado",
        candidate_abstract="resumen candidato",
    )

    await documents.update_draft_metadata(
        session, _ctx(uid), doc_id, abstract="resumen unificado"
    )

    assert await _staged_abstract(session, published_id) == "resumen unificado"
    assert await _staged_abstract(session, candidate_id) == "resumen unificado"
    assert {published_id, candidate_id} <= await _enqueued_refresh_version_ids(session)


async def test_processing_candidate_staged_but_not_reindexed(session):
    uid, doc_id, published_id, candidate_id = await _seed_published_with_candidate(
        session, candidate_status="processing"
    )

    await documents.update_draft_metadata(
        session, _ctx(uid), doc_id, abstract="resumen corregido"
    )

    # staged_* write-through happens regardless of index_status...
    assert await _staged_abstract(session, candidate_id) == "resumen corregido"
    refreshed = await _enqueued_refresh_version_ids(session)
    # ...but index_document owns a processing candidate's headline, so no
    # concurrent refresh is enqueued for it; the indexed published version is.
    assert candidate_id not in refreshed
    assert published_id in refreshed
