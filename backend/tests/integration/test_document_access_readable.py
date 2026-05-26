"""readable_where across the three visibility tiers + coauthor predicate.

ADR-0010 §6/§7: the central security gate of the MVP corpus. Each persona
(invitado, estudiante, docente, owner, accepted coauthor, pending coauthor)
must see exactly the documents it is entitled to.
"""
from sqlalchemy import text

from buscasam.core.auth import GUEST, UserCtx
from buscasam.core.document_access import invitado_where, readable_where
from tests.factories import make_document, make_document_author, make_user


async def _readable_ids(session, user_ctx) -> set[int]:
    where, params = readable_where("d", user_ctx)
    return set(
        (
            await session.execute(
                text(f"SELECT d.id FROM documents d WHERE {where}"), params
            )
        )
        .scalars()
        .all()
    )


async def test_visibility_matrix(session):
    publico = await make_document(session, visibility="publico")
    interno = await make_document(session, visibility="interno")
    privado = await make_document(session, visibility="privado")
    # Negative controls: publico but excluded by lifecycle state.
    await make_document(session, publication_status="draft")
    await make_document(session, soft_deleted=True)
    await make_document(session, moderation_hidden=True)

    estudiante_uid = await make_user(session, role="estudiante")
    docente_uid = await make_user(session, role="docente")
    owner_uid = await make_user(session, role="estudiante")
    accepted_uid = await make_user(session, role="estudiante")
    pending_uid = await make_user(session, role="estudiante")

    await make_document_author(session, privado, user_id=owner_uid, status="owner")
    await make_document_author(session, privado, user_id=accepted_uid, status="accepted")
    await make_document_author(session, privado, user_id=pending_uid, status="pending")
    await session.commit()

    def ctx(uid, role="estudiante"):
        return UserCtx(user_id=uid, is_unsam=True, role=role)

    cases = {
        "invitado": (GUEST, {publico}),
        "estudiante": (ctx(estudiante_uid), {publico, interno}),
        "docente": (ctx(docente_uid, "docente"), {publico, interno}),
        "owner": (ctx(owner_uid), {publico, interno, privado}),
        "accepted": (ctx(accepted_uid), {publico, interno, privado}),
        "pending": (ctx(pending_uid), {publico, interno}),
    }
    for name, (user_ctx, expected) in cases.items():
        assert await _readable_ids(session, user_ctx) == expected, name


async def test_pending_coauthor_excluded_from_search_and_detail(session):
    """A `pending` author row grants zero read access until `accepted`."""
    privado = await make_document(session, visibility="privado")
    uid = await make_user(session, role="estudiante")
    author_id = await make_document_author(
        session, privado, user_id=uid, status="pending"
    )
    await session.commit()

    user_ctx = UserCtx(user_id=uid, is_unsam=True, role="estudiante")
    assert privado not in await _readable_ids(session, user_ctx)

    await session.execute(
        text("UPDATE document_authors SET status = 'accepted' WHERE id = :id"),
        {"id": author_id},
    )
    await session.commit()
    assert privado in await _readable_ids(session, user_ctx)


async def test_docente_no_privileged_search_read(session):
    """Docente sees the same set as estudiante for docs they don't own/coauthor."""
    publico = await make_document(session, visibility="publico")
    interno = await make_document(session, visibility="interno")
    await make_document(session, visibility="privado")
    await make_document(session, moderation_hidden=True)
    await session.commit()

    estudiante = UserCtx(
        user_id=await make_user(session, role="estudiante"),
        is_unsam=True,
        role="estudiante",
    )
    docente = UserCtx(
        user_id=await make_user(session, role="docente"),
        is_unsam=True,
        role="docente",
    )

    docente_ids = await _readable_ids(session, docente)
    assert docente_ids == await _readable_ids(session, estudiante)
    assert docente_ids == {publico, interno}


async def test_sitemap_unchanged_under_authenticated_session(session):
    """`invitado_where` (sitemap/anonymous adapter, story 26) stays publico-only.

    It takes no `UserCtx`, so an authenticated `sid` can never widen the
    sitemap beyond `publico` — verified here against a mixed corpus that
    includes an owned `privado` document.
    """
    publico = await make_document(session, visibility="publico")
    await make_document(session, visibility="interno")
    privado = await make_document(session, visibility="privado")
    owner_uid = await make_user(session, role="estudiante")
    await make_document_author(session, privado, user_id=owner_uid, status="owner")
    await session.commit()

    where = invitado_where("d")
    ids = set(
        (await session.execute(text(f"SELECT d.id FROM documents d WHERE {where}")))
        .scalars()
        .all()
    )
    assert ids == {publico}
