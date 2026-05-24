from sqlalchemy import text

from buscasam.fixtures.corpus import CHUNKS
from buscasam.fixtures.seed import seed


async def test_every_seeded_chunk_has_nonnull_halfvec_1024(session):
    bind = await session.connection()
    await seed(bind)
    await session.commit()

    missing = (
        await session.execute(
            text("SELECT count(*) FROM chunks WHERE embedding IS NULL")
        )
    ).scalar_one()
    assert missing == 0

    wrong_dim = (
        await session.execute(
            text(
                "SELECT count(*) FROM chunks "
                "WHERE vector_dims(embedding::vector) <> 1024"
            )
        )
    ).scalar_one()
    assert wrong_dim == 0

    total = (
        await session.execute(text("SELECT count(*) FROM chunks"))
    ).scalar_one()
    assert total == len(CHUNKS)
