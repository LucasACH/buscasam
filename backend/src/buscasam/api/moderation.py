"""HTTP edge for the moderation flow (module map §api/moderation).

The single chokepoint where moderation access is gated: `require_authenticated`
for filing a report, `require_docente` for the triage queue read and
report-scoped inspection. Filing and the queue delegate to `core/moderation`;
the inspect reads compose `moderation_inspection_where` (detail metadata +
current main-file blob handoff only — no attachments, related, or version
history). Maps every domain miss to a uniform 404 so hidden/private/deleted
existence is never disclosed; role failures surface as 403 via
`require_docente`. Opens no transactions and writes no tables directly.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api._blob import download_response
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.document_access import moderation_inspection_where
from buscasam.core.moderation import (
    DocumentNotReadable,
    Reason,
    dismiss,
    file_report,
    hide,
    list_open_reports,
    unhide,
)

router = APIRouter(prefix="/api/moderation")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


class ReportBody(BaseModel):
    doc_id: int
    reason: Reason


class AuthorDisplayDTO(BaseModel):
    display_name: str
    user_id: int | None


class InspectMetadataDTO(BaseModel):
    titulo: str
    abstract: str
    palabras_clave: list[str]
    autores: list[AuthorDisplayDTO]
    tipo: str
    area_path: str


@router.post("/reports", status_code=204)
async def create_report(
    body: ReportBody,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await file_report(session, user_ctx, body.doc_id, body.reason)
    except DocumentNotReadable:
        raise _not_found()
    return Response(status_code=204)


class QueueEntryDTO(BaseModel):
    doc_id: int
    title: str
    reasons: list[str]
    first_reported_at: datetime
    last_reported_at: datetime
    report_count: int


class QueueResponse(BaseModel):
    items: list[QueueEntryDTO]


@router.get("/queue", response_model=QueueResponse)
async def queue(
    _docente: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> QueueResponse:
    entries = await list_open_reports(session)
    return QueueResponse(items=[QueueEntryDTO(**vars(e)) for e in entries])


@router.get("/reports/{report_id}/document", response_model=InspectMetadataDTO)
async def inspect_document(
    report_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> InspectMetadataDTO:
    # Report-scoped read (module map §api/moderation): moderation_inspection_where
    # selects the reported doc regardless of visibility/hidden, excluding author-
    # soft-deleted. Every miss is a uniform 404.
    where, params = moderation_inspection_where("d", report_id)
    row = (
        await session.execute(
            text(
                "SELECT d.id, d.titulo, d.tipo, d.area_path::text AS area_path, "
                "       d.abstract, COALESCE(d.keywords, ARRAY[]::text[]) AS keywords "
                f"FROM documents d WHERE {where}"
            ),
            params,
        )
    ).mappings().first()
    if row is None:
        raise _not_found()
    author_rows = (
        await session.execute(
            text(
                "SELECT display_name, user_id FROM document_authors "
                "WHERE doc_id = :d ORDER BY id"
            ),
            {"d": row["id"]},
        )
    ).mappings().all()
    return InspectMetadataDTO(
        titulo=row["titulo"],
        abstract=row["abstract"] or "",
        palabras_clave=list(row["keywords"]),
        autores=[
            AuthorDisplayDTO(display_name=a["display_name"], user_id=a["user_id"])
            for a in author_rows
        ],
        tipo=row["tipo"],
        area_path=row["area_path"],
    )


class HideBody(BaseModel):
    reason: Reason


class ActionBody(BaseModel):
    reason: Reason | None = None


@router.post("/reports/{report_id}/hide", status_code=204)
async def hide_report(
    report_id: int,
    body: HideBody,
    docente: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if await hide(session, docente, report_id, body.reason) is None:
        raise _not_found()
    return Response(status_code=204)


@router.post("/reports/{report_id}/unhide", status_code=204)
async def unhide_report(
    report_id: int,
    body: ActionBody,
    docente: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if await unhide(session, docente, report_id, body.reason) is None:
        raise _not_found()
    return Response(status_code=204)


@router.post("/reports/{report_id}/dismiss", status_code=204)
async def dismiss_report(
    report_id: int,
    body: ActionBody,
    docente: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if await dismiss(session, docente, report_id, body.reason) is None:
        raise _not_found()
    return Response(status_code=204)


@router.get("/reports/{report_id}/download")
async def inspect_download(
    report_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_docente),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Current main-file blob handoff for the reported doc (module map: no
    # attachments/related/version history). No current version → uniform 404.
    where, params = moderation_inspection_where("d", report_id)
    row = (
        await session.execute(
            text(
                "SELECT encode(dv.sha256, 'hex') AS sha, "
                "       dv.original_filename, dv.mime "
                "FROM documents d "
                "JOIN document_versions dv ON dv.doc_id = d.id AND dv.is_current "
                f"WHERE {where}"
            ),
            params,
        )
    ).first()
    if row is None:
        raise _not_found()
    return download_response(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )
