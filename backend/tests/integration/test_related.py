"""Integration tests for core/related.fetch_related (issue #45)."""
from __future__ import annotations

import numpy as np
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import related
from buscasam.core.auth import GUEST, UserCtx
from tests.factories import make_chunk, make_document, make_document_author, make_user


def _student(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed_current_version(session: AsyncSession, doc_id: int) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " index_status, is_current) "
                "VALUES (:d, 1, decode(repeat('11', 32), 'hex'), 'fixture.pdf', "
                " 1, 'application/pdf', 'indexed', true) RETURNING id"
            ),
            {"d": doc_id},
        )
    ).scalar_one()


def _vec(seed: float) -> np.ndarray:
    """Return a unit-ish 1024-vector tilted toward `seed` along dim 0."""
    v = np.full(1024, 0.001, dtype=np.float16)
    v[0] = seed
    norm = np.linalg.norm(v.astype(np.float32))
    return (v.astype(np.float32) / norm).astype(np.float16)


async def _add_headline(
    session: AsyncSession, doc_id: int, embedding: np.ndarray
) -> None:
    await make_chunk(
        session,
        doc_id,
        chunk_seq=0,
        is_headline=True,
        body_text=f"headline {doc_id}",
        embedding=embedding,
    )


async def test_returns_none_when_source_fails_readable_where(session):
    """Tracer: invitado on an interno source gets None (source-side access)."""
    source_id = await make_document(session, visibility="interno")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))
    await session.commit()

    assert (
        await related.fetch_related(
            session, source_id, GUEST, min_semantic_similarity=0.78
        )
    ) is None


async def test_excludes_source_doc_id_and_returns_candidate_metadata(session):
    """Source has a headline; a sibling público with a near-identical headline
    embedding must appear, the source must not appear in its own rail."""
    from datetime import date

    source_id = await make_document(
        session, visibility="publico", titulo="Source title"
    )
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))

    sibling_id = await make_document(
        session,
        visibility="publico",
        titulo="Sibling title",
        area_path="escuela_ciencia.carrera_informatica",
        tipo="paper",
        fecha=date(2024, 1, 15),
    )
    await _seed_current_version(session, sibling_id)
    await _add_headline(session, sibling_id, _vec(1.0))
    author_id = await make_user(session, name="Ada")
    await make_document_author(
        session, sibling_id, user_id=author_id, status="owner", display_name="Ada"
    )
    await session.commit()

    rows = await related.fetch_related(
        session, source_id, GUEST, min_semantic_similarity=0.78
    )

    assert rows is not None
    doc_ids = [r.doc_id for r in rows]
    assert source_id not in doc_ids
    assert sibling_id in doc_ids
    sibling = next(r for r in rows if r.doc_id == sibling_id)
    assert sibling.titulo == "Sibling title"
    assert sibling.area_path == "escuela_ciencia.carrera_informatica"
    assert sibling.tipo == "paper"
    assert sibling.fecha == date(2024, 1, 15)
    assert [a.display_name for a in sibling.autores] == ["Ada"]
    assert sibling.autores[0].user_id == author_id
    assert 0.78 <= sibling.similarity <= 1.0


async def test_drops_candidates_below_min_semantic_similarity(session):
    """A candidate with a near-orthogonal headline embedding is excluded."""
    source_id = await make_document(session, visibility="publico", titulo="src")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))

    far_id = await make_document(session, visibility="publico", titulo="far")
    await _seed_current_version(session, far_id)
    far_vec = np.full(1024, 0.001, dtype=np.float16)
    far_vec[1023] = 1.0  # orthogonal to dim-0-heavy source
    norm = np.linalg.norm(far_vec.astype(np.float32))
    await _add_headline(
        session, far_id, (far_vec.astype(np.float32) / norm).astype(np.float16)
    )
    await session.commit()

    rows = await related.fetch_related(
        session, source_id, GUEST, min_semantic_similarity=0.78
    )

    assert rows == []


