# Module Map: Report and moderation (report, hide/unhide/dismiss, author notifications)

## Source

PRD: [Issue #73 — Report and moderation flow: report, hide/unhide/dismiss, author notifications](https://github.com/LucasACH/buscasam/issues/73).

Materializes ADR-0010 §9: the `document_reports`/`moderation_actions` tables the ADR named but never wired, the moderation-access carve-out §6 reserved, and the `document_hidden|document_unhidden` notification kinds §9 listed. Lands one new deep domain module (`core/moderation` — sole writer of `documents.moderation_hidden_at`), one new access fragment (`core/document_access.moderation_inspection_where`, the second deliberate reader-policy exception after `pending_invitation_disclosure_where`), one new chokepoint router (`api/moderation`), and the frontend report dialog + Docente queue/inspect views. The per-surface exclusion of hidden documents from search/detail/related/download/sitemap already lives in the `moderation_hidden_at IS NULL` baked into `core/document_access` predicates — this slice only sets/clears that column and asserts the boundary once.

## Modules

### `core/moderation` — new (deep)

**Interface:**

```
file_report(session, user_ctx, doc_id, reason)          -> None   # require_authenticated upstream
    reason ∈ {spam, contenido_inadecuado, plagio, error}
    raises DocumentNotReadable when the doc fails readable_where (router → 404)
    second open report by the same reporter on the same doc = harmless no-op
    (ON CONFLICT on the unique partial index `(doc_id, reporter_user_id) WHERE status='open'`)

list_open_reports(session)                              -> list[QueueEntry]   # require_docente upstream
    one entry per reported document with title, reason(s), first/last reported_at,
    and report count (story 12); ordered for triage

hide(session, docente_ctx, report_id, reason)           -> ActionOutcome | None
unhide(session, docente_ctx, report_id, reason=None)    -> ActionOutcome | None
dismiss(session, docente_ctx, report_id, reason=None)   -> ActionOutcome | None
    None when report_id is unknown or its document is author-soft-deleted (router → 404)
    reason REQUIRED on hide, optional on unhide/dismiss
```

**Invariants:**
- **Sole writer of `documents.moderation_hidden_at`** — `hide` stamps it, `unhide` clears it, nothing else in the request path assigns it (arch test, below). Touches no other `documents` column: not `publication_status`, not `soft_deleted_at`, not `is_current` (stories 24-25).
- All three actions, in **one transaction**: append an append-only `moderation_actions` row (`report_id`, `docente_user_id`, `action`, `reason`, `created_at`) and resolve **all** open reports on the action's document — `dismiss` included (the matter is settled for that document; story 23 read uniformly).
- `hide`/`unhide` insert an in-app notification to **every registered author** (owner + accepted, `user_id NOT NULL`); external authors are skipped. Insert is `ON CONFLICT (user_id, event_key) DO NOTHING`, `event_key = f"{kind}:{action_id}"` keyed per `moderation_actions` id, so a retry of the same action never double-notifies any recipient (story 29). `dismiss` notifies no one (story 28).
- `unhide` clears the column unconditionally given an existing case; re-hiding/re-unhiding leaves no residue beyond the audit log (story 33).

**Responsibilities:** the entire report→queue→act→resolve→notify lifecycle and ownership of the two moderation tables. The event-key format for hide/unhide notifications lives here (the single producer; the consumer is `api/notifications`, which only reads/acks).

**Seams:** none — the reason and action enums are fixed and there is one backend; `hide`/`unhide`/`dismiss` share a private resolve-all-open + audit-append helper but are not a polymorphic seam (one adapter set, no second).

**Depth note:** deletion test passes hard. Remove it and the unique-partial-index no-op, the resolve-all-open transaction, the per-action notification idempotency, and the `moderation_hidden_at` stamp scatter across `api/moderation` and would drift from the readable predicate. Small verb-shaped interface (`file_report`/`hide`/`unhide`/`dismiss`/`list_open_reports`) over the whole moderation state machine.

---

### `core/document_access.moderation_inspection_where` — new fragment in an existing module

**Interface:**

```
moderation_inspection_where(alias, report_id) -> tuple[str, dict]
    WHERE-body + binds selecting the document of report :report_id
    regardless of visibility AND regardless of moderation_hidden_at,
    EXCLUDING soft_deleted_at IS NOT NULL, for ANY report status (open|resolved).
    Bind key :inspect_report_id (distinct from the other fragments' keys).
```

**Responsibilities:** the second deliberate exception to the normal reader policy — **report-scoped, not visibility-scoped** (ADR-0010 §6, §9). A Docente gains no standing access to private documents; access is bounded to the document behind a specific report id (stories 16-17). Inspection succeeds for `open` **and** `resolved` reports — the case record persists so a Docente can re-open detail after acting. Author-soft-deleted documents are excluded so moderation cannot resurrect removed content (story 18). Carries no role check — `require_docente` gates at the router; the predicate is purely the report→document scoping.

**Seams:** none — lives at the same seam as the existing `*_where` fragments.

**Depth note:** mirrors `pending_invitation_disclosure_where` exactly in shape and rationale — keeping it in `core/document_access` concentrates every "what a non-owner may read, and the two carve-outs from it" decision in one file. Deletion test: inline this `EXISTS` into the router and the visibility/hidden/deleted carve-out logic duplicates across the inspect and download endpoints and diverges from the readable predicate it deliberately parallels.

---

### `api/moderation` (FastAPI router) — new

**Interface:**

```
POST /api/moderation/reports                  body {doc_id, reason}   → 204 | 404   (require_authenticated)
GET  /api/moderation/queue                                            → 200 | 403   (require_docente)
GET  /api/moderation/reports/{report_id}/document                     → 200 | 404 | 403   (require_docente)
GET  /api/moderation/reports/{report_id}/download                     → 200 | 404 | 403   (require_docente)
POST /api/moderation/reports/{report_id}/hide     body {reason}       → 204 | 404 | 403   (require_docente)
POST /api/moderation/reports/{report_id}/unhide   body {reason?}      → 204 | 404 | 403   (require_docente)
POST /api/moderation/reports/{report_id}/dismiss  body {reason?}      → 204 | 404 | 403   (require_docente)
```

**Responsibilities:** the HTTP edge. Reporting is keyed by `doc_id` in the body; inspection and all three actions are keyed by `report_id` in the path (the case in front of the Docente). Delegates: filing and acting to `core/moderation`; the `document`/`download` reads compose `moderation_inspection_where(report_id)` (detail metadata + current main-file blob handoff only — no attachments, related, or version history, per anti-scope). Maps every domain miss (`DocumentNotReadable`, unknown report, author-deleted doc, no current version) to a uniform **404** so hidden/private/deleted existence is never disclosed (stories 9, 18); role failures surface as **403** via `require_docente`. Opens no transactions and writes no tables directly — same envelope discipline as `api/coauthor_invitations` and `api/docs`.

**Seams:** none.

**Depth note:** thin by design (an HTTP edge), but it earns its place as the single chokepoint where moderation access is gated — `require_authenticated` for filing, `require_docente` for everything else, and the report-scoped predicate for the two reads. No frontend process queries Postgres (ADR-0010 §6).

---

### Frontend: report dialog + Docente queue/inspect views — new

**Interface (user-facing surfaces, ADR-0004):**
- **`ReportDialog`** on the document detail page — a "Reportar" affordance rendered only for authenticated users (invitado sees nothing; story 7), four reasons, `POST /api/moderation/reports`, confirmation on success, silent on the duplicate no-op.
- **Moderation queue page** (Docente-only nav) — renders `GET /api/moderation/queue`: title, reason, reported-at, multi-reporter count (stories 10-12).
- **Inspect view** (Docente-only) — renders `GET …/document` metadata and links `GET …/download`; exposes the hide/unhide/dismiss actions with the reason field (required on hide).

**Responsibilities:** present the affordances and call the router; gate visibility on the session role client-side as UX (the server is the real gate — non-Docente endpoints already 403).

**Seams:** none.

**Depth note:** presentation only; no policy lives here. Deletion test is N/A (leaf UI), but the role-conditional rendering keeps the affordance contract (auth → report, docente → moderate) in one place per surface.

## Dependency graph

```
frontend (ReportDialog, queue, inspect)  →  api/moderation
api/moderation                           →  core/moderation
api/moderation                           →  core/document_access (moderation_inspection_where)
api/moderation                           →  core/blob_store        (main-file download handoff)
core/moderation                          →  core/document_access (readable_where — gate filing)
core/moderation                          →  notifications table   (in-app hide/unhide insert)
api/notifications  (existing, read-only) →  notifications table   (consumes document_hidden|document_unhidden)
```

No cycles. `core/moderation` depends on `core/document_access` (one direction); `core/document_access` stays leaf. Note `core/moderation` writes the `documents.moderation_hidden_at` column directly rather than routing through `core/documents` — this is the deliberate per-column sole-writer split (below), not a layering violation.

## Architecture guard

The existing sole-writer arch test (`backend/tests/unit/test_documents_writer_architecture.py`) is **per-column, not per-table**: it already enforces that only `core/documents` assigns `soft_deleted_at`. Extend it with a sibling rule — only `core/moderation` may assign `documents.moderation_hidden_at` (`SET … moderation_hidden_at =` or a bootstrap `INSERT INTO documents … moderation_hidden_at`), so the hide/unhide invariant cannot drift across modules (PRD Further Notes). The read predicates (`moderation_hidden_at IS NULL`) in `core/document_access` are not matched (no `=` assignment), exactly as the soft-delete rule already distinguishes.

## Out of scope

- **A separate report-filing module** — rejected; filing is a small insert cohesive with the rest of the `document_reports` lifecycle, so it lives in `core/moderation` (grilled).
- **A polymorphic "act" seam over hide/unhide/dismiss** — rejected; one adapter set, fixed enum, no second adapter (one adapter = hypothetical seam).
- **Routing the `moderation_hidden_at` write through `core/documents`** — rejected; PRD makes `core/moderation` the sole writer of that column, enforced per-column by the arch test.
- **A new notifications producer module** — rejected; the hide/unhide insert reuses the existing inline `INSERT … ON CONFLICT (user_id, event_key)` pattern and the existing `api/notifications` read/ack consumer; only a new `event_key` format (owned by `core/moderation`) is added.
- **Moderator inspection of attachments / related / version history** — anti-scope (PRD); `moderation_inspection_where` backs detail metadata + current main-file download only.
- **Appeals, email notification, general auth/roles, deletion/purge** — owned elsewhere (PRD Out of Scope); this slice consumes existing `require_authenticated`/`require_docente` and asserts moderation-hidden ⟂ soft-deleted at the boundary only.
