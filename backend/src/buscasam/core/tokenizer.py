"""Vendored e5 tokenizer for offline token-budget measurement (ADR-0002 §4/§5).

The chunker measures the full *prefixed* encoded input — `passage: <text>`,
special tokens included — against the e5 512-token budget without contacting
TEI. The vendored `tokenizer.json` is pinned to the same HF revision SHA as the
served model; `manifest.json` records that SHA so startup can verify the pin.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from tokenizers import Tokenizer

_VENDOR_DIR = Path(__file__).parent / "vendor" / "e5_tokenizer"

# ADR-0002 §1: multilingual-e5-large context window.
MAX_TOKENS = 512
# ADR-0002 §3: retrieval prefix the embedder prepends; the budget is measured
# against the same prefixed string the model will see.
_PASSAGE_PREFIX = "passage: "


@lru_cache(maxsize=1)
def _tokenizer() -> Tokenizer:
    return Tokenizer.from_file(str(_VENDOR_DIR / "tokenizer.json"))


def vendored_revision() -> str:
    """HF revision SHA the vendored tokenizer was pinned to (ADR-0002 §5)."""
    manifest = json.loads((_VENDOR_DIR / "manifest.json").read_text())
    return manifest["revision"]


def passage_token_len(text: str) -> int:
    """Encoded length of the prefixed passage, special tokens included."""
    return len(_tokenizer().encode(f"{_PASSAGE_PREFIX}{text}").ids)


def fits(text: str) -> bool:
    return passage_token_len(text) <= MAX_TOKENS
