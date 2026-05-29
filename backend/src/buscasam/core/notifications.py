"""Notification production: the single concentration of event-key format,
notification kinds, payload shape, and the idempotent insert for the one
`notifications` table (ADR-0010 §9).

Consolidates what was hand-written across `core/jobs` (coauthor fan-out),
`core/documents` (indexing + headline-refresh failure), and `core/moderation`
(hide/unhide). One concrete table — no producer-adapter seam. Each producer
keeps its own "who/when to notify" domain query and calls one `notify_*`
helper, which owns the `(event_key, kind, payload_json) ON CONFLICT DO NOTHING`
shape so those three cannot drift across producers.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Notification kinds (ADR-0010 §9). The frontend renders one branch per kind in
# components/NotificationItem; a new kind here needs a new branch there.
COAUTHOR_INVITE = "coauthor_invite"
PROCESSING_FAILED = "processing_failed"
DOCUMENT_HIDDEN = "document_hidden"
DOCUMENT_UNHIDDEN = "document_unhidden"


def coauthor_invite_event_key(doc_id: int, user_id: int) -> str:
    """Per-recipient dedup key for coauthor-invite notifications. The single
    format shared by the producer (`core/jobs` fan-out inserts under it) and the
    consumers (`core/documents.revoke_invitation` deletes it,
    `accept_invitation`/`decline_invitation` mark it read)."""
    return f"coauthor_invite:{doc_id}:{user_id}"


async def _insert(
    session: AsyncSession,
    *,
    user_id: int,
    event_key: str,
    kind: str,
    payload: dict,
) -> None:
    """The idempotent insert shape, owned in one place. The unique
    `(user_id, event_key)` index is the only dedup mechanism (ADR-0010 §9), so a
    retried producer adds zero duplicate rows."""
    await session.execute(
        text(
            "INSERT INTO notifications (user_id, event_key, kind, payload_json) "
            "VALUES (:uid, :ek, :kind, cast(:payload as jsonb)) "
            "ON CONFLICT (user_id, event_key) DO NOTHING"
        ),
        {"uid": user_id, "ek": event_key, "kind": kind, "payload": json.dumps(payload)},
    )


async def notify_coauthor_invite(
    session: AsyncSession,
    *,
    user_id: int,
    doc_id: int,
    doc_title: str,
    inviter: str,
) -> None:
    await _insert(
        session,
        user_id=user_id,
        event_key=coauthor_invite_event_key(doc_id, user_id),
        kind=COAUTHOR_INVITE,
        payload={"doc_title": doc_title, "doc_id": doc_id, "inviter": inviter},
    )


async def notify_indexing_failed(
    session: AsyncSession,
    *,
    user_id: int,
    doc_id: int,
    version_id: int,
    error: str,
) -> None:
    await _insert(
        session,
        user_id=user_id,
        event_key=f"processing_failed:{version_id}",
        kind=PROCESSING_FAILED,
        payload={"doc_id": doc_id, "version_id": version_id, "error": error},
    )


async def notify_headline_refresh_failed(
    session: AsyncSession,
    *,
    user_id: int,
    doc_id: int,
    version_id: int,
    error: str,
) -> None:
    """Same kind/payload as indexing failure (the consumer needs no new branch),
    but a distinct event_key prefix so a failed headline refresh and a failed
    body index on the same version are separate bandeja rows."""
    await _insert(
        session,
        user_id=user_id,
        event_key=f"headline_refresh_failed:{version_id}",
        kind=PROCESSING_FAILED,
        payload={"doc_id": doc_id, "version_id": version_id, "error": error},
    )


async def notify_moderation_action(
    session: AsyncSession,
    *,
    user_id: int,
    kind: str,
    action_id: int,
    doc_id: int,
    doc_title: str,
    reason: str | None,
) -> None:
    """Keyed per `moderation_actions` id (`{kind}:{action_id}`) so a retry of the
    same action never double-notifies any recipient. `kind` is one of
    DOCUMENT_HIDDEN / DOCUMENT_UNHIDDEN, chosen by `core/moderation`."""
    await _insert(
        session,
        user_id=user_id,
        event_key=f"{kind}:{action_id}",
        kind=kind,
        payload={"doc_id": doc_id, "doc_title": doc_title, "reason": reason},
    )
