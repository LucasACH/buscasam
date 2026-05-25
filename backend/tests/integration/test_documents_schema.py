from sqlalchemy import text


async def test_documents_supports_full_publishable_shape_and_ltree_filter(session):
    await session.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, "
            "titulo, fecha, area_path, tipo, abstract) VALUES "
            "(10, 'publico', 'published', 'On Hybrid Search', '2024-03-15', "
            "'escuela_ciencia.carrera_informatica.materia_bases_datos', "
            "'paper', 'A short abstract.'),"
            "(11, 'publico', 'published', 'On Statistics', '2023-09-01', "
            "'escuela_humanidades.carrera_filosofia.materia_logica', "
            "'tesis', NULL)"
        )
    )
    await session.commit()

    rows = (
        await session.execute(
            text(
                "SELECT id FROM documents "
                "WHERE area_path <@ 'escuela_ciencia' ORDER BY id"
            )
        )
    ).scalars().all()

    assert rows == [10]
