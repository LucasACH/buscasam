"""Reader-facing document endpoints (issues #43, #44, #45; module map §api/docs).

Five endpoints share one UserCtx dep (cookie → invitado on absent), and one
uniform 404 envelope across every denial path. Download handlers delegate
access-gated row lookup to `core/documents` (`get_readable_main_file`,
`get_readable_attachment`, `get_manageable_version_file`) and keep only
transport: headers, `None → 404` mapping, `X-Accel-Redirect` vs `FileResponse`
projection, `n` parsing, and the attachment `mime` fallback. Slice 3 wires
`core/related.fetch_related` through `settings.min_semantic_similarity`,
returning `RelatedDTO[]` or the uniform 404 envelope.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.documents import (
    get_detail,
    get_manageable_version_file,
    get_readable_attachment,
    get_readable_main_file,
)
from buscasam.core.related import fetch_related
from buscasam.settings import settings

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


class DetailVersionDTO(BaseModel):
    n: int
    original_filename: str
    mime: str
    size_bytes: int
    indexed_at: str | None  # ISO datetime; None when never indexed.
    is_current: bool


class RelatedDTO(BaseModel):
    doc_id: int
    titulo: str
    autores: list[AuthorDisplayDTO]
    area_path: str
    tipo: str
    fecha: str | None  # ISO date; None when documents.fecha is NULL.


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
    versions: list[DetailVersionDTO] | None = None
    manageable: bool

    @model_serializer(mode="wrap")
    def _omit_versions_when_absent(self, handler):
        # Non-managers get `versions` *omitted* (not null) — the no-leak contract
        # (module map §api/docs). Other null fields (fecha, user_id) are kept.
        data = handler(self)
        if self.versions is None:
            data.pop("versions", None)
        return data


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


def _content_disposition(original_filename: str) -> str:
    encoded = quote(original_filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


def _download_response(*, sha_hex: str, original_filename: str, mime: str) -> Response:
    # Prod ships an empty body and lets nginx serve the file via
    # X-Accel-Redirect. Local-dev runs uvicorn directly without nginx, so
    # `serve_blobs_inline` flips to streaming the blob from disk instead.
    if settings.serve_blobs_inline:
        return FileResponse(
            blob_store.local_path(sha_hex),
            media_type=mime,
            headers={"Content-Disposition": _content_disposition(original_filename)},
        )
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
        versions=(
            [
                DetailVersionDTO(
                    n=v.n,
                    original_filename=v.original_filename,
                    mime=v.mime,
                    size_bytes=v.size_bytes,
                    indexed_at=(
                        v.indexed_at.isoformat() if v.indexed_at is not None else None
                    ),
                    is_current=v.is_current,
                )
                for v in detail.versions
            ]
            if detail.versions is not None
            else None
        ),
        manageable=detail.manageable,
    )


@router.get("/{doc_id}/related", response_model=list[RelatedDTO])
async def get_doc_related(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RelatedDTO]:
    rows = await fetch_related(
        session,
        doc_id,
        user_ctx,
        min_semantic_similarity=settings.min_semantic_similarity,
    )
    if rows is None:
        raise _not_found()
    return [
        RelatedDTO(
            doc_id=r.doc_id,
            titulo=r.titulo,
            autores=[
                AuthorDisplayDTO(display_name=a.display_name, user_id=a.user_id)
                for a in r.autores
            ],
            area_path=r.area_path,
            tipo=r.tipo,
            fecha=r.fecha.isoformat() if r.fecha is not None else None,
        )
        for r in rows
    ]


@router.get("/{doc_id}/download")
async def download_main_file(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    file = await get_readable_main_file(session, doc_id, user_ctx)
    if file is None:
        raise _not_found()
    return _download_response(
        sha_hex=file.sha_hex, original_filename=file.original_filename, mime=file.mime
    )


@router.get("/{doc_id}/attachments/{att_id}")
async def download_attachment(
    doc_id: int,
    att_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    file = await get_readable_attachment(session, doc_id, att_id, user_ctx)
    if file is None:
        raise _not_found()
    return _download_response(
        sha_hex=file.sha_hex,
        original_filename=file.original_filename,
        # Attachments can have NULL mime per migration 0010; fall back to a
        # generic stream type so Content-Type is always present.
        mime=file.mime or "application/octet-stream",
    )


@router.api_route("/{doc_id}/versions/{n}/download", methods=["GET", "HEAD"])
async def download_version(
    doc_id: int,
    n: str,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # `n` is the 1-based row_number ordering shared with get_detail; any
    # non-integer / out-of-range value is the same uniform 404 — never a
    # 400/422 (module map §api/docs).
    try:
        version_n = int(n)
    except ValueError:
        raise _not_found() from None
    if version_n < 1:
        raise _not_found()

    file = await get_manageable_version_file(session, doc_id, version_n, user_ctx)
    if file is None:
        raise _not_found()
    return _download_response(
        sha_hex=file.sha_hex, original_filename=file.original_filename, mime=file.mime
    )
