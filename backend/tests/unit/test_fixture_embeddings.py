import numpy as np
import pytest

from buscasam.fixtures import embeddings as fixture_embeddings
from buscasam.fixtures.corpus import Chunk


def test_lookup_raises_with_chunk_context_on_missing_key():
    table = {"deadbeef" * 4: np.zeros(1024, dtype=np.float16)}
    chunk = Chunk(
        id=999, doc_id=42, chunk_seq=7,
        is_headline=False, body_text="never embedded",
    )

    with pytest.raises(KeyError) as exc:
        fixture_embeddings.lookup(table, chunk)

    msg = str(exc.value)
    assert "regenerate embeddings.npz" in msg
    assert "doc_id=42" in msg
    assert "chunk_seq=7" in msg


def test_lookup_returns_vector_for_present_key():
    chunk = Chunk(
        id=1, doc_id=1, chunk_seq=0,
        is_headline=True, body_text="some text",
    )
    key = fixture_embeddings.chunk_key(chunk.body_text)
    vec = np.full(1024, 0.25, dtype=np.float16)

    assert fixture_embeddings.lookup({key: vec}, chunk) is vec
