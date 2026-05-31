"""Domain chokepoint for all document mutations and queries (ADR-0010 §6, module map §core/documents).

Split by capability into submodules (drafts, versions, indexing, publication,
lifecycle, coauthors, attachments, detail) sharing `_shared` helpers and
`exceptions`. This package is the sole writer of document_versions /
soft_deleted_at (architecture guard). The public surface is re-exported here so
callers keep importing from `buscasam.core.documents`.
"""
from __future__ import annotations

from buscasam.core.documents._shared import (
    UNSET,
    DetailVersion,
    assert_manageable,
)
from buscasam.core.documents.attachments import add_attachment, remove_attachment
from buscasam.core.documents.coauthors import (
    accept_invitation,
    decline_invitation,
    invite_coauthor,
    revoke_invitation,
)
from buscasam.core.documents.detail import (
    Attachment,
    AuthorDisplay,
    DetailRow,
    DownloadableFile,
    InvitationDisclosure,
    MainFile,
    get_detail,
    get_manageable_version_file,
    get_pending_invitation,
    get_readable_attachment,
    get_readable_main_file,
)
from buscasam.core.documents.drafts import (
    AttachmentInfo,
    CandidateState,
    CoauthorRow,
    CoauthorStatus,
    DraftState,
    ExternalAuthor,
    OwnDocSummary,
    create_draft,
    get_draft_state,
    list_own_documents,
    update_draft_metadata,
)
from buscasam.core.documents.exceptions import (
    AttachmentCapExceeded,
    CoauthorAlreadyListed,
    CoauthorNotPending,
    DocumentNotFound,
    InvalidCoauthorId,
    InvitationNotPending,
    NoCandidateToDiscard,
    NoPublishedVersion,
    NotOwner,
    PublishConflict,
)
from buscasam.core.documents.indexing import (
    _begin_indexing,
    mark_failed,
    mark_headline_refresh_failed,
    set_index_stage,
    write_headline,
    write_indexed_candidate,
)
from buscasam.core.documents.lifecycle import (
    DeletedDocSummary,
    list_deleted_documents,
    restore,
    soft_delete,
)
from buscasam.core.documents.publication import publish
from buscasam.core.documents.versions import (
    CandidateVersion,
    attach_main_version,
    discard_candidate,
    load_candidate,
    replace_main_version,
)

__all__ = [
    "UNSET",
    "_begin_indexing",
    "Attachment",
    "AttachmentCapExceeded",
    "AttachmentInfo",
    "AuthorDisplay",
    "CandidateState",
    "CandidateVersion",
    "CoauthorAlreadyListed",
    "CoauthorNotPending",
    "CoauthorRow",
    "CoauthorStatus",
    "DeletedDocSummary",
    "DetailRow",
    "DetailVersion",
    "DocumentNotFound",
    "DownloadableFile",
    "DraftState",
    "ExternalAuthor",
    "InvalidCoauthorId",
    "InvitationDisclosure",
    "InvitationNotPending",
    "MainFile",
    "NoCandidateToDiscard",
    "NoPublishedVersion",
    "NotOwner",
    "OwnDocSummary",
    "PublishConflict",
    "accept_invitation",
    "add_attachment",
    "assert_manageable",
    "attach_main_version",
    "create_draft",
    "decline_invitation",
    "discard_candidate",
    "get_detail",
    "get_draft_state",
    "get_manageable_version_file",
    "get_pending_invitation",
    "get_readable_attachment",
    "get_readable_main_file",
    "invite_coauthor",
    "list_deleted_documents",
    "list_own_documents",
    "load_candidate",
    "mark_failed",
    "mark_headline_refresh_failed",
    "publish",
    "remove_attachment",
    "replace_main_version",
    "restore",
    "revoke_invitation",
    "set_index_stage",
    "soft_delete",
    "update_draft_metadata",
    "write_headline",
    "write_indexed_candidate",
]
