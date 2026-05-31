"""Integration tests for core/discovery (read tracking + más leídos, issue #109)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from buscasam.core import discovery
from tests.factories import make_document


async def _seed_reads(session, doc_id: int, *, days_ago: int, readers: int) -> None:
    """Insert `readers` distinct lecturas dated `days_ago` days before today."""
    for i in range(readers):
        await session.execute(
            text(
                "INSERT INTO document_reads (doc_id, reader_key, read_day) "
                "VALUES (:d, :k, CURRENT_DATE - :n)"
            ),
            {"d": doc_id, "k": f"u:{days_ago}:{i}", "n": days_ago},
        )


async def _read_count(session, doc_id: int) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM document_reads WHERE doc_id = :d"),
            {"d": doc_id},
        )
    ).scalar_one()


async def test_record_read_persists_one_lectura(session):
    doc_id = await make_document(session)
    await discovery.record_read(session, doc_id, "u:1")
    assert await _read_count(session, doc_id) == 1


async def test_record_read_same_reader_same_day_is_idempotent(session):
    doc_id = await make_document(session)
    await discovery.record_read(session, doc_id, "u:1")
    await discovery.record_read(session, doc_id, "u:1")
    assert await _read_count(session, doc_id) == 1


async def test_most_read_ranks_publico_by_lectura_count(session):
    hot = await make_document(
        session,
        titulo="Hot",
        area_path="escuela_ciencia",
        tipo="tesis",
        fecha=date(2024, 3, 1),
    )
    warm = await make_document(session, titulo="Warm")
    await _seed_reads(session, hot, days_ago=1, readers=3)
    await _seed_reads(session, warm, days_ago=1, readers=1)
    await session.commit()

    rows = await discovery.most_read(session, window_days=7, limit=3)

    assert [r.doc_id for r in rows] == [hot, warm]
    top = rows[0]
    assert top.titulo == "Hot"
    assert top.area_path == "escuela_ciencia"
    assert top.tipo == "tesis"
    assert top.fecha == date(2024, 3, 1)
    assert top.reads == 3


async def test_most_read_excludes_non_publico_even_if_more_read(session):
    publico = await make_document(session, visibility="publico", titulo="Pub")
    interno = await make_document(session, visibility="interno", titulo="Int")
    privado = await make_document(session, visibility="privado", titulo="Priv")
    await _seed_reads(session, publico, days_ago=1, readers=1)
    await _seed_reads(session, interno, days_ago=1, readers=9)
    await _seed_reads(session, privado, days_ago=1, readers=9)
    await session.commit()

    rows = await discovery.most_read(session, window_days=7, limit=10)

    assert [r.doc_id for r in rows] == [publico]


async def test_most_read_ignores_reads_outside_window(session):
    doc_id = await make_document(session)
    await _seed_reads(session, doc_id, days_ago=1, readers=2)
    await _seed_reads(session, doc_id, days_ago=30, readers=5)
    await session.commit()

    rows = await discovery.most_read(session, window_days=7, limit=10)

    assert rows[0].reads == 2


async def test_most_read_caps_at_limit(session):
    for i in range(5):
        doc_id = await make_document(session, titulo=f"D{i}")
        await _seed_reads(session, doc_id, days_ago=1, readers=i + 1)
    await session.commit()

    rows = await discovery.most_read(session, window_days=7, limit=3)

    assert len(rows) == 3
