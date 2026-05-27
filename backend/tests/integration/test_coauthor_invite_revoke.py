"""Integration tests for core/documents.invite_coauthor / revoke_invitation
(issue #52, module map §core/documents). Owner-only lifecycle: pending row
insert on invite (transactional fan-out enqueue on a published doc), atomic
DELETE of the document_authors row and matching notifications row on revoke.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import UserCtx
from buscasam.core.jobs import coauthor_invite_event_key
from tests.factories import (
    make_document,
    make_document_author,
    make_notification,
    make_user,
)


def _ctx(user_id: int) -> UserCtx:
    return UserCtx(user_id=user_id, is_unsam=True, role="estudiante")


async def _seed_doc(session, *, publication_status="draft"):
    owner = await make_user(session, name="Ada")
    doc_id = await make_document(
        session, publication_status=publication_status, titulo="Mi trabajo"
    )
    await make_document_author(
        session, doc_id, user_id=owner, status="owner", display_name="Ada"
    )
    return doc_id, owner


async def _status(session, doc_id, user_id) -> str | None:
    return (
        await session.execute(
            text(
                "SELECT status FROM document_authors "
                "WHERE doc_id = :d AND user_id = :u"
            ),
            {"d": doc_id, "u": user_id},
        )
    ).scalar_one_or_none()


async def test_invite_on_draft_inserts_pending_row_no_fan_out(session):
    doc_id, owner = await _seed_doc(session, publication_status="draft")
    invitee = await make_user(session, name="Bob")

    await documents.invite_coauthor(session, _ctx(owner), doc_id, invitee)

    assert await _status(session, doc_id, invitee) == "pending"
    enqueued = (
        await session.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE args->>'doc_id' = :did"
            ),
            {"did": str(doc_id)},
        )
    ).scalar_one()
    assert enqueued == 0


@pytest.mark.parametrize("existing_status", ["pending", "accepted", "declined", "owner"])
async def test_invite_with_existing_row_raises_already_listed(
    session, existing_status
):
    """Re-invite blocked regardless of status — covers the PRD story 10 rule
    that a declined user cannot be re-invited."""
    doc_id, owner = await _seed_doc(session)
    if existing_status == "owner":
        target = owner
    else:
        target = await make_user(session, name=f"{existing_status}-user")
        await make_document_author(
            session, doc_id, user_id=target, status=existing_status
        )

    with pytest.raises(documents.CoauthorAlreadyListed):
        await documents.invite_coauthor(session, _ctx(owner), doc_id, target)


async def test_revoke_pending_deletes_row_and_matching_notification(session):
    """Atomic delete (module map §core/documents, PRD story 7)."""
    doc_id, owner = await _seed_doc(session, publication_status="published")
    invitee = await make_user(session, name="Bob")
    await make_document_author(session, doc_id, user_id=invitee, status="pending")
    await make_notification(
        session,
        user_id=invitee,
        kind="coauthor_invite",
        event_key=coauthor_invite_event_key(doc_id, invitee),
    )

    await documents.revoke_invitation(session, _ctx(owner), doc_id, invitee)

    assert await _status(session, doc_id, invitee) is None
    notif_count = (
        await session.execute(
            text(
                "SELECT count(*) FROM notifications "
                "WHERE user_id = :uid AND event_key = :ek"
            ),
            {
                "uid": invitee,
                "ek": coauthor_invite_event_key(doc_id, invitee),
            },
        )
    ).scalar_one()
    assert notif_count == 0


@pytest.mark.parametrize("status", ["accepted", "declined"])
async def test_revoke_non_pending_raises_coauthor_not_pending(session, status):
    """Revoke pending-only at MVP (ADR-0010 §5)."""
    doc_id, owner = await _seed_doc(session)
    invitee = await make_user(session, name="Bob")
    await make_document_author(session, doc_id, user_id=invitee, status=status)

    with pytest.raises(documents.CoauthorNotPending):
        await documents.revoke_invitation(session, _ctx(owner), doc_id, invitee)

    # Row is untouched.
    assert await _status(session, doc_id, invitee) == status


async def test_revoke_missing_row_raises_coauthor_not_pending(session):
    doc_id, owner = await _seed_doc(session)
    ghost = await make_user(session, name="Ghost")

    with pytest.raises(documents.CoauthorNotPending):
        await documents.revoke_invitation(session, _ctx(owner), doc_id, ghost)


async def test_revoke_by_non_owner_raises_not_owner(session):
    doc_id, _owner = await _seed_doc(session)
    accepted = await make_user(session, name="Acc")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    invitee = await make_user(session, name="Bob")
    await make_document_author(session, doc_id, user_id=invitee, status="pending")

    with pytest.raises(documents.NotOwner):
        await documents.revoke_invitation(session, _ctx(accepted), doc_id, invitee)


async def test_revoke_then_reinvite_round_trip_produces_fresh_notification(session):
    """After revoke deletes both rows, a fresh invite_coauthor on a published
    doc enqueues fan-out and a re-run inserts a new notification under the
    same dedup key (no ON CONFLICT collision)."""
    doc_id, owner = await _seed_doc(session, publication_status="published")
    invitee = await make_user(session, name="Bob")

    await documents.invite_coauthor(session, _ctx(owner), doc_id, invitee)
    from buscasam.core import jobs
    await jobs._run_fan_out_coauthor_invites(session, doc_id)
    first_id = (
        await session.execute(
            text(
                "SELECT id FROM notifications "
                "WHERE user_id = :uid AND event_key = :ek"
            ),
            {"uid": invitee, "ek": coauthor_invite_event_key(doc_id, invitee)},
        )
    ).scalar_one()

    await documents.revoke_invitation(session, _ctx(owner), doc_id, invitee)
    await documents.invite_coauthor(session, _ctx(owner), doc_id, invitee)
    await jobs._run_fan_out_coauthor_invites(session, doc_id)

    second_id = (
        await session.execute(
            text(
                "SELECT id FROM notifications "
                "WHERE user_id = :uid AND event_key = :ek"
            ),
            {"uid": invitee, "ek": coauthor_invite_event_key(doc_id, invitee)},
        )
    ).scalar_one()
    # New row, not the original — the revoke's joint DELETE cleared the way.
    assert second_id != first_id
    assert await _status(session, doc_id, invitee) == "pending"


async def test_invite_by_non_owner_raises_not_owner(session):
    """Even an accepted coautor (who passes manageable_where) cannot manage
    coauthors — owner-only is stricter (ADR-0010 §8)."""
    doc_id, _owner = await _seed_doc(session)
    accepted = await make_user(session, name="Acc")
    await make_document_author(session, doc_id, user_id=accepted, status="accepted")
    invitee = await make_user(session, name="New")

    with pytest.raises(documents.NotOwner):
        await documents.invite_coauthor(session, _ctx(accepted), doc_id, invitee)


async def test_invite_on_published_enqueues_fan_out_in_same_txn(session):
    """ADR-0008 §1: the fan-out task INSERT is visible from the invite txn."""
    doc_id, owner = await _seed_doc(session, publication_status="published")
    invitee = await make_user(session, name="Bob")

    await documents.invite_coauthor(session, _ctx(owner), doc_id, invitee)

    assert await _status(session, doc_id, invitee) == "pending"
    row = (
        await session.execute(
            text(
                "SELECT task_name FROM procrastinate_jobs "
                "WHERE args->>'doc_id' = :did"
            ),
            {"did": str(doc_id)},
        )
    ).mappings().one_or_none()
    assert row is not None
    assert row["task_name"].endswith("fan_out_coauthor_invites")