async def test_caps_results_at_k(session):
    """With 6 similar candidates, only k=5 are returned."""
    source_id = await make_document(session, visibility="publico", titulo="src")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))
    for _ in range(6):
        cand_id = await make_document(session, visibility="publico", titulo="cand")
        await _seed_current_version(session, cand_id)
        await _add_headline(session, cand_id, _vec(1.0))
    await session.commit()

    rows = await related.fetch_related(
        session, source_id, GUEST, min_semantic_similarity=0.78
    )

    assert rows is not None
    assert len(rows) == 5


async def test_candidates_unreadable_to_requester_are_absent(session):
    """Three readable-by-someone candidates above the floor; each role sees only
    the ones their readable_where admits, never the others."""
    source_id = await make_document(session, visibility="publico", titulo="src")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))

    publico_id = await make_document(session, visibility="publico", titulo="pub")
    await _seed_current_version(session, publico_id)
    await _add_headline(session, publico_id, _vec(1.0))

    interno_id = await make_document(session, visibility="interno", titulo="int")
    await _seed_current_version(session, interno_id)
    await _add_headline(session, interno_id, _vec(1.0))

    privado_id = await make_document(session, visibility="privado", titulo="priv")
    await _seed_current_version(session, privado_id)
    await _add_headline(session, privado_id, _vec(1.0))
    owner_id = await make_user(session, name="Owner")
    accepted_id = await make_user(session, name="Accepted")
    stranger_id = await make_user(session, name="Stranger")
    await make_document_author(
        session, privado_id, user_id=owner_id, status="owner"
    )
    await make_document_author(
        session, privado_id, user_id=accepted_id, status="accepted"
    )
    await session.commit()

    # Invitado: only público.
    invitado_rows = await related.fetch_related(
        session, source_id, GUEST, min_semantic_similarity=0.78
    )
    assert {r.doc_id for r in invitado_rows} == {publico_id}

    # Stranger estudiante: público + interno; not privado.
    stranger_rows = await related.fetch_related(
        session, source_id, _student(stranger_id), min_semantic_similarity=0.78
    )
    assert {r.doc_id for r in stranger_rows} == {publico_id, interno_id}

    # Accepted coautor on privado: público + interno + privado.
    accepted_rows = await related.fetch_related(
        session, source_id, _student(accepted_id), min_semantic_similarity=0.78
    )
    assert {r.doc_id for r in accepted_rows} == {publico_id, interno_id, privado_id}


async def test_source_access_check_runs_before_headline_embedding_load(session):
    """When the source is denied, no cosine SQL fires — the source headline
    embedding must not be loaded before the access check (ADR-0010 §6,
    PRD story 33)."""
    source_id = await make_document(session, visibility="interno")
    await _seed_current_version(session, source_id)
    await _add_headline(session, source_id, _vec(1.0))
    await session.commit()

    sync_engine = session.bind.sync_engine
    seen: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _capture)
    try:
        result = await related.fetch_related(
            session, source_id, GUEST, min_semantic_similarity=0.78
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", _capture)

    assert result is None
    assert not any("<=>" in s for s in seen), (
        "cosine cast must not run when source is denied"
    )
    assert not any(
        "chunks" in s and "is_headline" in s for s in seen
    ), "headline chunk must not be loaded when source is denied"


async def test_returns_empty_when_source_has_no_headline_chunk(session):
    """Readable source without an `is_headline AND is_current` chunk: rail hides
    via `[]` (mid-flight reindex, candidate-only state, pre-headline doc)."""
    source_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, source_id)
    # Body chunk only — no headline row.
    await make_chunk(
        session,
        source_id,
        chunk_seq=1,
        is_headline=False,
        body_text="body without headline",
        embedding=_vec(1.0),
    )
    await session.commit()

    assert (
        await related.fetch_related(
            session, source_id, GUEST, min_semantic_similarity=0.78
        )
    ) == []
