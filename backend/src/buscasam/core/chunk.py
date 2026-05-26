"""Chunking + headline fingerprint (module map §core/chunk).

Single source of `headline_fingerprint` so the publish gate, the post-edit
reindex enqueue rule, and the worker all compute the same value without
coordination.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from buscasam.core.extract import ExtractedDoc


@dataclass(frozen=True)
class Chunk:
    body_text: str
    is_headline: bool
    chunk_seq: int


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def headline_fingerprint(title: str, abstract: str) -> str:
    payload = _normalize(title) + "\x00" + _normalize(abstract)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def headline_chunk(title: str, abstract: str) -> Chunk:
    body = f"{title}\n\n{abstract}" if abstract else title
    return Chunk(body_text=body, is_headline=True, chunk_seq=0)


def chunk(doc: ExtractedDoc) -> list[Chunk]:
    if not doc.text:
        return []
    paragraphs: list[str] = []
    start = 0
    for end in doc.paragraph_breaks:
        piece = doc.text[start:end].strip()
        if piece:
            paragraphs.append(piece)
        start = end
    tail = doc.text[start:].strip()
    if tail:
        paragraphs.append(tail)
    if not paragraphs:
        return []
    return [
        Chunk(body_text=p, is_headline=False, chunk_seq=i + 1)
        for i, p in enumerate(paragraphs)
    ]
