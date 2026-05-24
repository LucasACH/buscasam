from sqlalchemy import text

from buscasam.core.document_access import invitado_fragment


_DOC_COLS = (
    "id, visibility, publication_status, soft_deleted_at, moderation_hidden_at, "
    "titulo, fecha, area_path, tipo"
)


def _row(id_: int, visibility: str, publication_status: str,
         soft_deleted: str = "NULL", moderation_hidden: str = "NULL") -> str:
    return (
        f"({id_}, '{visibility}', '{publication_status}', "
        f"{soft_deleted}, {moderation_hidden}, "
        f"'doc {id_}', '2024-01-01', 'escuela_ciencia', 'paper')"
    )


async def test_document_access_invitado_excludes_non_publico(session):
    rows = ",".join(
        [
            _row(1, "publico", "published"),
            _row(2, "interno", "published"),
            _row(3, "privado", "published"),
            _row(4, "publico", "draft"),
            _row(5, "publico", "published", soft_deleted="now()"),
            _row(6, "publico", "published", moderation_hidden="now()"),
        ]
    )
    await session.execute(text(f"INSERT INTO documents ({_DOC_COLS}) VALUES {rows}"))
    await session.commit()

    sql, params = invitado_fragment()
    result = (
        await session.execute(
            text(f"SELECT id FROM documents WHERE {sql} ORDER BY id"), params
        )
    ).scalars().all()

    assert result == [1]
