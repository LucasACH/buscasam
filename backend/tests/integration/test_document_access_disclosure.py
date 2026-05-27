"""pending_invitation_disclosure_where: the ADR-0010 §6 recipient-scoped
pre-acceptance disclosure predicate.

The first access predicate with no visibility tier — a `pending` invitee
matches on a privado, interno, or publico document alike. Soft-delete and
moderation-hidden filtering are load-bearing (PRD stories 32-33).
"""
import pytest
from sqlalchemy import text

from buscasam.core.auth import GUEST, UserCtx
from buscasam.core.document_access import pending_invitation_disclosure_where
from tests.factories import make_document, make_document_author, make_user


async def _disclosable_ids(session, user_ctx) -> set[int]:
    where, params = pending_invitation_disclosure_where("d", user_ctx)
    return set(
        (
            await session.execute(
                text(f"SELECT d.id FROM documents d WHERE {where}"), params
            )
        )
        .scalars()
        .all()
    )


def _ctx(uid: int) -> UserCtx:
    return UserCtx(user_id=uid, is_unsam=True, role="estudiante")


async def test_pending_invitee_matches_privado(session):
    privado = await make_document(session, visibility="privado")
    uid = await make_user(session)
    await make_document_author(session, privado, user_id=uid, status="pending")
    await session.commit()

    assert await _disclosable_ids(session, _ctx(uid)) == {privado}


async def test_five_cell_matrix(session):
    """PRD Further Notes: from one requester's perspective only a `pending` row
    on the queried document discloses. Accepted, declined, and absent rows
    (different-doc + non-invitee) all fail to match."""
    uid = await make_user(session)
    other = await make_user(session)

    pending = await make_document(session, visibility="privado")
    accepted = await make_document(session, visibility="privado")
    declined = await make_document(session, visibility="privado")
    different = await make_document(session, visibility="privado")  # no row for uid
    non_invitee = await make_document(session, visibility="privado")  # other's pending

    await make_document_author(session, pending, user_id=uid, status="pending")
    await make_document_author(session, accepted, user_id=uid, status="accepted")
    await make_document_author(session, declined, user_id=uid, status="declined")
    await make_document_author(session, non_invitee, user_id=other, status="pending")
    await session.commit()

    assert await _disclosable_ids(session, _ctx(uid)) == {pending}


async def test_recipient_scoped_ignores_visibility(session):
    """The first predicate with no visibility tier — a pending invitee matches
    on privado, interno, and publico alike (ADR-0010 §6)."""
    uid = await make_user(session)
    ids = set()
    for visibility in ("privado", "interno", "publico"):
        doc = await make_document(session, visibility=visibility)
        await make_document_author(session, doc, user_id=uid, status="pending")
        ids.add(doc)
    await session.commit()

    assert await _disclosable_ids(session, _ctx(uid)) == ids


async def test_lifecycle_negatives(session):
    """A pending row on a soft-deleted, moderation-hidden, or unpublished
    document does not disclose (PRD stories 32-33)."""
    uid = await make_user(session)
    for kwargs in (
        {"soft_deleted": True},
        {"moderation_hidden": True},
        {"publication_status": "draft"},
    ):
        doc = await make_document(session, visibility="privado", **kwargs)
        await make_document_author(session, doc, user_id=uid, status="pending")
    await session.commit()

    assert await _disclosable_ids(session, _ctx(uid)) == set()


async def test_guest_raises(session):
    """Invitados cannot be invitees — there is no row to match (ADR-0010 §6)."""
    with pytest.raises(ValueError):
        pending_invitation_disclosure_where("d", GUEST)
