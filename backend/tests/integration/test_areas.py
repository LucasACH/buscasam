from sqlalchemy import text


async def test_areas_table_joins_documents_under_ltree_filter(session):
    await session.execute(
        text(
            "INSERT INTO areas (area_path, display_name) VALUES "
            "('escuela_ciencia', 'Escuela de Ciencia y Tecnología'),"
            "('escuela_ciencia.carrera_informatica', 'Ing. Informática'),"
            "('escuela_humanidades', 'Escuela de Humanidades')"
        )
    )
    await session.execute(
        text(
            "INSERT INTO documents (id, visibility, publication_status, "
            "titulo, fecha, area_path, tipo) VALUES "
            "(20, 'publico', 'published', 'd20', '2024-01-01', "
            "'escuela_ciencia.carrera_informatica', 'paper'),"
            "(21, 'publico', 'published', 'd21', '2024-01-01', "
            "'escuela_humanidades', 'tesis')"
        )
    )
    await session.commit()

    rows = (
        await session.execute(
            text(
                "SELECT d.id, a.display_name FROM documents d "
                "JOIN areas a ON d.area_path = a.area_path "
                "WHERE d.area_path <@ 'escuela_ciencia' ORDER BY d.id"
            )
        )
    ).all()

    assert rows == [(20, "Ing. Informática")]
