from sqlalchemy import text

from buscasam.fixtures.corpus import CHUNKS, DOCUMENTS
from buscasam.fixtures.seed import seed


async def _seed(session) -> None:
    bind = await session.connection()
    await seed(bind)
    await session.commit()


async def test_seed_documents_cover_every_dimension(session):
    await _seed(session)

    counts = {
        "by_visibility": dict(
            (
                await session.execute(
                    text(
                        "SELECT visibility, count(*) FROM documents "
                        "GROUP BY visibility"
                    )
                )
            ).all()
        ),
        "by_publication": dict(
            (
                await session.execute(
                    text(
                        "SELECT publication_status, count(*) FROM documents "
                        "GROUP BY publication_status"
                    )
                )
            ).all()
        ),
        "by_lifecycle_flag": (
            await session.execute(
                text(
                    "SELECT count(*) FILTER (WHERE soft_deleted_at IS NOT NULL), "
                    "count(*) FILTER (WHERE moderation_hidden_at IS NOT NULL) "
                    "FROM documents"
                )
            )
        ).one(),
        "by_tipo": dict(
            (
                await session.execute(
                    text("SELECT tipo, count(*) FROM documents GROUP BY tipo")
                )
            ).all()
        ),
        "by_area_level": dict(
            (
                await session.execute(
                    text(
                        "SELECT nlevel(area_path), count(*) FROM documents "
                        "GROUP BY nlevel(area_path)"
                    )
                )
            ).all()
        ),
        "distinct_years": (
            await session.execute(
                text("SELECT count(DISTINCT extract(year FROM fecha)) FROM documents")
            )
        ).scalar_one(),
    }

    assert counts["by_visibility"] == {"publico": 13, "interno": 1, "privado": 1}
    assert counts["by_publication"] == {"published": 14, "draft": 1}
    assert counts["by_lifecycle_flag"] == (1, 1)
    assert set(counts["by_tipo"].keys()) == {
        "tesis", "paper", "trabajo_practico", "proyecto_investigacion",
        "monografia", "ponencia_poster", "apunte_resumen", "informe_catedra",
    }
    assert set(counts["by_area_level"].keys()) == {1, 2, 3}
    assert counts["distinct_years"] >= 5


async def test_seed_is_idempotent(session):
    await _seed(session)
    await _seed(session)

    doc_count = (
        await session.execute(text("SELECT count(*) FROM documents"))
    ).scalar_one()
    chunk_count = (
        await session.execute(text("SELECT count(*) FROM chunks"))
    ).scalar_one()

    assert doc_count == len(DOCUMENTS)
    assert chunk_count == len(CHUNKS)
