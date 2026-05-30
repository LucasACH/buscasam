"""Unit tests for core/chunk (issue #28).

headline_fingerprint must be stable under whitespace + case normalization,
so the publish gate and the worker compute the same value without
coordination (module map §core/chunk).
"""
from __future__ import annotations

from buscasam.core.chunk import chunk, headline_chunk, headline_fingerprint
from buscasam.core.extract import ExtractedDoc
from buscasam.core.tokenizer import MAX_TOKENS, passage_token_len


def test_headline_fingerprint_is_deterministic():
    fp1 = headline_fingerprint("My Thesis", "An abstract.")
    fp2 = headline_fingerprint("My Thesis", "An abstract.")
    assert fp1 == fp2


def test_headline_fingerprint_normalizes_case():
    assert headline_fingerprint("My Thesis", "Abstract") == headline_fingerprint(
        "MY THESIS", "ABSTRACT"
    )


def test_headline_fingerprint_normalizes_inner_whitespace():
    assert headline_fingerprint("My  thesis", "A\tlong abstract") == headline_fingerprint(
        "My thesis", "A long abstract"
    )


def test_headline_fingerprint_strips_outer_whitespace():
    assert headline_fingerprint(" My thesis ", "An abstract.\n") == headline_fingerprint(
        "My thesis", "An abstract."
    )


def test_headline_fingerprint_differs_on_content_change():
    assert headline_fingerprint("Thesis", "abstract a") != headline_fingerprint(
        "Thesis", "abstract b"
    )


def test_headline_fingerprint_separates_title_and_abstract():
    """Concatenating across the boundary must not collide."""
    assert headline_fingerprint("ab", "cd") != headline_fingerprint("abc", "d")


def test_headline_fingerprint_returns_hex_string():
    fp = headline_fingerprint("title", "abstract")
    assert isinstance(fp, str)
    assert all(c in "0123456789abcdef" for c in fp)
    assert len(fp) == 32


def test_headline_chunk_marks_is_headline_with_chunk_seq_0():
    c = headline_chunk("My Thesis", "An abstract.")
    assert c.is_headline is True
    assert c.chunk_seq == 0
    assert "My Thesis" in c.body_text
    assert "An abstract." in c.body_text


def test_chunk_splits_on_paragraph_breaks():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    # paragraph_breaks: byte offsets at the END of each paragraph
    breaks = [16, 36, 56]
    doc = ExtractedDoc(text=text, paragraph_breaks=breaks, page_breaks=[], raw_metadata={})
    chunks = chunk(doc)
    assert len(chunks) == 3
    assert all(not c.is_headline for c in chunks)
    assert [c.chunk_seq for c in chunks] == [1, 2, 3]
    assert chunks[0].body_text == "First paragraph."
    assert chunks[1].body_text == "Second paragraph."
    assert chunks[2].body_text == "Third paragraph."


def test_chunk_empty_text_produces_no_chunks():
    doc = ExtractedDoc(text="", paragraph_breaks=[], page_breaks=[], raw_metadata={})
    assert chunk(doc) == []


def test_chunk_no_paragraph_breaks_yields_single_chunk():
    """A doc with text but no detected paragraph breaks is one chunk."""
    doc = ExtractedDoc(
        text="just one block of text", paragraph_breaks=[], page_breaks=[], raw_metadata={}
    )
    chunks = chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].body_text == "just one block of text"
    assert chunks[0].chunk_seq == 1


def test_chunk_splits_oversized_paragraph_at_sentence_boundaries():
    """ADR-0002 §4: paragraphs above the token budget split at sentence boundaries."""
    sentence = "Esta es una oración larga sobre el tema del trabajo. "
    big = sentence * 200  # ≈ 10kB, well above the 512-token budget
    doc = ExtractedDoc(text=big, paragraph_breaks=[], page_breaks=[], raw_metadata={})
    chunks = chunk(doc)
    assert len(chunks) > 1
    assert all(passage_token_len(c.body_text) <= MAX_TOKENS for c in chunks)
    assert [c.chunk_seq for c in chunks] == list(range(1, len(chunks) + 1))
