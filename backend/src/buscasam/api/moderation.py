"""HTTP edge for the moderation flow (module map §api/moderation).

The single chokepoint where moderation access is gated: `require_authenticated`
for filing a report, `require_docente` for report-scoped inspection. Filing
delegates to `core/moderation`; the inspect reads compose
`moderation_inspection_where` (detail metadata + current main-file blob handoff
only — no attachments, related, or version history). Maps every domain miss to a
uniform 404 so hidden/private/deleted existence is never disclosed; role
failures surface as 403 via `require_docente`. Opens no transactions and writes
no tables directly.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.document_access import moderation_inspection_where
from buscasam.core.moderation import DocumentNotReadable, Reason, file_report
from buscasam.settings import settings

router = APIRouter(prefix="/api/moderation")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


def _download_response(*, sha_hex: str, original_filename: str, mime: str) -> Response:
    # Same dual-mode projection as api/docs: nginx X-Accel-Redirect in prod,
    # inline FileResponse for local dev (settings.serve_blobs_inline).
    disposition = f"attachment; filename*=UTF-8''{quote(original_filename, safe='')}"
    if settings.serve_blobs_inline:
        return FileResponse(
            blob_store.local_path(sha_hex),
            media_type=mime,
            headers={"Content-Disposition": disposition},
        )
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": blob_store.internal_path(sha_hex),
            "Content-Type": mime,
            "Content-Disposition": disposition,
        },
    )


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
    return _download_response(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )
