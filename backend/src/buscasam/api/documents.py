"""HTTP surface for document management endpoints."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import AsyncIterator, Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.blob_store import BlobTooLarge
from buscasam.core.documents import (
    UNSET,
    AttachmentCapExceeded,
    CoauthorAlreadyListed,
    CoauthorNotPending,
    CoauthorStatus,
    DocumentNotFound,
    InvalidCoauthorId,
    NotOwner,
    PublishConflict,
    add_attachment,
    assert_manageable,
    attach_main_version,
    create_draft,
    get_draft_state,
    invite_coauthor,
    list_own_documents,
    publish,
    remove_attachment,
    revoke_invitation,
    update_draft_metadata,
)
from buscasam.core.extract import PDFEncryptionError, probe_encrypted

router = APIRouter(prefix="/api")

# Mirror the DB constraints (documents_visibility_check, documents_tipo_check,
# area_path ltree) so invalid input is a 422 at the boundary, not a 500 from
# the UPDATE. Same closed sets / pattern as api/search.py.
Visibility = Literal["publico", "interno", "privado"]
DocumentType = Literal[
    "tesis",
    "paper",
    "trabajo_practico",
    "proyecto_investigacion",
    "monografia",
    "ponencia_poster",
    "apunte_resumen",
    "informe_catedra",
]
_AREA_PATH_PATTERN = r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"


class OwnDocDTO(BaseModel):
    id: int
    title: str
    publication_status: str
    visibility: str
    published_at: datetime | None


class CreateDraftRequest(BaseModel):
    title: str
    area_path: str = Field(pattern=_AREA_PATH_PATTERN)
    document_type: DocumentType
    visibility: Visibility
    external_authors: list[str] = []
    coauthor_user_ids: list[int] = []


class CreateDraftResponse(BaseModel):
    id: int


@router.post("/documents", status_code=201, response_model=CreateDraftResponse)
async def create_draft_endpoint(
    body: CreateDraftRequest,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> CreateDraftResponse:
    try:
        doc_id = await create_draft(
            session,
            user_ctx,
            title=body.title,
            area_path=body.area_path,
            document_type=body.document_type,
            visibility=body.visibility,
            external_authors=body.external_authors,
            coauthor_user_ids=body.coauthor_user_ids,
        )
    except InvalidCoauthorId as exc:
        raise HTTPException(status_code=422, detail=f"Unknown coauthor user_id(s): {sorted(exc.ids)}")
    return CreateDraftResponse(id=doc_id)


_ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
}
_MAX_MAIN_BYTES = 50 * 1024 * 1024


async def _stream_bytes(data: bytes):
    yield data


@router.post("/documents/{doc_id}/upload", status_code=202)
async def upload_main_file(
    doc_id: int,
    file: UploadFile,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Pre-check gates byte writes: reject unauthorized requests before streaming
    # to disk. attach_main_version re-checks as the authoritative gate.
    try:
        await assert_manageable(session, user_ctx, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404)

    data = await file.read(_MAX_MAIN_BYTES + 1)
    if len(data) > _MAX_MAIN_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")

    if data[:4] == b"%PDF":
        try:
            probe_encrypted(data)
        except PDFEncryptionError:
            raise HTTPException(
                status_code=415,
                detail="Este PDF está protegido por contraseña — quitá la protección y reintentá",
            )

    result = await blob_store.put_stream(_stream_bytes(data), max_bytes=_MAX_MAIN_BYTES)

    if result.sniffed_mime not in _ALLOWED_MIMES:
        await blob_store.discard_if_unreferenced(session, result.sha256)
        raise HTTPException(status_code=415, detail="Formato no permitido")

    try:
        await attach_main_version(
            session,
            user_ctx,
            doc_id,
            result,
            original_filename=file.filename or "upload",
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404)
    return {}


class AttachmentDTO(BaseModel):
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


class CoauthorRowDTO(BaseModel):
    user_id: int | None
    display_name: str
    email_local: str | None
    status: CoauthorStatus


class DraftStateDTO(BaseModel):
    title: str
    index_status: str
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    index_error: str | None
    publish_gate_reason: str | None
    is_owner: bool
    attachments: list[AttachmentDTO]
    coauthors: list[CoauthorRowDTO]


class InviteCoauthorRequest(BaseModel):
    user_id: int


class UpdateDraftRequest(BaseModel):
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    fecha: date | None = None
    visibility: Visibility | None = None
    area_path: str | None = Field(default=None, pattern=_AREA_PATH_PATTERN)
    document_type: DocumentType | None = None


@router.get("/documents/{doc_id}/draft", response_model=DraftStateDTO)
async def get_draft(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> DraftStateDTO:
    try:
        state = await get_draft_state(session, user_ctx, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404)
    return DraftStateDTO(
        title=state.title,
        index_status=state.index_status,
        staged_abstract=state.staged_abstract,
        staged_keywords=state.staged_keywords,
        staged_fecha=state.staged_fecha,
        index_error=state.index_error,
        publish_gate_reason=state.publish_gate_reason,
        is_owner=state.is_owner,
        attachments=[
            AttachmentDTO(
                id=a.id,
                original_filename=a.original_filename,
                size_bytes=a.size_bytes,
                mime=a.mime,
            )
            for a in state.attachments
        ],
        coauthors=[
            CoauthorRowDTO(
                user_id=c.user_id,
                display_name=c.display_name,
                email_local=c.email_local,
                status=c.status,
            )
            for c in state.coauthors
        ],
    )


@router.post("/documents/{doc_id}/coauthors", status_code=204)
async def post_coauthor(
    doc_id: int,
    body: InviteCoauthorRequest,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await invite_coauthor(session, user_ctx, doc_id, body.user_id)
    except NotOwner:
        raise HTTPException(status_code=403)
    except CoauthorAlreadyListed:
        raise HTTPException(status_code=409)
    except InvalidCoauthorId:
        raise HTTPException(status_code=422, detail="Unknown user_id")
    return Response(status_code=204)


@router.delete("/documents/{doc_id}/coauthors/{user_id}", status_code=204)
async def delete_coauthor(
    doc_id: int,
    user_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await revoke_invitation(session, user_ctx, doc_id, user_id)
    except NotOwner:
        raise HTTPException(status_code=403)
    except CoauthorNotPending:
        raise HTTPException(status_code=404)
    return Response(status_code=204)


@router.patch("/documents/{doc_id}", status_code=204)
async def patch_draft(
    doc_id: int,
    body: UpdateDraftRequest,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await update_draft_metadata(
            session,
            user_ctx,
            doc_id,
            title=body.title,
            abstract=body.abstract,
            keywords=body.keywords,
            # Distinguish an absent fecha from an explicit null: only null clears
            # staged_fecha; omitting it leaves the stored value untouched.
            fecha=body.fecha if "fecha" in body.model_fields_set else UNSET,
            visibility=body.visibility,
            area_path=body.area_path,
            document_type=body.document_type,
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404)
    return Response(status_code=204)


@router.post("/documents/{doc_id}/publish", status_code=204)
async def publish_document(
    doc_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await publish(session, user_ctx, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404)
    except PublishConflict:
        raise HTTPException(status_code=409)
    return Response(status_code=204)


# ADR-0006 §10: attachment extension allowlist (no content sniffing). The
# component's <input accept=...> mirrors this set.
_ALLOWED_ATTACHMENT_EXTS = {
    ".csv", ".json", ".txt", ".py", ".ipynb",
    ".png", ".jpg", ".jpeg", ".gif", ".zip",
}
_MAX_ATTACHMENT_BYTES = 20_000_000


async def _file_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    while True:
        chunk = await file.read(1 << 20)
        if not chunk:
            break
        yield chunk


@router.post(
    "/documents/{doc_id}/attachments", status_code=201, response_model=AttachmentDTO
)
async def post_attachment(
    doc_id: int,
    file: UploadFile,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> AttachmentDTO:
    # Reject non-authors before streaming bytes to disk (parity with /upload):
    # an authenticated non-manager should not be able to write blobs to a
    # document they cannot manage. add_attachment re-checks under a row lock.
    try:
        await assert_manageable(session, user_ctx, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404)

    filename = file.filename or "adjunto"
    if Path(filename).suffix.lower() not in _ALLOWED_ATTACHMENT_EXTS:
        raise HTTPException(status_code=415, detail="Tipo de archivo no permitido")

    try:
        result = await blob_store.put_stream(
            _file_chunks(file), max_bytes=_MAX_ATTACHMENT_BYTES
        )
    except BlobTooLarge:
        raise HTTPException(status_code=413, detail="El adjunto supera los 20 MB")

    # Both reject paths below leave the just-written blob for the dedup-safe
    # orphan sweep (ADR-0006 §12). We deliberately don't delete it inline the
    # way /upload's 415 path does: the blob is content-addressed and may already
    # be shared with another row, so an unconditional delete could orphan that.
    try:
        att_id = await add_attachment(
            session, user_ctx, doc_id, result, original_filename=filename
        )
    except DocumentNotFound:
        raise HTTPException(status_code=404)
    except AttachmentCapExceeded:
        raise HTTPException(
            status_code=409, detail={"reason": "attachment_cap_exceeded"}
        )
    return AttachmentDTO(
        id=att_id,
        original_filename=filename,
        size_bytes=result.bytes,
        mime=result.sniffed_mime,
    )


@router.delete("/documents/{doc_id}/attachments/{att_id}", status_code=204)
async def delete_attachment(
    doc_id: int,
    att_id: int,
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await remove_attachment(session, user_ctx, doc_id, att_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404)
    return Response(status_code=204)


@router.get("/me/documents", response_model=list[OwnDocDTO])
async def get_own_documents(
    user_ctx: auth.UserCtx = Depends(auth.require_authenticated),
    session: AsyncSession = Depends(get_session),
) -> list[OwnDocDTO]:
    docs = await list_own_documents(session, user_ctx)
    return [
        OwnDocDTO(
            id=d.id,
            title=d.title,
            publication_status=d.publication_status,
            visibility=d.visibility,
            published_at=d.published_at,
        )
        for d in docs
    ]
