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

# ADR-0002 token budget. multilingual-e5-large is 512 tokens; ~4 chars/token
# leaves headroom for non-ASCII tokenization variance.
MAX_CHUNK_CHARS = 1800
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


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


def _split_oversized(paragraph: str) -> list[str]:
    """ADR-0007 §2: oversized paragraphs split at sentence boundaries.

    Falls back to a hard character cap when no sentence boundary fits.
    """
    if len(paragraph) <= MAX_CHUNK_CHARS:
        return [paragraph]
    pieces: list[str] = []
    sentences = _SENTENCE_BOUNDARY.split(paragraph)
    buf = ""
    for sentence in sentences:
        if not buf:
            buf = sentence
            continue
        candidate = f"{buf} {sentence}"
        if len(candidate) <= MAX_CHUNK_CHARS:
            buf = candidate
        else:
            pieces.append(buf)
            buf = sentence
    if buf:
        pieces.append(buf)
    # If any single sentence still exceeded the cap, hard-split at MAX_CHUNK_CHARS.
    out: list[str] = []
    for p in pieces:
        if len(p) <= MAX_CHUNK_CHARS:
            out.append(p)
            continue
        for i in range(0, len(p), MAX_CHUNK_CHARS):
            out.append(p[i:i + MAX_CHUNK_CHARS])
    return out


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
    pieces: list[str] = []
    for p in paragraphs:
        pieces.extend(_split_oversized(p))
    return [
        Chunk(body_text=p, is_headline=False, chunk_seq=i + 1)
        for i, p in enumerate(pieces)
    ]
