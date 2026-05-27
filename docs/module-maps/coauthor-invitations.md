# Module Map: Coauthor invitations (invite, accept/decline, in-app fan-out)

## Source

PRD: [Issue #48 — Coauthor invitations: invite, accept/decline, in-app notifications](https://github.com/LucasACH/buscasam/issues/48).

Materializes the second half of co-authorship: the publish-time fan-out that document-publication.md left as a no-op stub, the invitee accept/decline state transitions ADR-0010 §5 named but never wired, the recipient-scoped pre-acceptance disclosure ADR-0010 §6 carved out but never produced, the owner's CoauthorsPanel on `/mis-trabajos/{id}/editar`, and the inline accept/decline affordance on `CoauthorInviteItem`. Lands one new chokepoint module (`api/coauthor_invitations`) and one new access adapter (`core/document_access.pending_invitation_disclosure_where`); grows `core/documents` with four lifecycle methods and the pending-invitation read helper; fills `core/jobs.fan_out_coauthor_invites`.

## Modules

### `api/coauthor_invitations` (FastAPI router) — new

**Interface:**

```
POST   /api/coauthor_invitations/{doc_id}/accept   → 204 | 404   (require_authenticated)
POST   /api/coauthor_invitations/{doc_id}/decline  → 204 | 404   (require_authenticated)
```

Both endpoints take the doc id from the URL and the invitee from `current_user.user_id`. They delegate to `core/documents.accept_invitation` / `core/documents.decline_invitation`; each returns `None` for "no `pending` row for `(doc_id, user_id)`" (covers idempotent re-submit, owner-revoked-while-deciding, soft-deleted, moderation-hidden, and never-invited cases per PRD stories 20-22, 32-33), which the router maps to a uniform 404 — same envelope as `api/docs`. On 204 the response body is empty; the frontend invalidates the bandeja query and the `/docs/{id}` query on its own. No GET surface — the invitee never lists "my invitations" outside the bandeja; the bandeja and `/docs/{id}` are the two access surfaces, both fed by paths owned elsewhere (notifications + `api/docs`). Origin-checked by middleware (ADR-0005 §15).

**Responsibilities:** HTTP/URL edge for the two invitee-side mutations. Builds the uniform-404 envelope for every miss path. Never opens transactions; never queries `document_authors` or `notifications` directly. The atomic state transition (flip `document_authors.status`, mark the matching `notifications.read_at`) lives in `core/documents`.

**Seams:** None. Two endpoints, same auth dep, same denial envelope, same single-table-of-truth in `core/documents` — collocating is the obvious shape. Splitting into accept/decline files would force the 404 envelope to re-cross files for no callers' benefit.

**Depth note:** Earns its own router file because invitee-side semantics are categorically distinct from owner-managed `api/documents` (which the invitee has no manageable-where access to) and from reader-only `api/docs` (which never mutates). The deletion test passes: collapsing into `api/docs` would mix mutation into a router whose single-purpose contract is the uniform-404 reader envelope; collapsing into `api/documents` would force every owner-only dep there to allow invitees through. One file makes the invitee surface auditable.

---

### `components/CoauthorsPanel.tsx` — new

**Interface:**

```ts
type Props = { docId: number };
```

Consumes `useCoauthors(docId)`. Returns `null` if `!isOwner` (the hook surfaces the server's `is_owner` projection). Otherwise renders a header "Coautores" and:

- One row per coauthor: `display_name · email_local` (when registered) and a status pill (`Pendiente` / `Aceptado` / `Rechazado`). The `owner` row is rendered first and labelled `Vos` with no pill.
- Per-row "Quitar" button **only on `Pendiente` rows** (PRD stories 6, 8). Click → `revoke(userId)` from the hook. `Aceptado` and `Rechazado` rows have no Quitar affordance at all (not a disabled button — a missing one, since the rule is anchored in ADR-0010 §5 sticky-decline + MVP no-self-removal).
- Add-coauthor affordance at the bottom: `<CoauthorPicker value={[]} onChange={selected => selected.forEach(invite)} />` — reuses the picker from document-publication.md. The picker's existing exclude-self rule stands; this panel additionally filters its `onChange` payload against already-listed `user_id`s (Pendiente/Aceptado/Rechazado) so a re-invite of an existing row never round-trips to the server. Inline error surfaces hook mutation failures (e.g., a 409 from a race with another tab).

External-attribution rows (`status='external'`) render the `display_name` but no status pill and no actions — they are name-only per ADR-0010 §5 and out of scope for this PRD's invitation flow.

**Responsibilities:** The owner-only coauthor management view: list + status pills + per-row Quitar gating + invite affordance + the "filter already-invited from picker results" rule. Spanish copy lives here. Mutation requests, query invalidation, polling cadence, and the `is_owner` gate are owned by `useCoauthors`.

**Seams:** None.

**Depth note:** Concentrates the Quitar-on-Pendiente-only rule and the already-invited filter inside one component file, where a future contributor adding e.g. a bulk-invite affordance cannot accidentally re-enable Quitar on Aceptado rows. Deletion test: scattering the four status/action variants across the page would re-cross the panel's only-load-bearing rules — sticky decline (no re-invite path) and pending-only revoke — both of which are PRD acceptance criteria.

---

### `components/CoauthorInvitationBanner.tsx` — new

**Interface:**

```ts
type Props = {
  docId: number;
  titulo: string;
  inviter: string;   // display name of the user who created the pending row
  variant: "minimal" | "banner";
};
```

Renders a card containing título, inviter, and two buttons (`Aceptar`, `Rechazar`) wired to `useCoauthorInvitation()`. The `variant` prop controls layout only:

- `"minimal"` — used when `/docs/{id}` returned the minimal-only payload (privado document, requester is a pending invitee, normal `readable_where` denied access). The banner is the entire page content below the header; no metadata, no abstract, no archivo, no adjuntos, no related (PRD story 15).
- `"banner"` — used when `/docs/{id}` returned the normal detail payload AND a pending invitation. Rendered as a strip above the metadata block; the rest of the detail view is unchanged (PRD stories 16, 17).

After a successful accept or decline the banner unmounts (the page refetches `useDocDetail`; on accept the payload widens to the full reader view, on decline the page transitions to the `is404` empty state — same 404 envelope as any other unauthorized read per PRD story 19).

**Responsibilities:** The único visual contract for "you are pending on this document". Owns the two-button render, the Spanish copy ("X te invitó como coautor en Y. ¿Aceptar o rechazar?"), the layout-only variant switch, and the post-mutation behaviour (the hook handles cache invalidation; the banner just disappears).

**Seams:** None. The variant prop is internal layout, not a seam (no adapter implementing a contract).

**Depth note:** One file owns the only two surfaces where an invitee acts on `/docs/{id}` (the privado minimal-only render and the interno/público layered banner). Deletion test: inlining the two renders into `app/docs/[id]/page.tsx` would duplicate the title/inviter/CTA render + the post-mutation routing, and the next contributor touching one variant would predictably forget the other (PRD acceptance: both variants must show the same buttons wired to the same mutation).

---

### `lib/useCoauthorInvitation.ts` (invitee hook) — new

**Interface:**

```ts
useCoauthorInvitation() -> {
  accept(docId: number): Promise<InvitationMutationError | undefined>;
  decline(docId: number): Promise<InvitationMutationError | undefined>;
}

type InvitationMutationError =
  | { kind: "gone" }     // 404: row no longer pending (idempotent re-submit, revoked, soft-deleted)
  | { kind: "network" };
```

Two mutations against `POST /api/coauthor_invitations/{docId}/accept|decline`. On success, invalidates `["bandeja"]` (so the bandeja item transitions to read state per PRD story 23) and `["doc-detail", docId]` (so `/docs/{id}` refetches — full reader view on accept, 404 envelope on decline). On 404, returns `{ kind: "gone" }` without retrying; the calling surface decides whether to render an inline "ya respondiste a esta invitación" message or simply re-render with the refreshed cache. Network errors return `{ kind: "network" }`.

**Responsibilities:** Mutation request shape, query-key invalidation across the two surfaces that host the action (bandeja + `/docs/{id}` minimal/banner). Does not own polling — neither the bandeja nor the detail page polls; both refetch on invalidation. Stateless hook (no internal state); consumers (`CoauthorInviteItem`, `CoauthorInvitationBanner`) own per-button loading/disable state if they want it.

**Seams:** None.

**Depth note:** Earns its own file because two callers in scope (`CoauthorInviteItem` and `CoauthorInvitationBanner`) drive the same mutation pair, and the invalidation-of-both-query-keys rule must stay in one place — a contributor touching only one caller cannot accidentally drop one of the two invalidations. Deletion test: inlining the invalidation into the components would predictably diverge (bandeja invalidates bandeja-only; banner invalidates detail-only; the "X accepts in bandeja, then opens /docs/{id} in another tab and sees stale 404" bug ships silently).

---

### `app/mis-trabajos/[id]/editar/useCoauthors.ts` (owner hook) — new

**Interface:**

```ts
useCoauthors(docId: number) -> {
  isOwner: boolean;
  coauthors: CoauthorRow[] | undefined;   // includes owner row first; statuses: owner|pending|accepted|declined|external
  isLoading: boolean;
  isError: boolean;
  invite(userId: number): Promise<CoauthorMutationError | undefined>;
  revoke(userId: number): Promise<CoauthorMutationError | undefined>;
}

type CoauthorMutationError =
  | { kind: "already_listed" }   // server saw an existing row for (doc_id, user_id), regardless of status
  | { kind: "forbidden" }        // 403: caller is not owner (defensive — page should not have rendered the panel)
  | { kind: "network" };
```

Reads `coauthors` and `is_owner` from the existing `GET /api/documents/{id}/draft` payload (extended in this PRD — see `core/documents.get_draft_state` below). Shares its TanStack query key with `useDraftState(docId)` and `useDraftAttachments(docId)` per document-publication.md, so the panel polls/refreshes-on-focus with the same cadence as the draft view. Mutations call `POST /api/documents/{id}/coauthors` (body: `{ user_id }`) and `DELETE /api/documents/{id}/coauthors/{user_id}`; on success both invalidate the shared draft query so the panel and any sibling pill re-render. The invite mutation surfaces a 409 (server-side already-listed) as `{ kind: "already_listed" }` — the panel already filters CoauthorPicker results, so this is a tab-race fallback.

**Responsibilities:** Request shape, query-key sharing with the draft view, raw-DTO-to-row projection, mutation invalidation, `is_owner` surfacing. Does not own polling cadence (`useDraftState` owns it); does not own the Quitar-only-on-Pendiente rule (the panel owns it).

**Seams:** None.

**Depth note:** Earns isolation because the panel is the only consumer of the `coauthors` slice of the draft payload, but the share-with-useDraftState invalidation contract is the one rule that ripples into the rest of the /editar page (a metadata save must not blow away the freshly-fetched coauthor list, and an accept arriving from the invitee side must update the panel). Centralizing the shared-key invalidation here keeps the rule auditable. Deletion test: inlining into the panel would scatter the query-key contract across two consumers (page-level useDraftState and the panel), and the "owner edits title → coauthor list disappears because we used a different query key" bug ships silently.

---

### `core/document_access` — touched, gains `pending_invitation_disclosure_where`

**New surface:**

```python
def pending_invitation_disclosure_where(
    alias: str, user_ctx: UserCtx
) -> tuple[str, dict]:
    ...
```

Returns the SQL WHERE-clause body plus its bind params, column-qualified under the caller-supplied alias. Implements ADR-0010 §6 exactly: the source document must be `published` AND `soft_deleted_at IS NULL` AND `moderation_hidden_at IS NULL` AND an `EXISTS (SELECT 1 FROM document_authors da WHERE da.doc_id = <alias>.id AND da.user_id = :user_id AND da.status = 'pending')` row must hold. Returns no row for revoked invitations (the row was deleted), for declined invitations (status moved off pending), for accepted invitations (status moved off pending — those callers go through `readable_where`), or for any document under soft-delete / moderation-hidden lifecycle states.

`user_ctx.user_id` is required by construction; the function raises if called with `GUEST` (invitados cannot be invitees — there is no row to match). Callers must guard or use `require_authenticated` upstream.

**Responsibilities:** Sole owner of the access predicate for the ADR-0010 §6 carve-out. Visibility tier is **not** consulted — the predicate is recipient-scoped, not visibility-scoped (a pending invitee on a privado, interno, or público doc all match the same way). Soft-delete and moderation-hidden filtering are load-bearing: a pending invitee MUST NOT receive a minimal block disclosure for a soft-deleted or hidden document (PRD stories 32-33).

**Seams:** **Real seam, four adapters now.** `invitado_where` (sitemap, anonymous reads), `readable_where` (search, detail, related, current-version download, attachments), `manageable_where` (owner-or-accepted edits, historical-version download), and now `pending_invitation_disclosure_where`. The depth in the seam continues to come from caller count, not adapter count, but the fourth adapter completes the access model the ADR locked.

**Depth note:** The disclosure carve-out is the single most subtle access rule in the corpus (PRD Further Notes: "the most subtle access carve-out"). It is exactly one SELECT predicate; co-locating it with the other three keeps every "can this requester see this row" rule in one file with one architecture-test pattern. Deletion test: inlining the predicate into `core/documents.get_pending_invitation` would scatter access policy across two files for the first time since ADR-0010 — and the soft-delete / moderation-hidden filters would predictably drift between this caller and `readable_where` (they already share those filters today; future moderation-state additions must not have to be added in two places).

---

### `core/documents` — touched, gains four lifecycle methods, `get_pending_invitation`, extended `get_draft_state`

**New surface:**

```python
async def invite_coauthor(
    user_ctx: UserCtx, doc_id: DocId, invitee_user_id: int
) -> None
# Owner-only (raises NotOwner → 403). Inserts a pending document_authors row.
# Raises CoauthorAlreadyListed (→ 409) if a row already exists for (doc_id, user_id)
# regardless of status (covers re-invite-after-decline-attempt per PRD story 10).
# If documents.publication_status='published', enqueues fan_out_coauthor_invites(doc_id)
# inside the same transaction (ADR-0008 §1); for 'draft' the row sits silent until
# the publish-time fan-out (already wired in publish()) picks it up (PRD story 2).

async def revoke_invitation(
    user_ctx: UserCtx, doc_id: DocId, invitee_user_id: int
) -> None
# Owner-only. Pending-only at MVP per ADR-0010 §5: raises CoauthorNotPending (→ 404,
# uniform with not-found) if the row is owner / accepted / declined / missing.
# Atomic SQL: DELETE FROM document_authors WHERE (doc_id, user_id) AND status='pending'
# + DELETE FROM notifications WHERE user_id=invitee AND event_key='coauthor_invite:{doc_id}:{invitee}'
# in one transaction (PRD story 7, Implementation Decisions). The deleted notification row
# clears the bandeja entry so a re-invite later under the same dedup key can insert cleanly
# without an UPSERT (PRD Implementation Decisions, story 29).

async def accept_invitation(user_ctx: UserCtx, doc_id: DocId) -> None
# Invitee-keyed (user comes from user_ctx; no owner needed). Atomic SQL on a pending row
# for (doc_id, user_ctx.user_id) AND documents not soft-deleted, not moderation-hidden,
# published (the readable lifecycle guards): UPDATE document_authors.status='accepted',
# UPDATE notifications.read_at=now() for the matching event_key. Raises
# InvitationNotPending (→ 404) for any miss (already accepted, declined, revoked, never
# invited, doc soft-deleted / hidden — PRD stories 20-22, 32-33).

async def decline_invitation(user_ctx: UserCtx, doc_id: DocId) -> None
# Same shape as accept_invitation; flips to 'declined' instead. Declined is terminal
# (PRD story 10 / ADR-0010 §5); revoke is pending-only, so no return path to pending.

@dataclass(frozen=True)
class InvitationDisclosure:
    doc_id: int
    titulo: str
    inviter_display_name: str

async def get_pending_invitation(
    session: AsyncSession, doc_id: DocId, user_ctx: UserCtx
) -> InvitationDisclosure | None
# Returns the minimal-block payload iff pending_invitation_disclosure_where matches.
# Composes the access adapter; no other module reads document_authors.status='pending'
# for disclosure purposes. Returns None for guests (no user_id) without raising.
# inviter_display_name is sourced from the document_authors row with status='owner'
# joined to users.name.
```

**Extended surface:**

```python
# get_draft_state DTO gains:
#   is_owner: bool
#   coauthors: list[CoauthorRow]
#     where CoauthorRow = (user_id|None, display_name, email_local|None, status)
# Order: owner first, then by document_authors.id (insertion order).
# is_owner is derived server-side: document_authors.status='owner' AND user_id=user_ctx.user_id.
```

Invariants on the four lifecycle methods: every one takes `user_ctx`; owner-side methods (`invite_coauthor`, `revoke_invitation`) apply an owner-only predicate stricter than `manageable_where` (accepted coautores cannot manage coauthors per ADR-0010 §8); invitee-side methods (`accept_invitation`, `decline_invitation`) match on `user_id = user_ctx.user_id` AND the readable lifecycle guards (so a moderation-hidden or soft-deleted document collapses every state transition to 404, PRD stories 32-33). Idempotency lives at the row level: a re-submitted accept or decline on an already-transitioned row returns 404 because the `status='pending'` predicate no longer matches (PRD story 21). No worker function is added.

**Responsibilities:** Owns every mutation to `document_authors` lifecycle state (invite-time pending row, owner revoke, invitee accept/decline) plus the paired `notifications` row mutation on revoke and on accept/decline. Owns the `get_pending_invitation` read for the ADR-0010 §6 carve-out (composes the access adapter; no SQL repeated in `api/docs`). Owns the `is_owner` projection in the draft state DTO and the coauthor list ride-along. Does not own the fan-out task body — that lives in `core/jobs`. Does not own the `core/notifications` interface (no such module per PRD Implementation Decisions); the inline DELETE/UPDATE of `notifications` is the same pattern `core/documents.mark_failed` already uses for `processing_failed`.

**Seams:** None added. The single domain chokepoint rule from document-publication.md stands. Splitting accept/decline into a `core/coauthorship` module was considered and rejected — the atomic `document_authors + notifications` writes share their transaction surface with the publish path (which also writes `document_authors` via `create_draft`), and the readable-lifecycle guards reuse the same predicates `readable_where` already encodes.

**Depth note:** The atomicity rules concentrate here: (a) revoke's joint DELETE so a re-invite under the same dedup key works (PRD Implementation Decisions, story 29), (b) accept/decline's status flip + notification mark-read in one transaction (so a half-applied transition cannot leak a bandeja item pointing at an `accepted` row), (c) the readable-lifecycle guards on every transition (so a moderation-hidden doc cannot have its acceptance ratified). Deletion test: any one of these spread to the router or to a sibling module risks the exact bug the dedup-index / sticky-decline / no-zombie-acceptance acceptance tests are written to catch.

---

### `core/jobs` — touched, fills `fan_out_coauthor_invites` task body

**New task body (the `enqueue_fan_out_coauthor_invites` helper already exists per ADR-0008 §3 / document-publication.md; this PRD fills the worker side):**

```python
@task(queue="default", retry=...)
async def fan_out_coauthor_invites(doc_id: int) -> None:
    # SELECT document_authors rows for doc_id where status='pending' AND user_id IS NOT NULL,
    # join users.name and documents.title and the owner row for inviter_display_name.
    # For each row, INSERT INTO notifications (user_id, event_key, kind, payload_json)
    # VALUES (...) ON CONFLICT (user_id, event_key) DO NOTHING.
    # event_key = f"coauthor_invite:{doc_id}:{user_id}".
    # kind = "coauthor_invite".
    # payload_json = {"doc_title": ..., "doc_id": ..., "inviter": <owner display name>}.
```

Invariants: queueing/execution locks are `coauthors:d{doc_id}` per ADR-0008 §7 (unchanged from the stub's helper). `ON CONFLICT DO NOTHING` against the existing unique index on `notifications(user_id, event_key)` (ADR-0010 §9) is the only idempotency mechanism — application code does not bookkeep "already sent". The task body re-runs the SELECT on every invocation, so retries after partial completion produce zero duplicate rows and zero new rows for already-notified invitees (PRD story 27, Testing Decisions: fan-out idempotency). Caller contract: `core/documents.publish` enqueues once at first publish; `core/documents.invite_coauthor` enqueues once for post-publish invites (same task, same lock key, same dedup — a single new invite simply produces one new notification row and no duplicates). Retry policy per ADR-0008 §5 (3 attempts, exponential 60s base, terminal action = operator log; the owner-side notification on full failure is out of scope at MVP per PRD Out of Scope).

**Responsibilities:** The single concentration of "publish-time and post-publish invite fan-out → in-app notification rows". Owns the SELECT-and-insert SQL, the payload shape, the dedup-key format, and the `coauthor_invite` notification `kind` (already enumerated in ADR-0010 §9 and rendered in `components/NotificationItem` — this PRD is the first producer).

**Seams:** None. Procrastinate boundary unchanged; `feature code never imports procrastinate` (ADR-0008 §3).

**Depth note:** The dedup key format and the `ON CONFLICT DO NOTHING` shape concentrate here, where any future retry-correctness fix lands in one place. Deletion test: spreading the dedup contract across `core/documents.invite_coauthor` (single-invite send) and `core/documents.publish` (fan-out enqueue) would force both call sites to encode the `coauthor_invite:{doc_id}:{user_id}` format, and the next contributor adding e.g. an "invite by email_local" affordance would predictably drift one. ADR-0008 §3 locks all task bodies in `core/jobs`; this PRD just fills one stub.

---

### `api/documents` — touched, gains coauthor invite/revoke endpoints, extends `/draft` payload

**New endpoints:**

```
POST   /api/documents/{id}/coauthors                  → 204 / 403 / 404 / 409   (require_authenticated, manageable, owner-only)
DELETE /api/documents/{id}/coauthors/{user_id}        → 204 / 403 / 404         (require_authenticated, manageable, owner-only)
```

`POST` body is `{ user_id: int }`. Delegates to `core/documents.invite_coauthor`. 409 surfaces `CoauthorAlreadyListed` (a row for `(doc_id, user_id)` exists regardless of status — covers the "re-invite a declined user" attempt that the PRD explicitly forbids per story 10 / ADR-0010 §5). `DELETE` delegates to `core/documents.revoke_invitation`; `CoauthorNotPending` returns 404 (uniform with not-found — no leak about "this row exists but is accepted").

Both endpoints require the caller to be the document's owner. Owner-only is enforced inside `core/documents`; the router maps `NotOwner` to 403 (not 404) because the caller IS authorized to manage the document generally — they are already past `manageable_where` and arrived at `/editar`; gating the panel rendering by `is_owner` upstream prevents the panel from issuing forbidden requests in the normal case, so 403 is informational rather than a leakage signal.

**Extended `GET /api/documents/{id}/draft` DTO:**

```python
class DraftStateDTO:
    # ... existing fields ...
    is_owner: bool
    coauthors: list[CoauthorRowDTO]
```

No new endpoint for the coauthor list — it rides on the existing draft polling channel so `useCoauthors` shares cadence and invalidation with `useDraftState` per the PRD's "shares TanStack Query keys with useDraftState" wording.

**Responsibilities:** HTTP/URL contract for owner-side coauthor mutations. The router does NOT own the joint document-authors + notifications transaction (lives in `core/documents.revoke_invitation`); it does NOT own the post-publish enqueue (lives in `core/documents.invite_coauthor`). Maps the three core exceptions (`NotOwner` → 403, `CoauthorAlreadyListed` → 409, `CoauthorNotPending` → 404) to HTTP semantics. Extends the draft DTO shape only.

**Seams:** None. The two new endpoints share auth/manageable/owner-only dep set with the existing draft endpoints; collocating per document-publication.md's "earn extraction with a second caller" rule keeps the router cohesive.

**Depth note:** Thin by design. The policy bundle (owner-only, sticky-decline, atomic revoke) lives in `core/documents`; the router shapes HTTP. Splitting into `api/coauthors` was considered and rejected — these two endpoints are document-scoped owner mutations and share the `manageable` dep tree, while `api/coauthor_invitations` (invitee-side) lives separately precisely because its dep set, its mapping conventions (uniform 404), and its caller perspective differ.

---

### `api/docs` — touched, GET /api/docs/{id} second-try composition for pending-invitee disclosure

**Extended behaviour on `GET /api/docs/{id}`:**

```
1. Call core/documents.get_detail(doc_id, user_ctx).
2. If user_ctx.user_id is not None, call core/documents.get_pending_invitation(doc_id, user_ctx).
3. Compose:
     (detail=Some, invite=None)    → 200, normal DetailDTO.
     (detail=Some, invite=Some)    → 200, DetailDTO with invitation banner field populated.
     (detail=None, invite=Some)    → 200, MinimalInviteDTO (titulo + inviter + doc_id only).
     (detail=None, invite=None)    → 404, uniform envelope.
```

The response shape becomes a discriminated union (or a single DTO with a `view: "detail" | "minimal" | "detail_with_invitation"` tag and conditionally-populated fields — implementation choice in the FastAPI router, both are valid Pydantic v2 patterns). The two other reader endpoints (`/related`, `/download`, `/attachments/{att_id}`, `/versions/{n}/download`) are **unchanged** — pending invitees do NOT gain access to related, downloads, or attachments per PRD story 25 / ADR-0010 §6. The disclosure carve-out is bounded to the single `/api/docs/{id}` route.

For invitados (`user_ctx.user_id is None`), step 2 is skipped — invitados cannot be invitees, and `get_pending_invitation` already returns `None` for guests but the router skips the call to avoid a wasted query on the hot anonymous-read path.

**Responsibilities:** Owns the composition order (detail first, invitation second) and the union return shape. The "consult invitation only when authenticated" micro-optimization is also owned here. The denial envelope is unchanged.

**Seams:** None added. The five reader endpoints continue to share auth, the 404 envelope, and the X-Accel-Redirect projection.

**Depth note:** The composition logic is small but security-load-bearing: the order is detail-first because `get_detail` is the hot path for accepted readers (the overwhelming majority), and `get_pending_invitation` is a second SELECT only when needed (or for the invitation-on-top variants). Reversing the order would not be wrong, but the chosen order is auditable as "the carve-out is a second-try, not the primary path". Deletion test: inlining the disclosure SQL in the router instead of calling `core/documents.get_pending_invitation` would scatter the access predicate across two files (router + `core/document_access`), violating ADR-0010 §6's chokepoint rule.

---

### `components/NotificationItem` (`CoauthorInviteItem` branch) — touched, inline accept/decline buttons

**Extended `CoauthorInviteItem`:**

```ts
function CoauthorInviteItem({ item, payload }: { item: NotificationDTO; payload: CoauthorInvite }) {
  // existing render: "<inviter> te invitó como coautor en <Title>".
  // NEW: two buttons "Aceptar" / "Rechazar" wired to useCoauthorInvitation().
  // NEW: "Ver" link to `/docs/${payload.doc_id}`.
  // After accept/decline mutation returns: the bandeja query invalidates and the
  // notification refetches with read_at != null, so this item renders without
  // buttons on next render (PRD story 23). On 404 (revoked-while-deciding) the
  // bandeja query invalidation drops the item entirely (PRD story 24).
}
```

`payload.doc_id` is read from the existing notifications `payload_json` (produced by the fan-out task body). The pre-existing fallback rendering (when `doc_title` / `inviter` are absent) is preserved — this is still a defensive branch since notifications can in principle carry an older payload shape.

**Responsibilities:** Renders the per-notification actions for `kind='coauthor_invite'`. Does not own the mutation logic (that's `useCoauthorInvitation`); does not own the bandeja list (`useNotifications` already covers list, unread count, mark-read).

**Seams:** None. The `kind` dispatch in `renderBody` remains the single visual-contract chokepoint for notifications.

**Depth note:** The accept/decline-from-bandeja is the PRD's explicit no-extra-navigation affordance (story 13). Co-locating with the rest of the kind dispatch keeps the per-kind UI surface auditable in one file (`components/NotificationItem.tsx` already owns hidden/unhidden/processing-failed); spreading would invite per-kind drift.

---

### `app/mis-trabajos/[id]/editar/page.tsx` — touched, composes CoauthorsPanel

**Change:** Adds `<CoauthorsPanel docId={id} />` to the page composition. The panel is a sibling of the metadata form and `AttachmentsPanel`. No layout-level branching here (the panel returns `null` for non-owners — PRD story 5).

**Responsibilities, seams, depth note:** unchanged from document-publication.md. This is a one-line addition; the panel and its hook own everything visible.

---

### `app/docs/[id]/page.tsx` — touched, branches on the new union payload

**Change:** `useDocDetail(id)` now returns a payload tagged with a `view` discriminator (or equivalent shape). The page renders three branches:

- `view === "minimal"` → render only `<CoauthorInvitationBanner variant="minimal" ... />` plus the page header. No metadata, no abstract, no archivo, no adjuntos, no related rail, no Editar CTA, no VersionsPanel. The `useRelated` and `useVersionDownload` hooks are NOT mounted in this branch (PRD story 15).
- `view === "detail_with_invitation"` → render `<CoauthorInvitationBanner variant="banner" ... />` above the existing metadata block, then the rest of the page unchanged.
- `view === "detail"` → existing rendering, unchanged.

The `is404` branch is unchanged — `useDocDetail` still surfaces 404 from a `(detail=None, invite=None)` server response.

**Responsibilities, seams, depth note:** The page remains the single concentration point for the URL→layout binding. The new branching is exactly the manager-vs-reader-vs-invitee axis that document-detail.md's depth note already anticipated; co-locating with the existing manageable branching keeps the page as the single "what does this requester see at /docs/{id}" decision surface.

---

### `app/docs/[id]/useDocDetail.ts` — touched, accepts the new payload variants

**Change:** The hook's typed return widens from `DetailDTO | undefined` to `(DetailDTO | DetailWithInvitationDTO | MinimalInviteDTO) | undefined`, all sharing a `view` discriminator. The 404-no-retry policy is unchanged; the only semantic change is shape pass-through. Cache invalidation by `useCoauthorInvitation` (after accept/decline) refetches under the same query key and the page re-renders against the new payload (full reader view on accept, 404 envelope on decline).

**Responsibilities, seams, depth note:** Unchanged from document-detail.md. The 404-no-retry rule stays load-bearing; the union widening is a typing change.

---

## Touched, not new

- **`core/auth.GET /api/users/search`** — unchanged. The owner's CoauthorsPanel reuses the existing typeahead endpoint (PRD #25, document-publication.md). No new endpoint.
- **`components/CoauthorPicker`** — unchanged. The panel passes the existing component with `value={[]}` and consumes its `onChange` to drive individual `invite(userId)` calls; the "filter already-invited" rule lives in the panel (which has the row list), not in the picker.
- **`components/BandejaPanel`** / **`lib/useNotifications`** — unchanged. The bandeja list, unread count, mark-as-read, and per-kind dispatch are all already in place; this PRD only changes what `CoauthorInviteItem` renders inside the dispatch.
- **`lib/useDraftState`** / **`lib/useDraftAttachments`** — unchanged. The new `useCoauthors` hook shares their query key so a draft poll refreshes the coauthor list on the same cadence; no internal change to the existing hooks.
- **`api/notifications`** — unchanged. The PRD's "marks the notification read on accept/decline" is implemented as part of `core/documents.accept_invitation` / `decline_invitation`'s atomic SQL, not via a router call — so no new endpoint is needed and the existing read endpoints continue to serve the bandeja's display state.
- **`document_authors` schema** — unchanged. ADR-0010 §5 already locks the `owner | pending | accepted | declined | external` enum and the two unique indices. This PRD is the first to write `accepted` and `declined`.
- **`notifications` schema** — unchanged. The unique index on `(user_id, event_key)` from ADR-0010 §9 is the dedup mechanism; this PRD is the first producer for `kind='coauthor_invite'`.

## Dependency graph

```
                                                       app/docs/[id]/page.tsx
                                                       /        |        \
                                            useDocDetail   CoauthorInvitationBanner   (existing
                                                |                  |                    detail
                                                |                  |                    children:
                                                |          useCoauthorInvitation        useRelated,
                                                |                  |                    VersionsPanel,
                                                |                  |                    ResultCard)
                                                |                  |
                                       GET /api/docs/{id}    POST /api/coauthor_invitations/{doc_id}/accept|decline
                                                |                  |
                                                |                  └────────── components/NotificationItem (CoauthorInviteItem branch)
                                                |                                          ↑
                                                |                                          | (same hook, both surfaces)
                                                |
                                            api/docs
                                          /         \
                       core/documents.get_detail   core/documents.get_pending_invitation
                                                                    |
                                                  core/document_access.pending_invitation_disclosure_where
                                                                    |
                                                      (Postgres: documents, document_authors,
                                                                  users)

                       app/mis-trabajos/[id]/editar/page.tsx
                                            |
                                  CoauthorsPanel (new)
                                            |
                                    useCoauthors (new, shares query key with useDraftState)
                                            |
                       GET /api/documents/{id}/draft  (extended payload: is_owner, coauthors[])
                       POST /api/documents/{id}/coauthors
                       DELETE /api/documents/{id}/coauthors/{user_id}
                                            |
                                       api/documents
                                            |
                                    core/documents
                                       /       |       \
                              invite_coauthor  revoke_invitation  get_draft_state (extended)
                                     |                |
                                     |                └── DELETE notifications WHERE event_key=…
                                     |                    (atomic with document_authors DELETE)
                                     |
                            enqueue fan_out_coauthor_invites (transactional, ADR-0008 §1)
                                     |
                                core/jobs
                                     |
                       fan_out_coauthor_invites task (queue=default, lock=coauthors:d{id})
                                     |
                       INSERT notifications (kind='coauthor_invite',
                                             event_key='coauthor_invite:{doc_id}:{user_id}')
                                ON CONFLICT (user_id, event_key) DO NOTHING

                       (invitee response — already drawn above)
                       POST /api/coauthor_invitations/{doc_id}/accept|decline
                                     |
                              api/coauthor_invitations
                                     |
                       core/documents.accept_invitation | decline_invitation
                                     |
                  Atomic SQL: UPDATE document_authors.status + UPDATE notifications.read_at
```

No cycles. `core/jobs.fan_out_coauthor_invites` reads `document_authors` and writes `notifications` directly — it does not call back into `core/documents` because it has no domain row to mutate beyond the notifications insert (parallels the inline-SQL pattern `core/documents.mark_failed` already uses). `core/documents` enqueues into `core/jobs` for fan-out (both at publish via the existing call and at post-publish invite via the new `invite_coauthor` branch); `core/jobs` does not enqueue back. `api/coauthor_invitations` and `api/documents` both depend on `core/documents`; `api/docs` depends on `core/documents` (`get_detail` + `get_pending_invitation`); no router depends on another router. Frontend talks to FastAPI only through the typed OpenAPI client (ADR-0004 §6); no Server Components on either `/docs/[id]` or `/mis-trabajos/{id}/editar` (ADR-0004 §3).

## Out of scope

- **Email delivery for invitations** — PRD §"Out of Scope"; SPEC deviation tracked in PRD's *Further Notes*. No `core/email`, no SMTP transport, no `send_coauthor_invite` task body. The `enqueue_send_coauthor_invite` helper from ADR-0008 §3 either stays as a no-op stub or is removed in this PRD's implementation commit (the choice is deferred per PRD Further Notes; the module map does not prescribe).
- **Owner notifications on accept/decline** — no `coauthor_accepted` / `coauthor_declined` notification kinds. CoauthorsPanel surfaces status via the draft polling channel (PRD §"Out of Scope").
- **Self-removal of accepted coauthors** — `accepted` is permanent at MVP; revoke is pending-only (PRD §"Out of Scope" + ADR-0010 §5).
- **Re-invite of declined users** — `declined` is terminal; the `CoauthorAlreadyListed → 409` mapping in `invite_coauthor` blocks the attempt server-side (PRD story 10 + ADR-0010 §5).
- **Dedicated `/invitaciones/{id}/responder` page** — rejected. Bandeja-inline + `/docs/{id}` minimal banner are the only response surfaces.
- **Coauthor invite for external (non-registered) authors** — external attribution is text-only per ADR-0010 §5; no row, no notification, no flow.
- **Invitation expiry** — pending invitations do not expire at MVP (PRD §"Out of Scope").
- **Bulk invite operations** — owner invites one user at a time via `CoauthorPicker`.
- **Cross-document invitation digest** — each invitation is its own bandeja row (PRD story 37).
- **`core/notifications` domain module** — rejected per PRD §"Implementation Decisions" (already rejected in auth-sessions.md). The new notification producers (fan-out task body, accept/decline read-mark, revoke joint delete) all use inline SQL, paralleling `core/documents.mark_failed`. Three call sites do not yet earn extraction; the existing `api/notifications` router stays inline.
- **`core/coauthorship` separate domain module** — rejected. The `document_authors` lifecycle is one slice of the document domain; the atomic transactions (revoke + dedup-row delete, accept/decline + notification mark) reuse `core/documents`'s readable-lifecycle predicates and would re-cross any split boundary on every call.
- **Separate `useInviteCoauthor` / `useRevokeCoauthor` hooks** — rejected. The two owner mutations share TanStack invalidation and a single error-mapping contract (`CoauthorMutationError`); splitting would scatter the shared-query-key rule for no caller's benefit (`CoauthorsPanel` is the only consumer).
- **Separate `api/invitations` router for the disclosure read** — rejected. The minimal-invite disclosure is a variant of `GET /api/docs/{id}`, not a new endpoint; per ADR-0010 §6 the disclosure rides on the existing detail URL.
- **Server-rendered `/docs/{id}` for the minimal-invite variant (SSR / Open Graph)** — out per PRD §"Testing Decisions" (CSR-only per ADR-0004 §3).
- **Real email transport tests / SMTP fakes** — PRD §"Testing Decisions" anti-scope; no `core/email` exists.
- **Probing `send_coauthor_invite` task in tests** — PRD §"Testing Decisions" anti-scope; the helper is a stub or removed.
- **`api/users` separate router** — still not relevant (CoauthorPicker already calls `GET /api/users/search` on `api/auth` per document-publication.md).
- **Profile links for coautores on `/docs/{id}`** — out of MVP per document-detail.md; this PRD does not change the autores rendering on the detail page beyond the new banner.

## Further Notes

- **The dedup-key contract is the single load-bearing format in this slice.** Every producer and every consumer encodes `coauthor_invite:{doc_id}:{user_id}` — the fan-out task body inserts, `core/documents.revoke_invitation` deletes, and `core/documents.accept_invitation` / `decline_invitation` mark-read all key off this format. A future contributor changing the format must edit four call sites; the format string ideally lives as a single constant in `core/jobs` (e.g., `def _coauthor_invite_event_key(doc_id, user_id) -> str`) reused by `core/documents`. Module-map decision: the constant lives in `core/jobs` because that is the producer and is already the chokepoint ADR-0008 §3 locks for task contracts.
- **`pending_invitation_disclosure_where` is the first access predicate with no visibility tier.** Unlike `readable_where` (which encodes the público / interno / privado axis) and `manageable_where` (which encodes the owner-or-accepted axis), the disclosure predicate is purely recipient-scoped — the same pending invitee gets the minimal-block carve-out on a privado, interno, or público document. The visibility tier only affects what the router composes around the banner (minimal-only vs banner-on-top), not what the predicate matches. This is exactly what ADR-0010 §6 prescribes and what makes the carve-out "the most subtle" in the corpus.
- **The accept-decline atomic transaction includes the `notifications` UPDATE.** This is a small departure from `mark_failed`'s pattern (which only inserts the notification, never updates one), but it is the simplest way to honour PRD story 23 (bandeja stops showing buttons after a response) without a second round-trip from the router. The matching `event_key` is the lookup; if no notification row exists (e.g., the invitee accepted before the fan-out actually ran — a near-impossible race the unique-index DEFER doesn't allow), the UPDATE is a no-op and the status flip still succeeds.
- **`get_draft_state`'s extension to include coauthors[]** is the second time the draft polling channel has grown (the first was the staged-metadata fields in document-publication.md). The channel is now the management-side view of the document, and `useCoauthors` shares the same query key with `useDraftState` and `useDraftAttachments` so all three views refresh on the same cadence. A future fourth grower (e.g., comment counts in PRD #14 if it lands) should follow the same pattern; if the payload size grows substantially, a per-field `If-None-Match` or a separate channel can be carved out then.
- **The minimal-only vs banner-on-top split lives in the router, not in the frontend.** The server returns a discriminator (`view`) and the page picks the layout. This keeps the access logic (was-readable + has-pending-invitation) inside `core/documents` and `core/document_access` where ADR-0010 §6 puts it; the frontend just renders what the server says it can see. A client-side decision (e.g., "if I have an invitation banner, suppress the detail content for privado") would re-encode the access policy and predictably drift from the server's predicate.
- **`api/coauthor_invitations` does not have a GET surface, and this is load-bearing.** The bandeja already lists invitations (via `kind='coauthor_invite'` notifications) and `/api/docs/{id}` already exposes the minimal block; a third "list my invitations" surface would re-encode the disclosure scope and risk drifting from the recipient-scoped rule. The decision is recorded in *Out of scope* above as well.
- **Full interface-level wiring for the implementation slice** is the next document this PRD produces (a /to-issues split, likely). The module map's job is the anchor; the per-issue PRs reference back to it for the shape contract.
