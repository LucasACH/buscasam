"""ADR-0002 §4/§5/§7: chunk boundaries measured against the e5 token budget."""
import httpx
import pytest

from buscasam.core import embed
from buscasam.core.chunk import chunk, headline_chunk
from buscasam.core.extract import ExtractedDoc
from buscasam.core.tokenizer import MAX_TOKENS, passage_token_len
from buscasam.settings import Settings


def _doc(text: str) -> ExtractedDoc:
    return ExtractedDoc(text=text, paragraph_breaks=[], page_breaks=[])


def test_every_passage_chunk_within_budget_cjk():
    chunks = chunk(_doc("日本語のテスト文字列です。" * 600))
    assert chunks
    for c in chunks:
        assert passage_token_len(c.body_text) <= MAX_TOKENS


def test_every_passage_chunk_within_budget_ascii():
    chunks = chunk(_doc("Esta es una oración de prueba. " * 400))
    assert chunks
    for c in chunks:
        assert passage_token_len(c.body_text) <= MAX_TOKENS


def test_no_whitespace_blob_is_split_within_budget():
    chunks = chunk(_doc("a" * 20000))
    assert chunks
    for c in chunks:
        assert passage_token_len(c.body_text) <= MAX_TOKENS


def test_oversized_headline_truncated_to_budget():
    c = headline_chunk("Título " * 40, "palabra " * 3000)
    assert c.is_headline and c.chunk_seq == 0
    assert passage_token_len(c.body_text) <= MAX_TOKENS


def test_short_headline_not_truncated():
    c = headline_chunk("Un título", "Un resumen corto.")
    assert c.body_text == "Un título\n\nUn resumen corto."


def test_chunk_works_with_tei_down(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("TEI is down")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)
    chunks = chunk(_doc("Una oración larga de prueba. " * 300))
    assert chunks
    for c in chunks:
        assert passage_token_len(c.body_text) <= MAX_TOKENS


def test_startup_raises_on_revision_mismatch(monkeypatch):
    monkeypatch.setattr(
        embed, "settings", Settings(embedding_model_revision="deadbeef")
    )
    with pytest.raises(RuntimeError):
        embed.assert_model_revision_pinned()


def test_startup_passes_when_revision_matches():
    embed.assert_model_revision_pinned()
