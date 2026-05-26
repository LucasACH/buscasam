"""Text extraction and metadata derivation (ADR-0007). Full pipeline lands in slice #3.

probe_encrypted ships in slice #2 as a synchronous stub.
"""
from __future__ import annotations


class PDFEncryptionError(Exception):
    pass


def probe_encrypted(head_bytes: bytes) -> None:
    """Raises PDFEncryptionError if head_bytes indicate a password-protected PDF."""
    if b"/Encrypt" in head_bytes:
        raise PDFEncryptionError("PDF is password-protected")
