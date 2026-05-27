"""Reader-facing document endpoints (issue #43, module map §api/docs).

Three endpoints share one UserCtx dep (cookie → invitado on absent), and one
uniform 404 envelope across every denial path. Slice 1 is reader-only: no
manager affordances, no related rail, no historical-version download — those
land in later PRD slices.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.document_access import readable_where
from buscasam.core.documents import get_detail

router = APIRouter(prefix="/api/docs")


class AuthorDisplayDTO(BaseModel):
    display_name: str
    user_id: int | None


class MainFileDTO(BaseModel):
    original_filename: str
    size_bytes: int
    mime: str


class AttachmentDTO(BaseModel):
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


class DetailDTO(BaseModel):
    doc_id: int
    titulo: str
    autores: list[AuthorDisplayDTO]
    area_path: str
    tipo: str
    fecha: str | None  # ISO date; None when documents.fecha is NULL.
    visibility: str
    abstract: str
    palabras_clave: list[str]
    archivo_principal: MainFileDTO
    adjuntos: list[AttachmentDTO]
    manageable: bool


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


def _content_disposition(original_filename: str) -> str:
    encoded = quote(original_filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


def _download_response(*, sha_hex: str, original_filename: str, mime: str) -> Response:
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": blob_store.internal_path(sha_hex),
            "Content-Type": mime,
            "Content-Disposition": _content_disposition(original_filename),
        },
    )


@router.get("/{doc_id}", response_model=DetailDTO)
async def get_doc_detail(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> DetailDTO:
    detail = await get_detail(session, doc_id, user_ctx)
    if detail is None:
        raise _not_found()
    return DetailDTO(
        doc_id=detail.doc_id,
        titulo=detail.titulo,
        autores=[
            AuthorDisplayDTO(display_name=a.display_name, user_id=a.user_id)
            for a in detail.autores
        ],
        area_path=detail.area_path,
        tipo=detail.tipo,
        fecha=detail.fecha.isoformat() if detail.fecha is not None else None,
        visibility=detail.visibility,
        abstract=detail.abstract,
        palabras_clave=detail.palabras_clave,
        archivo_principal=MainFileDTO(
            original_filename=detail.archivo_principal.original_filename,
            size_bytes=detail.archivo_principal.size_bytes,
            mime=detail.archivo_principal.mime,
        ),
        adjuntos=[
            AttachmentDTO(
                id=a.id,
                original_filename=a.original_filename,
                size_bytes=a.size_bytes,
                mime=a.mime,
            )
            for a in detail.adjuntos
        ],
        manageable=detail.manageable,
    )


@router.get("/{doc_id}/download")
async def download_main_file(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    where, params = readable_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT encode(dv.sha256, 'hex') AS sha, "
                "       dv.original_filename, dv.mime "
                "FROM documents d "
                "JOIN document_versions dv "
                "  ON dv.doc_id = d.id AND dv.is_current "
                f"WHERE d.id = :doc_id AND ({where})"
            ),
            {"doc_id": doc_id, **params},
        )
    ).first()
    if row is None:
        raise _not_found()
    return _download_response(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )


@router.get("/{doc_id}/attachments/{att_id}")
async def download_attachment(
    doc_id: int,
    att_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    where, params = readable_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT encode(a.sha256, 'hex') AS sha, "
                "       a.original_filename, a.mime "
                "FROM documents d "
                "JOIN document_attachments a "
                "  ON a.doc_id = d.id "
                f"WHERE d.id = :doc_id AND a.id = :att_id AND ({where})"
            ),
            {"doc_id": doc_id, "att_id": att_id, **params},
        )
    ).first()
    if row is None:
        raise _not_found()
    return _download_response(
        sha_hex=row.sha,
        original_filename=row.original_filename,
        # Attachments can have NULL mime per migration 0010; fall back to a
        # generic stream type so Content-Type is always present.
        mime=row.mime or "application/octet-stream",
    )
