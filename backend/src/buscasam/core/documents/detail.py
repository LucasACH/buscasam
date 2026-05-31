"""Reader-facing detail, pending-invitation disclosure, and access-gated file
lookups for downloads (module map §document-detail)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core.document_access import (
    manageable_where,
    pending_invitation_disclosure_where,
    readable_where,
)

from buscasam.core.documents._shared import (
    DetailVersion,
    _published_version_history,
    _to_detail_version,
)

if TYPE_CHECKING:
    from buscasam.core.auth import UserCtx


@dataclass(frozen=True)
class AuthorDisplay:
    display_name: str
    user_id: int | None


@dataclass(frozen=True)
class MainFile:
    original_filename: str
    size_bytes: int
    mime: str


@dataclass(frozen=True)
class Attachment:
    id: int
    original_filename: str
    size_bytes: int
    mime: str | None


@dataclass(frozen=True)
class DetailRow:
    doc_id: int
    titulo: str
    autores: list[AuthorDisplay]
    area_path: str
    tipo: str
    fecha: date | None
    visibility: str
    abstract: str
    palabras_clave: list[str]
    archivo_principal: MainFile
    adjuntos: list[Attachment]
    versions: list[DetailVersion] | None
    manageable: bool


async def get_detail(
    session: AsyncSession,
    doc_id: int,
    user_ctx: UserCtx,
) -> DetailRow | None:
    """Reader DTO for `/docs/{id}` (module map §core/documents).

    Returns `None` when the document fails `readable_where(user_ctx)` — the
    router maps `None → 404` uniformly. `archivo_principal` and `adjuntos`
    reflect the published current version's rows (`document_versions.is_current`)
    and `document_attachments` respectively. `versions` (ascending by 1-based
    `n`) and `manageable=True` are populated only when `manageable_where(user_ctx)`
    admits the requester (owner / accepted coautor); for any other reader
    `versions is None` and `manageable=False` (issue #44).
    """
    where, params = readable_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT d.id, d.titulo, d.area_path::text AS area_path, d.tipo, "
                "       d.fecha, d.visibility, d.abstract, "
                "       COALESCE(d.keywords, ARRAY[]::text[]) AS keywords, "
                "       dv.original_filename AS main_filename, "
                "       dv.bytes AS main_bytes, "
                "       dv.mime AS main_mime "
                "FROM documents d "
                "JOIN document_versions dv "
                "  ON dv.doc_id = d.id AND dv.is_current "
                f"WHERE d.id = :doc_id AND ({where})"
            ),
            {"doc_id": doc_id, **params},
        )
    ).mappings().first()
    if row is None:
        return None

    author_rows = (
        await session.execute(
            text(
                "SELECT display_name, user_id "
                "FROM document_authors WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).mappings().all()
    attachment_rows = (
        await session.execute(
            text(
                "SELECT id, original_filename, bytes, mime "
                "FROM document_attachments WHERE doc_id = :d ORDER BY id"
            ),
            {"d": doc_id},
        )
    ).mappings().all()

    mgmt_where, mgmt_params = manageable_where("d", user_ctx)
    manageable = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({mgmt_where})"),
            {"doc_id": doc_id, **mgmt_params},
        )
    ).scalar_one_or_none() is not None

    versions: list[DetailVersion] | None = None
    if manageable:
        # ADR-0011 §4: the audit list shows only versions that were at some
        # point the public current. _published_version_history owns the gate +
        # ordering shared with get_manageable_version_file, so the 1-based n stays
        # aligned with the version-download route.
        versions = [
            _to_detail_version(v)
            for v in await _published_version_history(session, doc_id)
        ]

    return DetailRow(
        doc_id=row["id"],
        titulo=row["titulo"],
        autores=[
            AuthorDisplay(display_name=a["display_name"], user_id=a["user_id"])
            for a in author_rows
        ],
        area_path=row["area_path"],
        tipo=row["tipo"],
        fecha=row["fecha"],
        visibility=row["visibility"],
        abstract=row["abstract"] or "",
        palabras_clave=list(row["keywords"]),
        archivo_principal=MainFile(
            original_filename=row["main_filename"],
            size_bytes=row["main_bytes"],
            mime=row["main_mime"],
        ),
        adjuntos=[
            Attachment(
                id=a["id"],
                original_filename=a["original_filename"],
                size_bytes=a["bytes"],
                mime=a["mime"],
            )
            for a in attachment_rows
        ],
        versions=versions,
        manageable=manageable,
    )


@dataclass(frozen=True)
class InvitationDisclosure:
    doc_id: int
    titulo: str
    inviter_display_name: str


async def get_pending_invitation(
    session: AsyncSession, doc_id: int, user_ctx: UserCtx
) -> InvitationDisclosure | None:
    """Minimal-block payload for a pending invitee on `doc_id`, else `None`.

    Composes `pending_invitation_disclosure_where` (ADR-0010 §6) — the sole
    reader of `document_authors.status='pending'` for disclosure. Returns `None`
    for guests (no `user_id`) without raising. `inviter_display_name` comes from
    the document's `owner` author row, consistent with `get_detail`'s autores.
    """
    if user_ctx.user_id is None:
        return None
    where, params = pending_invitation_disclosure_where("d", user_ctx)
    row = (
        await session.execute(
            text(
                "SELECT d.titulo, "
                "       (SELECT a.display_name FROM document_authors a "
                "         WHERE a.doc_id = d.id AND a.status = 'owner' LIMIT 1) "
                "         AS inviter "
                f"FROM documents d WHERE d.id = :doc_id AND ({where})"
            ),
            {"doc_id": doc_id, **params},
        )
    ).mappings().first()
    if row is None:
        return None
    return InvitationDisclosure(
        doc_id=doc_id,
        titulo=row["titulo"],
        inviter_display_name=row["inviter"],
    )


@dataclass(frozen=True)
class DownloadableFile:
    sha_hex: str
    original_filename: str
    mime: str | None  # NULL only possible for attachments (migration 0010)


async def get_readable_main_file(
    session: AsyncSession,
    doc_id: int,
    user_ctx: UserCtx,
) -> DownloadableFile | None:
    """Current published main-file lookup gated by `readable_where`.

    Returns `None` for missing doc, denied access, or no `is_current` version.
    Router maps `None → 404`.
    """
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
        return None
    return DownloadableFile(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )


async def get_readable_attachment(
    session: AsyncSession,
    doc_id: int,
    att_id: int,
    user_ctx: UserCtx,
) -> DownloadableFile | None:
    """Attachment lookup gated by `readable_where`. `mime` may be NULL."""
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
        return None
    return DownloadableFile(
        sha_hex=row.sha, original_filename=row.original_filename, mime=row.mime
    )


async def get_manageable_version_file(
    session: AsyncSession,
    doc_id: int,
    n: int,
    user_ctx: UserCtx,
) -> DownloadableFile | None:
    """Historical-version lookup gated by `manageable_where` (story 26).

    `n` is the 1-based row_number ordering shared with `get_detail`. Any
    out-of-range value returns `None`. The ordering is owned by
    `_published_version_history`, so it matches `get_detail`'s versions list.
    """
    where, params = manageable_where("d", user_ctx)
    manageable = (
        await session.execute(
            text(f"SELECT 1 FROM documents d WHERE d.id = :doc_id AND ({where})"),
            {"doc_id": doc_id, **params},
        )
    ).scalar_one_or_none() is not None
    if not manageable:
        return None
    # ADR-0011 §4: only versions that were at some point the public current are
    # downloadable here. _published_version_history applies the gate + the
    # row_number() ordering shared with get_detail, so `n` resolves to the same
    # file the manager clicked. Failed, discarded, and in-flight ready candidates
    # are absent from the projection, so an out-of-range n returns None (404).
    match = next(
        (v for v in await _published_version_history(session, doc_id) if v.n == n),
        None,
    )
    if match is None:
        return None
    return DownloadableFile(
        sha_hex=match.sha_hex,
        original_filename=match.original_filename,
        mime=match.mime,
    )
