"""restorable_where — the single predicate that *selects* soft-deleted rows.

The deliberate inverse of the four exclusion predicates (module map
§core/document_access, issue #66): owner-scoped (status = 'owner' only, NOT the
manageable owner|accepted set) AND soft_deleted_at IS NOT NULL. Drives restore
and list_deleted_documents.
"""
from sqlalchemy import text

from buscasam.core.auth import UserCtx
from buscasam.core.document_access import restorable_where
from tests.factories import make_document, make_document_author, make_user


def _ctx(uid: int) -> UserCtx:
    return UserCtx(user_id=uid, is_unsam=True, role="estudiante")


async def _restorable_ids(session, user_ctx) -> set[int]:
    where, params = restorable_where("d", user_ctx)
    return set(
        (
            await session.execute(
                text(f"SELECT d.id FROM documents d WHERE {where}"), params
            )
        )
        .scalars()
        .all()
    )


async def test_restorable_matrix(session):
    owner = await make_user(session)
    other = await make_user(session)

    # The one row restorable_where must select: owner's own soft-deleted doc.
    deleted_own = await make_document(session, soft_deleted=True)
    await make_document_author(session, deleted_own, user_id=owner, status="owner")

    # Live doc owned by the caller — excluded (soft_deleted_at IS NULL).
    live_own = await make_document(session, soft_deleted=False)
    await make_document_author(session, live_own, user_id=owner, status="owner")

    # Accepted coautor (NOT owner) on a soft-deleted doc — excluded: restore is
    # owner-only, stricter than manageable_where's owner|accepted set.
    deleted_as_coautor = await make_document(session, soft_deleted=True)
    await make_document_author(
        session, deleted_as_coautor, user_id=other, status="owner"
    )
    await make_document_author(
        session, deleted_as_coautor, user_id=owner, status="accepted"
    )

    # Another user's soft-deleted doc — excluded (owner-scoped, no leak).
    deleted_other = await make_document(session, soft_deleted=True)
    await make_document_author(session, deleted_other, user_id=other, status="owner")
    await session.commit()

    assert await _restorable_ids(session, _ctx(owner)) == {deleted_own}
