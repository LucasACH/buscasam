"""Integration tests for the get_draft_state coauthors[] extension (issue #52,
module map §core/documents). The DTO carries is_owner + coauthors with the
owner row first and registered rows in insertion order."""
from __future__ import annotations

from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from tests.factories import make_document, make_document_author, make_user


def _ctx(uid: int) -> UserCtx:
    return UserCtx(user_id=uid, is_unsam=True, role="estudiante")


async def _seed_draft_with_version(session, owner_id: int) -> int:
    doc_id = await make_document(session, publication_status="draft", titulo="t")
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Ada"
    )
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " uploaded_by, index_status, headline_fingerprint) "
            "VALUES (:d, 1, decode(repeat('00', 32), 'hex'), 'f', 1, "
            " 'application/pdf', :uid, 'indexed', :fp)"
        ),
        {"d": doc_id, "uid": owner_id, "fp": _fp_for("t")},
    )
    return doc_id


def _fp_for(title: str) -> str:
    from buscasam.core.chunk import headline_fingerprint
    return headline_fingerprint(title, "")


async def test_draft_state_lists_owner_first_then_insertion_order(session):
    owner = await make_user(session, name="Ada")
    doc_id = await _seed_draft_with_version(session, owner)
    bob = await make_user(session, name="Bob")
    carla = await make_user(session, name="Carla")
    await make_document_author(
        session, doc_id, user_id=bob, status="pending", display_name="Bob"
    )
    await make_document_author(
        session, doc_id, user_id=carla, status="accepted", display_name="Carla"
    )
    await make_document_author(
        session, doc_id, user_id=None, status="external", display_name="Ext Ed"
    )

    state = await documents.get_draft_state(session, _ctx(owner), doc_id)

    assert state.is_owner is True
    names = [c.display_name for c in state.coauthors]
    assert names == ["Ada", "Bob", "Carla", "Ext Ed"]
    statuses = [c.status for c in state.coauthors]
    assert statuses == ["owner", "pending", "accepted", "external"]
    # Registered rows carry user_id; external rows do not.
    assert state.coauthors[0].user_id == owner
    assert state.coauthors[1].user_id == bob
    assert state.coauthors[2].user_id == carla
    assert state.coauthors[3].user_id is None
