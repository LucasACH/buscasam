# Module Map: Auth & Sessions (Google UNSAM login, role-derived visibility, in-app bandeja)

## Source

PRD: [Issue #16 — Auth & Sessions: Google UNSAM login, role-derived visibility, in-app bandeja](https://github.com/LucasACH/buscasam/issues/16).

Implements the SPEC §"Usuarios Y Autenticación" slice end-to-end: Google OIDC restricted to UNSAM tenants, role from `hd`, opaque Postgres sessions, the `interno`/`privado` reach into search, and the bandeja popover (table + read API + per-kind rendering shipped now; producers land in PRDs #3 / #5 / #8).

## Modules

### `core/auth`

**Interface:** Single flat module per ADR-0005 §3. Exports:

- `ROLE_BY_HD: Mapping[str, Literal["estudiante", "docente"]]` — frozen.
- `@dataclass(frozen=True) UserCtx(user_id: int | None, is_unsam: bool, role: Literal["estudiante","docente"] | None)` and `GUEST = UserCtx(None, False, None)`.
- `current_user(request) -> UserCtx` — FastAPI dep. Returns `GUEST` on no / invalid / expired `sid`; never raises. Refreshes `last_seen_at` and reissues cookie only when `last_seen_at < now() - 24h`.
- `require_authenticated(user_ctx) -> UserCtx` — 401 if `user_id is None`.
- `require_docente(user_ctx) -> UserCtx` — 403 if `role != "docente"`.
- `begin_login(next_path: str) -> RedirectResponse` — validates `next` (`startswith('/') and not startswith('//')`), mints PKCE verifier + nonce, signs `oauth_state` cookie (HMAC, 10 min TTL), 302 to Google authorize.
- `complete_login(code, state_cookie, state_param) -> RedirectResponse` — exchanges code, validates `email_verified` + `hd`, looks up role, JIT-upserts `users` row by `google_sub`, creates `sessions` row, sets `sid` cookie, 302 to validated `next`. Rejected claims redirect to `/login?error=not_unsam`; no `users` row touched.
- `end_session(user_ctx, sid) -> Response` — deletes `sessions` row, clears cookie.

Invariants: `sid` is 32 random bytes (`secrets.token_bytes(32)`); `expires_at = created_at + 90 days` is immutable; sliding-idle cap is 30 days; cookie is `HttpOnly; Secure; SameSite=Lax; Path=/`; SSR never calls into this module.

**Responsibilities:** OIDC client setup (Authlib + `pydantic-settings` credentials), `hd → role` mapping, `email_verified` enforcement, OAuth state cookie + PKCE, JIT `INSERT ... ON CONFLICT (google_sub) DO UPDATE` for `users`, session lifecycle SQL (`INSERT`, validity check, sliding `UPDATE last_seen_at`, immutable `expires_at`, `DELETE`), `UserCtx` instantiation, and the three deps. Cookie shape and `next` validation live here.

**Seams:** None. Single chokepoint per ADR-0005 §3 is the load-bearing invariant — splitting it would dilute the audit surface. The OIDC sidecar (Google) is reachable only through Authlib, treated as an external boundary, not a project seam.

**Depth note:** The security spine of the app. Deletion test: any leak — `hd` matched by suffix instead of claim, `email_verified` ignored, a session refresh skipped, an unsafe `next` redirect, an `oauth_state` replay — would be tracked back here. ADR-0005 §3 explicitly locks centralization; PRD §28 restates it.

---

### `core/document_access`

**Interface:** Grows alongside the PRD-1 `invitado_where`:

```python
def invitado_where(alias: str) -> str: ...   # PRD-1, unchanged
def readable_where(alias: str, user_ctx: UserCtx) -> tuple[str, dict]: ...   # PRD-2 (this PRD)
```

`readable_where` returns the SQL `WHERE`-clause body plus its bind params (`{"user_id": ..., "is_unsam": ...}`), column-qualified under the caller-supplied `alias`. Implements ADR-0010 §7 exactly: `published AND NOT soft_deleted AND NOT moderation_hidden AND (publico OR (interno AND :is_unsam) OR EXISTS accepted-or-owner author row)`. Invitado callers still use `invitado_where` (sitemap, anonymous paths); authenticated callers route through `readable_where` regardless of role. `pending` invitees are excluded by construction.

**Responsibilities:** Sole owner of "what counts as a readable document," now across all three visibility tiers and the co-author predicate. Visibility, publication state, soft-delete, moderation-hidden, and authorship are joined into one fragment so search, recientes ordering, detail, related, and sitemap reuse identical semantics.

**Seams:** **Real seam now.** Two adapters in scope: `invitado_where` (sitemap, anonymous read paths) and `readable_where` (search, detail, related). The conceptual seam flagged in the search-mvp map is materialized.

**Depth note:** The central security predicate of the corpus. Deletion test: every MVP visibility leak — invitado seeing `interno`, a `pending` coauthor pre-acquiring access, a hidden doc surfacing in search — would scatter into per-endpoint hand-rolled SQL. ADR-0010 §6 locks this as the chokepoint for every document-derived read.

---

### `api/auth` (FastAPI router)

**Interface:**

- `GET /api/auth/login?next=<path>` → `core/auth.begin_login(next)`. No session required.
- `GET /api/auth/google/callback?code=&state=` → `core/auth.complete_login(...)`. No session required; reads `oauth_state` cookie.
- `POST /api/auth/logout` → `core/auth.end_session(...)`. Guarded by `require_authenticated`. Origin-checked by middleware.
- `GET /api/me` → `{ user_id, role, name, picture_url, hd }` on 200; **401** on `GUEST`. The hook-fetchable identity surface.

Returned shapes are ORM-free Pydantic DTOs.

**Responsibilities:** URL / HTTP contract layer over `core/auth`. The router never opens a transaction, never queries `users` or `sessions` directly, never touches `oauth_state` outside reading the cookie value to pass through.

**Seams:** None. The four endpoints are orchestrators of `core/auth` primitives.

**Depth note:** Shallow but justified — it is the single place URL contracts and HTTP semantics (302 vs 200, redirect-on-error, cookie clearing) live, so `core/auth` remains framework-agnostic and pure. Deletion test passes: collapsing into `core/auth` would couple OIDC to FastAPI redirect mechanics; keeping it here preserves the chokepoint's testability.

---

### `api/notifications` (FastAPI router)

**Interface:**

- `GET /api/notifications` → list owned by `current_user.user_id`, newest first.
- `GET /api/notifications/unread_count` → `{ count: int }`.
- `POST /api/notifications/{id}/read` → idempotent.
- `POST /api/notifications/mark_all_read` → bulk; idempotent.

All four guarded by `require_authenticated`. All mutations Origin-checked. Cross-user reads / writes return 404 (not 403) to avoid existence leakage.

**Responsibilities:** Owns the SQL inline against `notifications(id, user_id, event_key, kind, payload_json, read_at, created_at)` per ADR-0010 §9. Renders `payload_json` to a DTO indexed by `kind`. Enforces ownership in every query (`WHERE user_id = :uid`).

**Seams:** None. PRD explicit: "SQL stays in the router until a second caller earns extraction." No `core/notifications.py` until a producer / consumer outside this router materializes.

**Depth note:** Shallow by design. Earns its own router file because notifications are a domain noun (ADR-0010 §9) and the unread-count read path is hot enough that it shouldn't bleed into `api/search` or `api/auth`. Deletion test currently borderline — the four routes are the only callers — but cross-user isolation tests anchor the boundary.

---

### Origin-check middleware

**Interface:** ASGI middleware registered in `api/app.py`. For requests where `method in {POST, PUT, PATCH, DELETE}` AND a valid `sid` cookie is present, requires `request.headers.get("Origin") == settings.BUSCASAM_BASE_URL`; otherwise 403. Anonymous unsafe methods (e.g., the OAuth callback redirect target, which is a GET anyway) are unaffected. Health, OpenAPI, and login initiator are unaffected by virtue of method.

**Responsibilities:** Sole place CSRF defense in depth lives (ADR-0005 §15). Reads the cookie but does not validate it — middleware only checks Origin presence/match; auth-correctness is `current_user`'s job.

**Seams:** None.

**Depth note:** Single rule applied across the entire authenticated surface. Deletion test: scattered as per-route deps it would inevitably be forgotten on a future write endpoint, weakening the SameSite=Lax-plus-Origin posture. Middleware makes it unforgettable.

---

### `lib/useUser.ts` (TanStack hook)

**Interface:** `useUser() -> { user: { user_id, role, name, picture_url, hd } | null, isInvitado: boolean, isLoading: boolean }`. Stable query key (`["me"]`). `staleTime: 5min`, `refetchOnWindowFocus: true`. Maps 401 to `{ user: null, isInvitado: true }`; throws only on network failure.

**Responsibilities:** Single concentration of identity state on the client. Owns the request shape against `/api/me`, the 401-as-guest semantics, and the focus-refetch policy.

**Seams:** None.

**Depth note:** Shallow but earns isolation: every consumer (`AuthNav`, write paths that want to gate UI, the chip-rendering logic on `ResultCard` via prop drilling) reads from the same query cache, never duplicating `/api/me` fetches. Deletion test: without it, identity fetches would proliferate across components and SSR rules would be hard to enforce in review.

---

### `lib/useNotifications.ts` (TanStack hooks)

**Interface:** Two co-located hooks sharing cache keys:

- `useNotifications() -> { items, isLoading, markRead(id), markAllRead() }`.
- `useUnreadCount() -> { count, isLoading }`.

Both gate on `useUser()`'s `isInvitado === false`; for invitado they short-circuit to `{ items: [], count: 0 }` without fetching. `refetchOnWindowFocus: true` on count. `markRead` / `markAllRead` are optimistic — local cache decrements + flips immediately, rolls back on mutation error.

**Responsibilities:** Request shape against `/api/notifications*`, cache key design, optimistic update logic, and the invitado short-circuit.

**Seams:** None.

**Depth note:** Concentrates the focus-refetch + optimistic-mutation policy in one place so the bell badge and the panel list stay coherent. Deletion test: without it, the bell and panel would each maintain their own caches; mark-read in one would not reflect in the other.

---

### `app/login/page.tsx`

**Interface:** Next.js client page at `/login`. Renders the "Iniciar sesión con UNSAM" CTA pointing at `/api/auth/login?next=<encoded-current-or-/buscar>`. Reads `?error=not_unsam` and renders the retry surface ("Solo cuentas @unsam.edu.ar o @estudiantes.unsam.edu.ar...") with a single "Probar otra cuenta" button that re-initiates login. No SSR per ADR-0004 §3.

**Responsibilities:** Entry + retry UX. Knows the message variant set. Reads `next` from `useSearchParams` and forwards it.

**Seams:** None.

**Depth note:** Thin but earns its own page because the error-state copy and the retry mechanics are non-trivial and need Playwright coverage independent of the nav.

---

### `components/AuthNav.tsx`

**Interface:** Props: `{}`. Mounts inside `app/layout.tsx`. Reads `useUser()`. Renders either:

- Invitado: an "Iniciar sesión con UNSAM" `Link` pointing at `/login?next=<encodeURIComponent(currentPath)>`.
- Authenticated: avatar (picture_url) + dropdown with name, role label ("Estudiante" / "Docente"), and "Cerrar sesión" item that POSTs `/api/auth/logout` then `router.replace("/")`.

Composes `NotificationBell` next to the avatar (authenticated only).

**Responsibilities:** The global identity surface. Owns the redirect-on-logout convention and the role label projection.

**Seams:** None.

**Depth note:** Single visual contract for "who am I." Deletion test passes once: scatter the role label and login link into every page header.

---

### `components/NotificationBell.tsx`

**Interface:** Props: `{}`. Reads `useUnreadCount()`. Renders a bell icon with a numeric badge when `count > 0`. Wraps `BandejaPanel` as the Popover trigger; on open, fires `markAllRead()` (PRD §19 auto-mark behavior is at the open boundary, scoped to currently rendered items — see depth note).

**Responsibilities:** Trigger + badge. Owns the count → badge projection and the auto-mark-on-open trigger.

**Seams:** None.

**Depth note:** Earns isolation because the badge is the most-viewed component in the app and must be testable from the count query alone, independent of panel rendering. Auto-mark semantics live here, not in the panel, so the panel can render historical state cleanly during animations.

---

### `components/BandejaPanel.tsx`

**Interface:** Props: `{ onClose?: () => void }`. Popover content. Reads `useNotifications()`. Renders a vertically scrollable list of `NotificationItem` keyed by id; an empty state when `items.length === 0`; a footer with "Marcar todas como leídas" (bulk) when any unread remain.

**Responsibilities:** Panel layout, empty state, per-row hover affordance for the "Marcar como leída" button, bulk action wiring.

**Seams:** None.

**Depth note:** The list orchestrator. Without it, `NotificationBell` would couple to per-item layout decisions; keeping it separate lets the panel evolve (search-within-bandeja, grouping by day) without touching the bell.

---

### `components/NotificationItem.tsx`

**Interface:** Props: `{ item: NotificationDTO }`. Dispatches on `item.kind` to one of four per-kind renderers:

- `CoauthorInviteItem` — document title + inviter; CTA links to the acceptance surface (PRD #5).
- `DocumentHiddenItem` — document title + docente's reason (PRD #8 payload).
- `DocumentUnhiddenItem` — document title + docente's note (PRD #8 payload).
- `ProcessingFailedItem` — document title + draft management link (PRD #3 payload).

Each renderer exposes its own per-row "Marcar como leída" affordance (delegated to `useNotifications().markRead(id)`).

**Responsibilities:** Kind dispatch + payload-shape ownership per kind. Each per-kind subcomponent owns its own copy and CTA target.

**Seams:** **Real seam now.** Four adapters today, all rendering against test-seeded rows (producers land in PRDs #3, #5, #8). The dispatch table is the contract the producer PRDs satisfy.

**Depth note:** The contract surface that future producer PRDs must respect. Deletion test: collapse the four renderers into one switch and the producer PRDs would each be tempted to subclass / fork the renderer to add kind-specific UI (inline accept button for coauthor, reason expansion for hidden). The dispatcher pre-empts that.

---

## Touched, not new

- **`core/search_query.run`** — signature already accepts `user_ctx` (search-mvp map). `Results.rows` gains a `visibility` field so the frontend can render the `Interno`/`Privado` chip without a second roundtrip. Bind params from `readable_where` thread through.
- **`api/search`** — constructs `UserCtx` via `current_user`, forwards `visibility` in `ResultDTO`. The `unfiltered_total` rule is unchanged.
- **`api/areas`** — unchanged; no auth dep.
- **`app/buscar/ResultCard.tsx`** — surgical: renders a small "Interno" or "Privado" chip when `result.visibility !== "publico"`. Component contract stays single-purpose (no badge-slot abstraction).
- **`api/client.ts`** — gains a single 401-on-mutation interceptor that fires a soft toast ("Iniciá sesión para continuar"). 401 on read requests is intentionally silent (the read path already demoted to invitado server-side).

## Dependency graph

```
                      app/layout.tsx
                       /        \
                AuthNav      (page content)
                 / | \
        useUser  |  NotificationBell
                 |        |   \
                 |        |    BandejaPanel
                 |        |       |
                 |        |    NotificationItem
                 |        |       | \ \ \
                 |        |       CoauthorInviteItem
                 |        |       DocumentHiddenItem
                 |        |       DocumentUnhiddenItem
                 |        |       ProcessingFailedItem
                 |        |
                 |    useNotifications / useUnreadCount
                 |        |
                 |    GET /api/notifications*
                 |    POST /api/notifications/{id}/read
                 |    POST /api/notifications/mark_all_read
                 |        |
                 |    api/notifications
                 |        |
                 |    (Postgres: notifications)
                 |
              GET /api/me, POST /api/auth/logout, GET /api/auth/login, GET /api/auth/google/callback
                          |
                       api/auth
                          |
                       core/auth ─── Authlib ─── Google OIDC
                          |
                       (Postgres: users, sessions)

  (existing search slice, unchanged shape, threaded user_ctx)
                  api/search
                     |  \
                     |   current_user (core/auth)
                     |
                  core/search_query
                     |
                  core/document_access.readable_where (user_ctx)
                     |
                  (Postgres: chunks + documents + document_authors + áreas)

  (cross-cutting)
                  Origin-check middleware  ──>  every authenticated unsafe method
```

No cycles. Frontend talks to FastAPI only through the typed OpenAPI client (ADR-0004 §6); no Server Components consume `/api/me` (ADR-0005 §12).

## Out of scope

- **Coauthor invite producer** — PRD #5 owns the create / accept / decline flow and the `notifications` row insert. Only the renderer ships here.
- **Hide / unhide producer** — PRD #8 owns the moderation endpoints and the `document_hidden` / `document_unhidden` `notifications` inserts. Only renderers ship here.
- **`processing_failed` producer** — PRD #3 owns the indexing-pipeline failure path that writes the row. Only the renderer ships here.
- **Dedicated `/bandeja` route** — popover-only at MVP; if a producer in PRD #5 or #8 needs a deep-link surface, add it there.
- **Logout-everywhere / session list UI** — per-device only (ADR-0005 §13).
- **Onboarding interstitial** — first login lands directly on validated `next` or `/`.
- **Server-Component `/api/me`** — explicitly excluded by ADR-0004 §4 + ADR-0005 §12. SSR stays cookie-forward only.
- **Email notifications** — no SMTP path at MVP beyond what PRD #5 may add for the coauthor invite.
- **`core/sessions.py` / `core/oauth.py` split** — rejected. ADR-0005 §3 locks single-chokepoint `core/auth.py`; splitting would dilute the audit surface.
- **`/api/me` as its own router** — rejected. PRD locates it alongside `/api/auth/*` because all four endpoints share the same auth concerns and dep set.
- **`core/notifications.py` domain module** — rejected. SQL stays inline in `api/notifications.py` until a second caller earns extraction (PRD explicit).
- **`MIN_SEMANTIC_SIMILARITY` recalibration** — out of scope per PRD; same fixture-anchored offline workflow as PRD #1.
- **Real Google OIDC integration in tests** — a local mocked issuer Authlib can hit (`backend/tests/fixtures/oidc_issuer.py`) covers the dance; Google credentials never present outside production.
- **Personalization, query history, favourites, comments, browse landings** — ADR-0010 §2; never appear in MVP.

## Further Notes

- The `users`, `sessions`, and `notifications` tables ship via a single Alembic migration. Schema is the verbatim ADR-0005 §6/§8 + ADR-0010 §9 shape — no MVP additions.
- The mocked OIDC issuer fixture is the single seam between integration tests and the Authlib client; production never sees it. It lives next to other test fixtures, not under `src/`.
- The `Interno` / `Privado` chip relies on `Results.rows[].visibility` being present in the search response. That field addition is the only structural change to the search contract from this PRD — all other reach into `interno` / `privado` happens server-side through `readable_where`.
- The 401-on-mutation toast is a frontend-only convention; backend never returns content for the soft prompt. The interceptor reads the request method and lets reads pass silently.
