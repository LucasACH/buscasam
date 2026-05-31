"""Pydantic request/response DTOs for the document-management endpoints
(ADR-0003 §6: DTOs separate from ORM). Shapes the HTTP contract; orchestration
lives in api/documents.py, domain logic in core/documents."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from buscasam.core.documents import CoauthorStatus

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
    moderation_hidden: bool


# Exposes purge_at (the server-computed soft_deleted_at + 180 días) but not the
# raw deletion time: the frontend derives "Se elimina en N días" from purge_at
# alone, so the 180-día constant stays single-sourced in the SQL projection.
class DeletedDocDTO(BaseModel):
    id: int
    title: str
    publication_status: str
    purge_at: datetime


class ExternalAuthorInput(BaseModel):
    name: str
    surname: str
    email: str


class CreateDraftRequest(BaseModel):
    title: str
    area_path: str = Field(pattern=_AREA_PATH_PATTERN)
    document_type: DocumentType
    visibility: Visibility
    external_authors: list[ExternalAuthorInput] = []
    coauthor_user_ids: list[int] = []


class CreateDraftResponse(BaseModel):
    id: int


class AttachmentDTO(BaseModel):
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


class CoauthorRowDTO(BaseModel):
    user_id: int | None
    display_name: str
    email_local: str | None
    email: str | None
    status: CoauthorStatus


class DraftVersionDTO(BaseModel):
    n: int
    original_filename: str
    mime: str
    size_bytes: int
    indexed_at: str | None  # ISO datetime; None when never indexed.
    is_current: bool


class CandidateStateDTO(BaseModel):
    status: Literal["processing", "ready", "failed"]
    index_stage: str | None  # pipeline checkpoint while status='processing'
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    can_publish: bool
    can_discard: bool
    indexed_at: str | None  # ISO datetime; None until indexed.
    error: str | None


class DraftStateDTO(BaseModel):
    title: str
    index_status: str
    index_stage: str | None
    staged_abstract: str | None
    staged_keywords: list[str]
    staged_fecha: date | None
    generated_abstract: str | None
    generated_keywords: list[str]
    generated_fecha: date | None
    index_error: str | None
    publish_gate_reason: str | None
    is_owner: bool
    visibility: Visibility
    area_path: str
    attachments: list[AttachmentDTO]
    coauthors: list[CoauthorRowDTO]
    versions: list[DraftVersionDTO]
    candidate: CandidateStateDTO | None


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
