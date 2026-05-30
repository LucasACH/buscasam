"""Chunking + headline fingerprint (module map §core/chunk).

Single source of `headline_fingerprint` so the publish gate, the post-edit
reindex enqueue rule, and the worker all compute the same value without
coordination.

Chunk boundaries are measured against the e5 token budget using the vendored
tokenizer (ADR-0002 §4): every `passage` chunk encodes to `<= 512` tokens with
the `passage:` prefix and special tokens included. Chunking never contacts TEI.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from buscasam.core.extract import ExtractedDoc
from buscasam.core.tokenizer import fits

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
    return Chunk(body_text=_truncate_to_budget(body), is_headline=True, chunk_seq=0)


def _largest_prefix_within_budget(text: str) -> int:
    """Largest character count whose prefixed encoding fits the token budget."""
    lo, hi = 1, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(text[:mid]):
            lo = mid
        else:
            hi = mid - 1
    return lo


def _truncate_to_budget(text: str) -> str:
    """ADR-0002 §7: truncate oversized headline text by the measured rule."""
    if fits(text):
        return text
    return text[: _largest_prefix_within_budget(text)]


def _split_by_chars(text: str) -> list[str]:
    pieces: list[str] = []
    rest = text
    while rest:
        if fits(rest):
            pieces.append(rest)
            break
        cut = _largest_prefix_within_budget(rest)
        pieces.append(rest[:cut])
        rest = rest[cut:]
    return pieces


def _split_to_budget(text: str) -> list[str]:
    """Split `text` into pieces each encoding to `<= MAX_TOKENS` (measured)."""
    if fits(text):
        return [text]
    units = _SENTENCE_BOUNDARY.split(text)
    if len(units) == 1:
        units = text.split(" ")
        if len(units) == 1:
            return _split_by_chars(text)
    pieces: list[str] = []
    buf = ""
    for unit in units:
        candidate = unit if not buf else f"{buf} {unit}"
        if fits(candidate):
            buf = candidate
            continue
        if buf:
            pieces.append(buf)
            buf = ""
        if fits(unit):
            buf = unit
        else:
            pieces.extend(_split_to_budget(unit))
    if buf:
        pieces.append(buf)
    return pieces


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
        pieces.extend(_split_to_budget(p))
    return [
        Chunk(body_text=p, is_headline=False, chunk_seq=i + 1)
        for i, p in enumerate(pieces)
    ]
