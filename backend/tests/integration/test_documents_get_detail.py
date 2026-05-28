"""Integration tests for core/documents.get_detail (reader branch, issue #43)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import documents
from buscasam.core.auth import GUEST, UserCtx
from tests.factories import make_document, make_document_author, make_user


def _student(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed_current_version(
    session: AsyncSession,
    doc_id: int,
    *,
    original_filename: str = "tesis.pdf",
    bytes_: int = 2048,
    mime: str = "application/pdf",
    sha_hex: str = "aa" * 32,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_versions "
                "(doc_id, version_no, sha256, original_filename, bytes, mime, "
                " index_status, is_current) "
                "VALUES (:d, 1, decode(:sha, 'hex'), :name, :b, :m, 'indexed', true) "
                "RETURNING id"
            ),
            {"d": doc_id, "sha": sha_hex, "name": original_filename, "b": bytes_, "m": mime},
        )
    ).scalar_one()


async def _seed_attachment(
    session: AsyncSession,
    doc_id: int,
    *,
    original_filename: str = "datos.csv",
    bytes_: int = 512,
    mime: str | None = "text/csv",
    sha_hex: str = "bb" * 32,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime) "
                "VALUES (:d, decode(:sha, 'hex'), :name, :b, :m) RETURNING id"
            ),
            {"d": doc_id, "sha": sha_hex, "name": original_filename, "b": bytes_, "m": mime},
        )
    ).scalar_one()


async def test_get_detail_returns_publico_reader_dto_for_invitado(session):
    doc_id = await make_document(
        session,
        visibility="publico",
        titulo="Búsqueda híbrida en repositorios académicos",
        abstract="Resumen del trabajo.",
        fecha=date(2024, 3, 15),
        area_path="escuela_ciencia.carrera_informatica",
        tipo="tesis",
    )
    owner_id = await make_user(session, name="Ada Lovelace")
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Ada Lovelace"
    )
    await make_document_author(
        session, doc_id, user_id=None, status="external", display_name="Grace Hopper"
    )
    await session.execute(
        text("UPDATE documents SET keywords = ARRAY['busqueda', 'hibrida'] WHERE id = :d"),
        {"d": doc_id},
    )
    await _seed_current_version(session, doc_id)
    await _seed_attachment(session, doc_id)
    await session.commit()

    detail = await documents.get_detail(session, doc_id, GUEST)

    assert detail is not None
    assert detail.doc_id == doc_id
    assert detail.titulo == "Búsqueda híbrida en repositorios académicos"
    assert detail.abstract == "Resumen del trabajo."
    assert detail.fecha == date(2024, 3, 15)
    assert detail.area_path == "escuela_ciencia.carrera_informatica"
    assert detail.tipo == "tesis"
    assert detail.visibility == "publico"
    assert detail.palabras_clave == ["busqueda", "hibrida"]
    assert detail.manageable is False
    # Author order = document_authors row order; external rows carry no user_id.
    assert [a.display_name for a in detail.autores] == ["Ada Lovelace", "Grace Hopper"]
    assert detail.autores[0].user_id == owner_id
    assert detail.autores[1].user_id is None
    # archivo_principal reflects the published current version row.
    assert detail.archivo_principal.original_filename == "tesis.pdf"
    assert detail.archivo_principal.size_bytes == 2048
    assert detail.archivo_principal.mime == "application/pdf"
    # adjuntos reflect document_attachments rows.
    assert len(detail.adjuntos) == 1
    assert detail.adjuntos[0].original_filename == "datos.csv"
    assert detail.adjuntos[0].size_bytes == 512
    assert detail.adjuntos[0].mime == "text/csv"


async def test_get_detail_returns_none_when_readable_where_misses(session):
    """Reader-side denials all collapse to None; the router maps to a uniform 404."""
    # Invitado on non-publico states + non-existent id.
    interno_id = await make_document(session, visibility="interno")
    await _seed_current_version(session, interno_id)
    privado_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, privado_id)
    draft_id = await make_document(session, publication_status="draft")
    await _seed_current_version(session, draft_id)
    deleted_id = await make_document(session, soft_deleted=True)
    await _seed_current_version(session, deleted_id)
    hidden_id = await make_document(session, moderation_hidden=True)
    await _seed_current_version(session, hidden_id)
    await session.commit()

    for blocked_id in (interno_id, privado_id, draft_id, deleted_id, hidden_id):
        assert await documents.get_detail(session, blocked_id, GUEST) is None
    assert await documents.get_detail(session, 999_999, GUEST) is None


async def test_get_detail_returns_none_for_pending_coauthor_on_privado(session):
    """Pending coautor on a privado doc gets None (story 10)."""
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session, name="Owner")
    pending_id = await make_user(session, name="Pending Coautor")
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await make_document_author(
        session, doc_id, user_id=pending_id, status="pending", display_name="Pending Coautor"
    )
    await session.commit()

    assert await documents.get_detail(session, doc_id, _student(pending_id)) is None
    # Sanity: owner gets the row.
    assert await documents.get_detail(session, doc_id, _student(owner_id)) is not None


async def test_get_detail_interno_visible_to_estudiante_blocked_for_privado_non_author(session):
    estudiante_id = await make_user(session)
    interno_id = await make_document(session, visibility="interno")
    await _seed_current_version(session, interno_id)
    privado_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, privado_id)
    # Privado document owned by *somebody else*; the requester is not in
    # document_authors at all.
    other_owner = await make_user(session, name="Other")
    await make_document_author(session, privado_id, user_id=other_owner, status="owner")
    await session.commit()

    assert (
        await documents.get_detail(session, interno_id, _student(estudiante_id))
    ) is not None
    assert (
        await documents.get_detail(session, privado_id, _student(estudiante_id))
    ) is None


async def test_get_detail_archivo_principal_uses_current_version_not_candidate(session):
    """Mid-replace state: a newer non-current candidate must not leak into
    archivo_principal — only the published current version is shown (story 13)."""
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(
        session,
        doc_id,
        original_filename="published-v1.pdf",
        bytes_=1000,
        sha_hex="cc" * 32,
    )
    # A second, non-current row simulates an in-flight replacement.
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current) "
            "VALUES (:d, 2, decode(:sha, 'hex'), :name, :b, :m, 'indexed', false)"
        ),
        {
            "d": doc_id,
            "sha": "dd" * 32,
            "name": "candidate-v2.pdf",
            "b": 9999,
            "m": "application/pdf",
        },
    )
    await session.commit()

    detail = await documents.get_detail(session, doc_id, GUEST)

    assert detail is not None
    assert detail.archivo_principal.original_filename == "published-v1.pdf"
    assert detail.archivo_principal.size_bytes == 1000


async def test_get_detail_manageable_branch_populates_versions_for_owner(session):
    """Manager branch (issue #44): owner gets versions ascending by 1-based n,
    with is_current and a tz-aware indexed_at; manageable is True."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session, name="Owner")
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, indexed_at, first_published_at) VALUES "
            "(:d, 1, decode('11', 'hex'), 'v1.pdf', 100, 'application/pdf', "
            " 'indexed', false, CAST('2024-01-01T10:00:00Z' AS timestamptz), now()), "
            "(:d, 2, decode('22', 'hex'), 'v2.pdf', 200, 'application/pdf', "
            " 'indexed', true, CAST('2024-02-01T10:00:00Z' AS timestamptz), now())"
        ),
        {"d": doc_id},
    )
    await session.commit()

    detail = await documents.get_detail(session, doc_id, _student(owner_id))

    assert detail is not None
    assert detail.manageable is True
    assert detail.versions is not None
    assert [(v.n, v.original_filename, v.is_current) for v in detail.versions] == [
        (1, "v1.pdf", False),
        (2, "v2.pdf", True),
    ]
    assert detail.versions[0].size_bytes == 100
    assert detail.versions[0].indexed_at == datetime(
        2024, 1, 1, 10, 0, tzinfo=timezone.utc
    )


async def test_get_detail_versions_excludes_never_published_candidate(session):
    """ADR-0011 §4: the manager Versiones list filters on first_published_at
    IS NOT NULL. A never-public candidate (failed, discarded, or in-flight
    ready) does not appear, and the published rows keep their 1-based n."""
    doc_id = await make_document(session, visibility="privado")
    owner_id = await make_user(session, name="Owner")
    await make_document_author(session, doc_id, user_id=owner_id, status="owner")
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) VALUES "
            "(:d, 1, decode('11', 'hex'), 'published.pdf', 100, 'application/pdf', "
            " 'indexed', true, now()), "
            "(:d, 2, decode('22', 'hex'), 'candidate.pdf', 200, 'application/pdf', "
            " 'indexed', false, NULL)"
        ),
        {"d": doc_id},
    )
    await session.commit()

    detail = await documents.get_detail(session, doc_id, _student(owner_id))

    assert detail is not None and detail.versions is not None
    assert [(v.n, v.original_filename) for v in detail.versions] == [
        (1, "published.pdf"),
    ]
