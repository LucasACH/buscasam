"""Domain exceptions for the documents chokepoint (module map §core/documents)."""
from __future__ import annotations


class DocumentNotFound(Exception):
    pass


class InvalidCoauthorId(Exception):
    def __init__(self, ids: set[int]) -> None:
        self.ids = ids


class PublishConflict(Exception):
    """The candidate is not indexed, or its stored headline fingerprint no
    longer matches current title + staged_abstract (→ 409)."""


class NoPublishedVersion(Exception):
    """replace_main_version on a document without a published current version
    (→ 409). The inverse of /upload's initial-publication-only entry state
    (module map §api/documents)."""


class NoCandidateToDiscard(Exception):
    """discard_candidate on a document with no in-flight candidate (→ 404):
    none ever uploaded, or it was already discarded / published (module map
    §core/documents, ADR-0011 §9)."""


class AttachmentCapExceeded(Exception):
    """The document already holds the maximum of 5 attachments (→ 409)."""


class InvitationNotPending(Exception):
    """No `pending` row for `(doc_id, user_id)` on a readable document (→ 404):
    already-transitioned, revoked, never-invited, or the document
    soft-deleted / moderation-hidden / unpublished (PRD stories 20-22, 32-33)."""


class NotOwner(Exception):
    """Caller is not the document's owner (→ 403). Owner-only is stricter than
    manageable_where, which also admits accepted coautores (ADR-0010 §8)."""


class CoauthorAlreadyListed(Exception):
    """A document_authors row already exists for (doc_id, user_id), regardless
    of status (owner | pending | accepted | declined | external) (→ 409).
    Blocks re-invite of a declined user per ADR-0010 §5 / PRD story 10."""


class CoauthorNotPending(Exception):
    """Revoke is pending-only at MVP (ADR-0010 §5). Maps to 404 uniform with
    not-found — no leak about whether a non-pending row exists."""
