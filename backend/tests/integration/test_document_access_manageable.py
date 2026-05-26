"""manageable_where: owner+accepted access, pending+other excluded (ADR-0010 §8)."""
from sqlalchemy import text

from buscasam.core.auth import UserCtx
from buscasam.core.document_access import manageable_where
from tests.factories import make_document, make_document_author, make_user


async def _manageable_ids(session, user_ctx) -> set[int]:
    where, params = manageable_where("d", user_ctx)
    return set(
        (
            await session.execute(
                text(f"SELECT d.id FROM documents d WHERE {where}"), params
            )
        )
        .scalars()
        .all()
    )


async def test_manageable_owner_and_accepted_visible(session):
    doc = await make_document(session, publication_status="draft", visibility="privado")
    owner_uid = await make_user(session, role="estudiante")
    accepted_uid = await make_user(session, role="estudiante")
    pending_uid = await make_user(session, role="estudiante")
    other_uid = await make_user(session, role="estudiante")

    await make_document_author(session, doc, user_id=owner_uid, status="owner")
    await make_document_author(session, doc, user_id=accepted_uid, status="accepted")
    await make_document_author(session, doc, user_id=pending_uid, status="pending")
    await session.commit()

    def ctx(uid):
        return UserCtx(user_id=uid, is_unsam=True, role="estudiante")

    assert doc in await _manageable_ids(session, ctx(owner_uid))
    assert doc in await _manageable_ids(session, ctx(accepted_uid))
    assert doc not in await _manageable_ids(session, ctx(pending_uid))
    assert doc not in await _manageable_ids(session, ctx(other_uid))


async def test_manageable_excludes_soft_deleted(session):
    doc = await make_document(session, soft_deleted=True)
    uid = await make_user(session)
    await make_document_author(session, doc, user_id=uid, status="owner")
    await session.commit()

    ids = await _manageable_ids(session, UserCtx(user_id=uid, is_unsam=True, role="estudiante"))
    assert doc not in ids


async def test_manageable_includes_draft_and_published(session):
    draft = await make_document(session, publication_status="draft")
    published = await make_document(session, publication_status="published")
    uid = await make_user(session)
    await make_document_author(session, draft, user_id=uid, status="owner")
    await make_document_author(session, published, user_id=uid, status="owner")
    await session.commit()

    ids = await _manageable_ids(session, UserCtx(user_id=uid, is_unsam=True, role="estudiante"))
    assert draft in ids
    assert published in ids
