from sqlalchemy import text

from buscasam.core.document_access import invitado_where
from tests.factories import make_document


async def test_document_access_invitado_excludes_non_publico(session):
    publico_published = await make_document(session)
    await make_document(session, visibility="interno")
    await make_document(session, visibility="privado")
    await make_document(session, publication_status="draft")
    await make_document(session, soft_deleted=True)
    await make_document(session, moderation_hidden=True)
    await session.commit()

    where = invitado_where("d")
    result = (
        await session.execute(
            text(f"SELECT d.id FROM documents d WHERE {where} ORDER BY d.id")
        )
    ).scalars().all()

    assert result == [publico_published]
