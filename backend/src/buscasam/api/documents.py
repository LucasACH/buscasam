"""HTTP surface for document management endpoints."""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.api.deps import get_session
from buscasam.core import auth, blob_store
from buscasam.core.documents import (
    DocumentNotFound,
    InvalidCoauthorId,
    assert_manageable,
    attach_main_version,
    create_draft,
    list_own_documents,
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
            probe_encrypted(data[:2048])
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
