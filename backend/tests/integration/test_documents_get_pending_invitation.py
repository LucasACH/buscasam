"""core/documents.get_pending_invitation: the disclosure read composing
pending_invitation_disclosure_where (ADR-0010 §6, module map §core/documents).

The five-cell matrix lives in test_document_access_disclosure.py; this pins
the composition — the disclosure payload, the guest short-circuit, and the
None-on-miss contract.
"""
from sqlalchemy import text

from buscasam.core import documents
from buscasam.core.auth import GUEST, UserCtx


def _ctx(uid: int) -> UserCtx:
    return UserCtx(user_id=uid, is_unsam=True, role="estudiante")


async def _seed_current_version(session, doc_id: int) -> None:
    await session.execute(
        text(
            "INSERT INTO document_versions "
            "(doc_id, version_no, sha256, original_filename, bytes, mime, "
            " index_status, is_current) "
            "VALUES (:d, 1, decode(:sha, 'hex'), 'tesis.pdf', 2048, "
            "        'application/pdf', 'indexed', true)"
        ),
        {"d": doc_id, "sha": "aa" * 32},
    )


async def test_returns_disclosure_payload_for_pending_invitee(session):
    from tests.factories import make_document, make_document_author, make_user

    doc_id = await make_document(session, visibility="privado", titulo="Tesis X")
    await _seed_current_version(session, doc_id)
    owner_id = await make_user(session)
    invitee_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=owner_id, status="owner", display_name="Ada Lovelace"
    )
    await make_document_author(
        session, doc_id, user_id=invitee_id, status="pending", display_name="Invitee"
    )
    await session.commit()

    disclosure = await documents.get_pending_invitation(
        session, doc_id, _ctx(invitee_id)
    )

    assert disclosure == documents.InvitationDisclosure(
        doc_id=doc_id, titulo="Tesis X", inviter_display_name="Ada Lovelace"
    )


async def test_returns_none_for_guest_without_raising(session):
    from tests.factories import make_document, make_document_author, make_user

    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    invitee_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=invitee_id, status="pending"
    )
    await session.commit()

    assert await documents.get_pending_invitation(session, doc_id, GUEST) is None


async def test_returns_none_when_predicate_does_not_match(session):
    """Accepted invitee goes through readable_where, not disclosure."""
    from tests.factories import make_document, make_document_author, make_user

    doc_id = await make_document(session, visibility="privado")
    await _seed_current_version(session, doc_id)
    accepted_id = await make_user(session)
    await make_document_author(
        session, doc_id, user_id=accepted_id, status="accepted"
    )
    await session.commit()

    assert (
        await documents.get_pending_invitation(session, doc_id, _ctx(accepted_id))
        is None
    )
