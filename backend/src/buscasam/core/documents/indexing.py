"""Worker-side indexing writeback for document versions (ADR-0008, ADR-0011 §5).

The seam the durable queue calls into: begin/stage/finalize the index pipeline,
refresh the headline, and stamp terminal failure. Every write is gated on the
version's index_status so a descartar committed mid-IO leaves no resurrected
rows."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import notifications
from buscasam.core.embed import halfvec_literal
from buscasam.settings import settings

from buscasam.core.documents._shared import _EMBEDDING_MODEL_VERSION
from buscasam.core.documents.exceptions import DocumentNotFound
from buscasam.core.documents.versions import CandidateVersion, load_candidate

if TYPE_CHECKING:
    from buscasam.core.chunk import Chunk
    from buscasam.core.extract import IndexableMetadata


async def _begin_indexing(
    session: AsyncSession, version_id: int
) -> CandidateVersion | None:
    status = (
        await session.execute(
            text(
                "SELECT index_status FROM document_versions "
                "WHERE id = :id FOR UPDATE"
            ),
            {"id": version_id},
        )
    ).scalar_one_or_none()
    if status is None:
        raise DocumentNotFound
    # ADR-0011 §5: 'discarded' is terminal — a descartar committed before the
    # worker began (or between attempts) aborts indexing with no resurrected
    # writes. 'indexed' short-circuits the retry-safe duplicate path.
    if status in ("indexed", "discarded"):
        return None
    await session.execute(
        text(
            "UPDATE document_versions "
            "SET index_status = 'processing', index_stage = 'reading' "
            "WHERE id = :id"
        ),
        {"id": version_id},
    )
    return await load_candidate(session, version_id)


async def set_index_stage(
    session: AsyncSession, version_id: int, stage: str
) -> None:
    """Record the worker's current pipeline checkpoint for the editar progress
    UI. Guarded on index_status='processing' (like the finalize write) so a
    descartar committed mid-IO leaves the stage untouched — a no-op on a
    discarded/failed/indexed row. Advisory only; never gates publish."""
    await session.execute(
        text(
            "UPDATE document_versions SET index_stage = :stage "
            "WHERE id = :id AND index_status = 'processing'"
        ),
        {"stage": stage, "id": version_id},
    )


async def write_indexed_candidate(
    session: AsyncSession,
    version_id: int,
    *,
    body: list["Chunk"],
    headline: "Chunk",
    embeds: list[np.ndarray],
    meta: "IndexableMetadata",
    headline_fingerprint: str,
) -> None:
    # ADR-0011 §5: gate the whole write on index_status='processing'. A descartar
    # committed after _begin_indexing released its lock leaves the row 'discarded';
    # the guard then makes the chunk inserts + status flip a clean no-op so no
    # chunks materialize on a cancelled candidate. FOR UPDATE serializes against a
    # concurrent descartar that has not yet committed.
    doc_id = (
        await session.execute(
            text(
                "SELECT doc_id FROM document_versions "
                "WHERE id = :id AND index_status = 'processing' FOR UPDATE"
            ),
            {"id": version_id},
        )
    ).scalar_one_or_none()
    if doc_id is None:
        return

    all_chunks = [headline, *body]
    for c, emb in zip(all_chunks, embeds):
        await session.execute(
            text(
                "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
                "  embedding, embedding_model_version, version_id, is_current) "
                "VALUES (:doc_id, :seq, :hl, :body, "
                "        cast(:emb as halfvec(1024)), :mv, :vid, false)"
            ),
            {
                "doc_id": doc_id,
                "seq": c.chunk_seq,
                "hl": c.is_headline,
                "body": c.body_text,
                "emb": halfvec_literal(emb),
                "mv": _EMBEDDING_MODEL_VERSION,
                "vid": version_id,
            },
        )

    # Extraction is an initial fill, not an overwrite: a user who lands on the
    # editar form while still `processing` can save their own staged_* via
    # save-on-blur. COALESCE leaves any column they already wrote untouched
    # (staged_* are NULL until first written), so the author edit always wins.
    # generated_* is the immutable extractor snapshot (issue #94): written once
    # here from the raw meta, never COALESCE-guarded and never touched by an
    # author edit, so any staged field can be reverted to what the extractor
    # produced.
    await session.execute(
        text(
            "UPDATE document_versions SET "
            "  index_status = 'indexed', "
            "  index_stage = NULL, "
            "  staged_abstract = COALESCE(staged_abstract, :abstract), "
            "  staged_keywords = COALESCE(staged_keywords, :keywords), "
            "  staged_fecha = COALESCE(staged_fecha, :fecha), "
            "  generated_abstract = :abstract, "
            "  generated_keywords = :keywords, "
            "  generated_fecha = :fecha, "
            "  headline_fingerprint = :fp, "
            "  extract_pipeline_version = :pv, "
            "  indexed_at = now() "
            "WHERE id = :id"
        ),
        {
            "abstract": meta.abstract,
            "keywords": meta.keywords,
            "fecha": meta.fecha,
            "fp": headline_fingerprint,
            "pv": settings.extract_pipeline_version,
            "id": version_id,
        },
    )

    # A título/abstract edit can land after this task embedded its headline (the
    # index window spans minutes for OCR). The R001 guard suppresses the enqueue
    # while processing, so the stamped fingerprint is now stale against the
    # current título + preserved staged_abstract with no refresh queued — a
    # permanently stuck `reindexing_headline` gate. Detect the drift here and
    # enqueue the refresh ourselves so the headline catches up to the edit.
    from buscasam.core.chunk import headline_fingerprint as _compute_fp

    drift = (
        await session.execute(
            text(
                "SELECT d.titulo, v.staged_abstract "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.id = :id"
            ),
            {"id": version_id},
        )
    ).mappings().one()
    if _compute_fp(drift["titulo"], drift["staged_abstract"] or "") != headline_fingerprint:
        from buscasam.core import jobs

        await jobs.enqueue_refresh_headline(session, version_id)


async def write_headline(
    session: AsyncSession,
    version_id: int,
    headline: "Chunk",
    embed: np.ndarray,
    headline_fingerprint: str,
) -> None:
    """ADR-0007 §10: only write if the row's title+abstract still match the
    fingerprint the caller computed for this embedding. A racing edit that
    updates staged_abstract between embed-time and write-time wins."""
    from buscasam.core.chunk import headline_fingerprint as _compute_fp

    # ADR-0011 §5: gate on index_status='indexed' so a refresh_headline already
    # in flight when the candidate is descartado no-ops — it neither rewrites the
    # discarded version's headline chunk nor restamps its fingerprint. The
    # published current version is always 'indexed', so this is transparent to
    # the post-publish headline-reindex path.
    row = (
        await session.execute(
            text(
                "SELECT v.doc_id, v.is_current, d.titulo, v.staged_abstract "
                "FROM document_versions v JOIN documents d ON d.id = v.doc_id "
                "WHERE v.id = :id AND v.index_status = 'indexed' FOR UPDATE OF v"
            ),
            {"id": version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        return
    current_fp = _compute_fp(row["titulo"], row["staged_abstract"] or "")
    if current_fp != headline_fingerprint:
        # Title or abstract changed since this task computed its embedding;
        # let the newer refresh_headline task own the write.
        return
    doc_id = row["doc_id"]

    await session.execute(
        text(
            "DELETE FROM chunks WHERE version_id = :vid AND is_headline"
        ),
        {"vid": version_id},
    )
    await session.execute(
        text(
            "INSERT INTO chunks (doc_id, chunk_seq, is_headline, body_text, "
            "  embedding, embedding_model_version, version_id, is_current) "
            "VALUES (:doc_id, 0, true, :body, "
            "        cast(:emb as halfvec(1024)), :mv, :vid, :is_current)"
        ),
        {
            "doc_id": doc_id,
            "body": headline.body_text,
            "emb": halfvec_literal(embed),
            "mv": _EMBEDDING_MODEL_VERSION,
            "vid": version_id,
            "is_current": row["is_current"],
        },
    )
    await session.execute(
        text(
            "UPDATE document_versions SET headline_fingerprint = :fp WHERE id = :id"
        ),
        {"fp": headline_fingerprint, "id": version_id},
    )


async def mark_failed(
    session: AsyncSession, version_id: int, error: str
) -> None:
    """Candidate terminal-state writer (ADR-0008 §5, ADR-0010 §9).

    Single seam called by every fatal indexing path — recognized parse/OCR
    failures and exhausted transient failures (`core/jobs._run_attempt`). The
    UPDATE is first-write-wins so a later `exhausted retries:` reason cannot
    overwrite an earlier, more specific `corrupted:` cause. The notification
    insert is deduped at the unique (user_id, event_key) index.
    """
    cv = await load_candidate(session, version_id)
    # ADR-0011 §5: 'discarded' is terminal and excluded here too — a terminal
    # failure handler running after a descartar must not resurrect the row to
    # 'failed' nor notify. '<> failed' keeps first-write-wins (a later
    # exhausted-retries reason cannot overwrite an earlier corrupted cause).
    result = await session.execute(
        text(
            "UPDATE document_versions SET index_status = 'failed', "
            "  index_error = :err "
            "WHERE id = :id AND index_status NOT IN ('failed', 'discarded')"
        ),
        {"err": error, "id": version_id},
    )
    # No transition (already failed, or discarded mid-flight) → no notification.
    if result.rowcount == 0 or cv.owner_user_id is None:
        return
    await notifications.notify_indexing_failed(
        session,
        user_id=cv.owner_user_id,
        doc_id=cv.doc_id,
        version_id=version_id,
        error=error,
    )


async def mark_headline_refresh_failed(
    session: AsyncSession, version_id: int, *, reason: str
) -> None:
    """ADR-0008 §5 row 3: refresh_headline exhausted retries.

    Leaves `index_status` alone (published headline stays current; draft
    publish stays blocked by the fingerprint mismatch) and inserts a deduped
    notification keyed on `headline_refresh_failed:{vid}`. Same `kind` as
    indexing failures so the consumer list does not need a new branch.
    """
    cv = await load_candidate(session, version_id)
    if cv.owner_user_id is None:
        return
    await notifications.notify_headline_refresh_failed(
        session,
        user_id=cv.owner_user_id,
        doc_id=cv.doc_id,
        version_id=version_id,
        error=reason,
    )
