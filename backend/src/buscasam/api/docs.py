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

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api._blob import download_response
from buscasam.api.deps import get_session
from buscasam.core import auth
from buscasam.core.documents import (
    DetailRow,
    get_detail,
    get_manageable_version_file,
    get_pending_invitation,
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


class InvitationBannerDTO(BaseModel):
    inviter_display_name: str


class _DetailFields(BaseModel):
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


class DetailDTO(_DetailFields):
    view: Literal["detail"] = "detail"


class DetailWithInvitationDTO(_DetailFields):
    view: Literal["detail_with_invitation"] = "detail_with_invitation"
    invitation: InvitationBannerDTO


class MinimalInviteDTO(BaseModel):
    view: Literal["minimal"] = "minimal"
    doc_id: int
    titulo: str
    inviter_display_name: str


# Discriminated on `view` so the generated TS client narrows the three reader
# shapes (module map §api/docs; ADR-0010 §6).
DocDetailResponse = Annotated[
    DetailDTO | MinimalInviteDTO | DetailWithInvitationDTO,
    Field(discriminator="view"),
]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not_found")


def _detail_fields(detail: DetailRow) -> dict:
    return dict(
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


@router.get("/{doc_id}", response_model=DocDetailResponse)
async def get_doc_detail(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.current_user),
    session: AsyncSession = Depends(get_session),
) -> DetailDTO | MinimalInviteDTO | DetailWithInvitationDTO:
    # Second-try composition (module map §api/docs / ADR-0010 §6): detail first
    # (the hot path for accepted readers), then the recipient-scoped disclosure.
    # The second SELECT is skipped unless it could change the response: invitados
    # cannot be invitees, and a present detail on a privado doc means owner/
    # accepted (readable_where excludes pending), so no banner is ever owed there.
    detail = await get_detail(session, doc_id, user_ctx)
    needs_disclosure = user_ctx.user_id is not None and (
        detail is None or detail.visibility in ("interno", "publico")
    )
    invite = (
        await get_pending_invitation(session, doc_id, user_ctx)
        if needs_disclosure
        else None
    )
    if detail is not None:
        fields = _detail_fields(detail)
        if invite is not None:
            return DetailWithInvitationDTO(
                **fields,
                invitation=InvitationBannerDTO(
                    inviter_display_name=invite.inviter_display_name
                ),
            )
        return DetailDTO(**fields)
    if invite is not None:
        return MinimalInviteDTO(
            doc_id=invite.doc_id,
            titulo=invite.titulo,
            inviter_display_name=invite.inviter_display_name,
        )
    raise _not_found()


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
    return download_response(
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
    return download_response(
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
    return download_response(
        sha_hex=file.sha_hex, original_filename=file.original_filename, mime=file.mime
    )
