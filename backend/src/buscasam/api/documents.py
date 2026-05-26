"""HTTP surface for document management endpoints."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.documents import (
    DocumentNotFound,
    InvalidCoauthorId,
    assert_manageable,
    attach_main_version,
    create_draft,
    get_draft_state,
    list_own_documents,
    update_draft_metadata,
)
from buscasam.core.extract import PDFEncryptionError, probe_encrypted

router = APIRouter(prefix="/api")


class OwnDocDTO(BaseModel):
    id: int
    title: str
    publication_status: str
    visibility: str


class CreateDraftRequest(BaseModel):
    title: str
    area_path: str
    document_type: str
    visibility: str
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
        await blob_store.delete(result.sha256)
        raise HTTPException(status_code=415, detail="Formato no permitido")

    await attach_main_version(
        session,
        user_ctx,
        doc_id,
        result,
        original_filename=file.filename or "upload",
    )
    return {}


class DraftStateDTO(BaseModel):
    title: str
    index_status: str
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    index_error: str | None
    publish_gate_reason: str | None


class UpdateDraftRequest(BaseModel):
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    fecha: date | None = None
    visibility: str | None = None
    area_path: str | None = None
    document_type: str | None = None


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
    )


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
            fecha=body.fecha,
            visibility=body.visibility,
            area_path=body.area_path,
            document_type=body.document_type,
        )
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
        )
        for d in docs
    ]
