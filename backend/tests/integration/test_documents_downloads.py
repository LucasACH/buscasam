"""Integration tests for core/documents download lookups (issue: deepening §4).

Pins the access matrix at the lookup boundary so the router tests can stay
focused on transport (headers, X-Accel projection, 404 envelope).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from buscasam.core import documents
from buscasam.core.auth import GUEST, UserCtx
from tests.factories import make_document, make_document_author, make_user


def _student(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


def _docente(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="docente")


async def _seed_current_version(
    session: AsyncSession,
    doc_id: int,
    *,
    original_filename: str = "tesis.pdf",
    bytes_: int = 2048,
    mime: str = "application/pdf",
    sha_hex: str = "aa" * 32,
) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) "
            "VALUES (:d, 1, decode(:sha, 'hex'), :name, :b, :m, 'indexed', true, now())"
        ),
        {"d": doc_id, "sha": sha_hex, "name": original_filename, "b": bytes_, "m": mime},
    )


async def _seed_version(
    session: AsyncSession,
    doc_id: int,
    *,
    version_no: int,
    original_filename: str,
    sha_hex: str,
    is_current: bool = False,
    bytes_: int = 1024,
    mime: str = "application/pdf",
    index_status: str = "indexed",
    first_published: bool = True,
) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current, first_published_at) "
            "VALUES (:d, :vn, decode(:sha, 'hex'), :name, :b, :m, :st, :cur, "
            "        CASE WHEN :fp THEN now() ELSE NULL END)"
        ),
        {
            "d": doc_id,
            "vn": version_no,
            "sha": sha_hex,
            "name": original_filename,
            "b": bytes_,
            "m": mime,
            "cur": is_current,
            "st": index_status,
            "fp": first_published,
        },
    )


async def _seed_attachment(
    session: AsyncSession,
    doc_id: int,
    *,
    original_filename: str = "datos.csv",
    mime: str | None = "text/csv",
    sha_hex: str = "bb" * 32,
) -> int:
    return (
        await session.execute(
            text(
                "INSERT INTO document_attachments "
                "(doc_id, sha256, original_filename, bytes, mime) "
                "VALUES (:d, decode(:sha, 'hex'), :name, 512, :m) RETURNING id"
            ),
            {"d": doc_id, "sha": sha_hex, "name": original_filename, "m": mime},
        )
    ).scalar_one()


# --- get_readable_main_file ---


async def test_main_file_publico_granted_for_invitado(session):
    doc_id = await make_document(session, visibility="publico")
    await _seed_current_version(session, doc_id, sha_hex="ab" + "cd" * 31)

    file = await documents.get_readable_main_file(session, doc_id, GUEST)

    assert file is not None
    assert file.sha_hex == "ab" + "cd" * 31
    assert file.original_filename == "tesis.pdf"
    assert file.mime == "application/pdf"


@pytest.mark.parametrize(
    "factory_kwargs",
    [
        {"visibility": "interno"},
        {"visibility": "privado"},
        {"publication_status": "draft"},
        {"soft_deleted": True},
        {"moderation_hidden": True},
    ],
    ids=["interno", "privado", "draft", "soft_deleted", "moderation_hidden"],
)
async def test_main_file_denied_for_invitado_returns_none(session, factory_kwargs):
    doc_id = await make_document(session, **factory_kwargs)
    await _seed_current_version(session, doc_id)

    assert await documents.get_readable_main_file(session, doc_id, GUEST) is None


async def test_main_file_interno_granted_for_unsam(session):
    doc_id = await make_document(session, visibility="interno")
    await _seed_current_version(session, doc_id)
    uid = await make_user(session, role="estudiante")

    assert await documents.get_readable_main_file(session, doc_id, _student(uid)) is not None


async def test_main_file_privado_granted_for_accepted_coautor(session):
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    uid = await make_user(session, role="docente")
    await make_document_author(
        session, doc_id, user_id=uid, status="accepted", display_name="Co"
    )

    assert await documents.get_readable_main_file(session, doc_id, _docente(uid)) is not None


async def test_main_file_privado_pending_coautor_returns_none(session):
    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    uid = await make_user(session, role="estudiante")
    await make_document_author(
        session, doc_id, user_id=uid, status="pending", display_name="P"
    )

    assert await documents.get_readable_main_file(session, doc_id, _student(uid)) is None


async def test_main_file_missing_doc_returns_none(session):
    assert await documents.get_readable_main_file(session, 999_999, GUEST) is None


# --- get_readable_attachment ---


async def test_attachment_publico_granted_with_null_mime_preserved(session):
    doc_id = await make_document(session, visibility="publico")
    att_id = await _seed_attachment(session, doc_id, mime=None)

    file = await documents.get_readable_attachment(session, doc_id, att_id, GUEST)

    assert file is not None
    assert file.mime is None
    assert file.original_filename == "datos.csv"


async def test_attachment_denied_on_privado_for_invitado_returns_none(session):
    doc_id = await make_document(session, visibility="privado")
    att_id = await _seed_attachment(session, doc_id)

    assert await documents.get_readable_attachment(session, doc_id, att_id, GUEST) is None


async def test_attachment_unknown_att_id_returns_none(session):
    doc_id = await make_document(session, visibility="publico")
    await _seed_attachment(session, doc_id)

    assert await documents.get_readable_attachment(session, doc_id, 999_999, GUEST) is None


# --- get_manageable_version_file ---


async def _seed_two_versions(session: AsyncSession, doc_id: int) -> None:
    await _seed_version(
        session, doc_id, version_no=1, original_filename="tesis_v1.pdf",
        sha_hex="11" * 32, is_current=False,
    )
    await _seed_version(
        session, doc_id, version_no=2, original_filename="tesis_v2.pdf",
        sha_hex="22" * 32, is_current=True,
    )


@pytest.mark.parametrize("status", ["owner", "accepted"])
async def test_version_each_n_granted_for_manager(session, status):
    doc_id = await make_document(session, visibility="privado")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    requester = owner
    ctx: UserCtx = _docente(owner)
    if status == "accepted":
        requester = await make_user(session, role="docente")
        await make_document_author(
            session, doc_id, user_id=requester, status="accepted", display_name="Co"
        )
        ctx = _docente(requester)
    await _seed_two_versions(session, doc_id)

    v1 = await documents.get_manageable_version_file(session, doc_id, 1, ctx)
    v2 = await documents.get_manageable_version_file(session, doc_id, 2, ctx)

    assert v1 is not None and v1.original_filename == "tesis_v1.pdf"
    assert v1.sha_hex == "11" * 32
    assert v2 is not None and v2.original_filename == "tesis_v2.pdf"
    assert v2.sha_hex == "22" * 32


@pytest.mark.parametrize(
    "requester",
    ["invitado", "estudiante_non_author", "pending_coautor"],
)
async def test_version_non_manager_returns_none(session, requester):
    doc_id = await make_document(session, visibility="publico")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await _seed_two_versions(session, doc_id)

    if requester == "invitado":
        ctx = GUEST
    else:
        uid = await make_user(session, role="estudiante")
        if requester == "pending_coautor":
            await make_document_author(
                session, doc_id, user_id=uid, status="pending", display_name="P"
            )
        ctx = _student(uid)

    assert await documents.get_manageable_version_file(session, doc_id, 1, ctx) is None
    assert await documents.get_manageable_version_file(session, doc_id, 2, ctx) is None


@pytest.mark.parametrize("bad_n", [0, -1, 3, 99])
async def test_version_out_of_range_returns_none(session, bad_n):
    doc_id = await make_document(session, visibility="privado")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await _seed_two_versions(session, doc_id)

    assert (
        await documents.get_manageable_version_file(session, doc_id, bad_n, _docente(owner))
        is None
    )


@pytest.mark.parametrize("index_status", ["pending", "processing", "indexed", "failed"])
async def test_version_never_published_returns_none_for_manager(session, index_status):
    """ADR-0011 §4: a candidate that was never the public current
    (first_published_at IS NULL) is not downloadable through the historic-version
    lookup, regardless of its index_status or the caller's role."""
    doc_id = await make_document(session, visibility="privado")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    # version_no=1 is the published current; the candidate is version_no=2.
    await _seed_version(
        session, doc_id, version_no=1, original_filename="published.pdf",
        sha_hex="11" * 32, is_current=True,
    )
    await _seed_version(
        session, doc_id, version_no=2, original_filename="candidate.pdf",
        sha_hex="33" * 32, index_status=index_status, first_published=False,
    )

    # The candidate is filtered out before row_number() runs, so n=2 resolves
    # to no row while the published current keeps n=1.
    assert (
        await documents.get_manageable_version_file(session, doc_id, 2, _docente(owner))
        is None
    )
    published = await documents.get_manageable_version_file(
        session, doc_id, 1, _docente(owner)
    )
    assert published is not None and published.original_filename == "published.pdf"


async def test_version_n_ordering_matches_get_detail(session):
    """The row_number() ordering (`ORDER BY id`) used by the version lookup
    must match `get_detail.versions[].n`; otherwise the manager UI would
    download a different file than the row it clicked."""
    doc_id = await make_document(session, visibility="privado")
    owner = await make_user(session)
    await make_document_author(session, doc_id, user_id=owner, status="owner")
    await _seed_two_versions(session, doc_id)
    ctx = _docente(owner)

    detail = await documents.get_detail(session, doc_id, ctx)
    assert detail is not None and detail.versions is not None
    for v in detail.versions:
        file = await documents.get_manageable_version_file(session, doc_id, v.n, ctx)
        assert file is not None
        assert file.original_filename == v.original_filename
