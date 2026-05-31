"""Unit tests for `core/embed` — TEI chokepoint (ADR-0002 §3)."""

from __future__ import annotations

import json

import httpx
import numpy as np
import pytest

from buscasam.core import embed as embed_mod
from buscasam.core.embed import EmbedUnavailable, embed


@pytest.fixture(autouse=True)
def _clear_query_cache():
    embed_mod._query_cache.clear()
    yield
    embed_mod._query_cache.clear()


async def test_embed_query_sends_query_prefix_and_returns_1024d_halfvec():
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json=[[0.01] * 1024])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://tei") as client:
        vec = await embed(client, "foo", kind="query")

    assert vec.shape == (1024,)
    assert vec.dtype == np.float16

    body = json.loads(captured["body"])
    assert body["inputs"] == ["query: foo"]
    assert body["truncate"] is True
    assert body["normalize"] is True


async def test_embed_query_caches_and_skips_tei_on_repeat():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[[0.01] * 1024])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://tei") as client:
        first = await embed(client, "Foo  Bar", kind="query")
        second = await embed(client, "foo bar", kind="query")

    assert calls == 1
    assert np.array_equal(first, second)


async def test_embed_raises_embed_unavailable_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("hang", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://tei") as client:
        with pytest.raises(EmbedUnavailable):
            await embed(client, "foo", kind="query")


async def test_embed_raises_embed_unavailable_on_tei_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="overloaded")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://tei") as client:
        with pytest.raises(EmbedUnavailable):
            await embed(client, "foo", kind="query")
