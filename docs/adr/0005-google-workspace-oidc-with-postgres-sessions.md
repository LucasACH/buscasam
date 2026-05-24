# Google Workspace OIDC, role from `hd`, opaque Postgres sessions

## Status

Accepted

## Decision

Authentication is Google OIDC restricted to UNSAM Workspace tenants. Role derives mechanically from the OIDC `hd` (hosted-domain) claim: `estudiantes.unsam.edu.ar` → `estudiante`, `unsam.edu.ar` → `docente`; any other `hd`, a missing `hd`, or `email_verified != true` is rejected at the callback with no session created. Sessions are opaque server-side rows in a Postgres `sessions` table, addressed by a 32-byte random `sid` carried in an `HttpOnly; Secure; SameSite=Lax` cookie, 30-day sliding expiry with a 90-day hard cap. The OAuth callback lands on FastAPI (`/api/auth/google/callback`); Next is not in the dance. Three FastAPI dependencies (`current_user`, `require_authenticated`, `require_docente`) gate every endpoint, and **guests are a first-class `UserCtx`** (`user_id=None, is_unsam=False, role=None`) that flows through the visibility predicate from ADR-0001 §9 and collapses it naturally to `WHERE visibility = 'publico'` — no `if guest:` branching anywhere in feature code. JIT user provisioning runs on every callback via a single `INSERT … ON CONFLICT (google_sub) DO UPDATE …` statement.

## Context

SPEC §Usuarios calls for UNSAM SSO with role derived from the directory and `Invitados` browsing without login. UNSAM IT does not currently expose a federation-friendly endpoint (no confirmed CAS/SAML/OIDC URL the team can target without a coordination cycle), but both UNSAM email domains (`unsam.edu.ar` and `estudiantes.unsam.edu.ar`) are Google Workspace tenants — which gives us a verified `hd` claim on every ID token, sufficient to discriminate role without any institutional integration. ADR-0001 §9 already requires a `user_ctx = (user_id, is_unsam)` on every search query and centralises the visibility predicate in one SQL builder; ADR-0003 §3 keeps that predicate behind a CI-enforced chokepoint; ADR-0004 §5 deferred the SSO-callback-origin decision explicitly to this ADR. The visibility predicate is load-bearing for correctness — a leaked `interno` or `privado` document is a credibility failure — and the team is small enough that "two ways to do auth" is itself a risk.

## Considered options

- **UNSAM CAS / Apereo direct integration.** Rejected pending confirmation that UNSAM IT runs CAS at all. Even if they do, the integration requires service registration, endpoint exchange, and almost certainly a separate LDAP bind to recover affiliation — two systems to keep in sync, blocked on an IT coordination cycle the team can't schedule.
- **SAML / Shibboleth federation.** Rejected: heaviest setup (metadata exchange, signing certificates, IdP discovery), and UNSAM's federation membership is unconfirmed. Same dependency on IT as CAS, more moving parts.
- **Custom username + password.** Rejected: re-implements identity (password reset, throttling, breach recovery) for no payoff. Not the bar for an academic platform when the user population already has Workspace accounts.
- **JWT in cookie instead of opaque session.** Rejected: revocation needs a denylist (which is itself a DB read, so the "stateless" win evaporates), role-in-token is staleness-sensitive (a domain reassignment doesn't take effect until the token expires), and the only JWT advantage that matters — statelessness across origins — doesn't apply on a single-VM same-origin deploy. Cookie size also balloons from ~40 bytes to ~1 KB on every request.
- **NextAuth.js / Auth.js owning sessions in the frontend.** Rejected: puts the session-of-record in the process that does *not* own the visibility predicate. The `users` row would either be duplicated or read across processes, the cookie would have to be parsed on both sides, and the ADR-0003 §9 "OpenAPI is the only seam" invariant would crack.
- **OAuth callback on the Next frontend** (the ADR-0004 §5 carve-out). Rejected: nothing forces the callback to the frontend origin — the reverse proxy already provides same-origin. Two processes touching auth where one suffices; the carve-out goes unused.
- **A permissions table layered on top of `hd`.** Rejected: SPEC's "any docente moderates" rule is honoured cleanly by collapsing "UNSAM staff with `@unsam.edu.ar`" into the `docente` role. A permissions table adds complexity for a hypothetical future need and can be introduced later if non-teaching `@unsam.edu.ar` holders ever need to be excluded from moderation.
- **Sourcing Escuela / carrera / cursos from an institutional system for cold-start recommendations.** Rejected at this scope: requires LDAP or SIU-Guaraní integration that doesn't exist. The recommendation system degrades from "personalised from day one" to "generic until the user marks intereses or accumulates search history" — acceptable for MVP, documented as a SPEC amendment (§Perfil / §Primer ingreso).

## Architecture decisions locked by this ADR

1. **IdP.** Google OIDC, via `Authlib`. `client_id` / `client_secret` issued from Google Cloud against the UNSAM Workspace, configured through `pydantic-settings` (ADR-0003 §7).
2. **Domain allowlist.** Exactly two entries: `estudiantes.unsam.edu.ar` → `estudiante`, `unsam.edu.ar` → `docente`. Encoded as a frozen `ROLE_BY_HD` mapping in `core/auth.py`. Any other `hd`, a missing `hd`, or `email_verified != True` triggers a 302 to `/login?error=not_unsam` with no session created and no `users` row touched.
3. **Auth chokepoint.** All `hd` → role mapping, session creation, and `UserCtx` instantiation live in `core/auth.py`. Feature code never reads `hd`, never constructs a `UserCtx`, and never queries `users` for role. A CI grep blocks the literals `claims["hd"]`, `claims.get("hd")`, `ROLE_BY_HD`, and `UserCtx(` from appearing anywhere outside `core/auth.py` and its tests — same shape as the search chokepoint (ADR-0003 §3) and the embed chokepoint (ADR-0002 §3).
4. **OAuth dance.** Initiator: `GET /api/auth/login?next=<path>` issues a 302 to Google's authorize endpoint. Callback: `GET /api/auth/google/callback`. State carried in a 10-minute HMAC-signed `oauth_state` cookie (`itsdangerous`) containing `(nonce, next_url, expires_at, pkce_verifier)`. PKCE enabled. `hd=*` hint passed to the Google authorize URL to filter pure `@gmail.com` at the account picker; the post-exchange allowlist (§2) remains the load-bearing check.
5. **`next` safety.** Post-callback redirect target must satisfy `next.startswith('/') and not next.startswith('//')`; otherwise default to `/`. Standard open-redirect guard.
6. **Sessions.** Postgres `sessions` table:

   ```
   sessions (
     sid           bytea primary key,                    -- 32 random bytes
     user_id       bigint not null references users(id) on delete cascade,
     created_at    timestamptz not null default now(),
     last_seen_at  timestamptz not null default now(),   -- sliding expiry signal
     expires_at    timestamptz not null,                 -- hard cap, immutable from row creation
     user_agent    text,
     ip            inet
   )
   ```

   `sid` generated with `secrets.token_bytes(32)`. Sliding window: `last_seen_at` is updated on every authenticated request. Hard cap: `expires_at = created_at + 90 days`, never extended. A request whose session row has `expires_at < now()` is treated as anonymous and the cookie is silently dropped.
7. **Cookie.** `Set-Cookie: sid=<base64url(sid)>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000`. No second non-HttpOnly companion cookie; the frontend learns identity through `GET /api/me`.
8. **Users table.**

   ```
   users (
     id            bigserial primary key,
     google_sub    text unique not null,         -- match key, IMMUTABLE
     email         text not null,
     hd            text not null,                -- refreshed → drives role
     role          text not null,                -- recomputed from hd at every login
     name          text not null,
     picture_url   text,
     created_at    timestamptz not null default now(),  -- IMMUTABLE
     last_login_at timestamptz not null default now()
   )
   ```

   **Immutable**: `id`, `google_sub`, `created_at`. **Refreshed every login**: `email`, `hd`, `role`, `name`, `picture_url`, `last_login_at`.
9. **JIT provisioning.** Single `INSERT … ON CONFLICT (google_sub) DO UPDATE …` statement at the callback. Race-safe under concurrent first-logins; no read-then-write.
10. **`UserCtx` and dependencies.** Three FastAPI dependencies, defined in `core/auth.py`:

    ```python
    @dataclass(frozen=True)
    class UserCtx:
        user_id: int | None
        is_unsam: bool
        role: Literal["estudiante", "docente"] | None

    GUEST = UserCtx(user_id=None, is_unsam=False, role=None)

    async def current_user(...) -> UserCtx: ...              # GUEST if no/invalid/expired sid
    def require_authenticated(...) -> UserCtx: ...           # 401 if user_id is None
    def require_docente(...) -> UserCtx: ...                 # 403 if role != "docente"
    ```

    Every router endpoint declares exactly one of the three. A fourth tier ("only the document's owner") is not introduced here — ownership checks happen inside the handler against `current_user.user_id`.
11. **Visibility predicate integration.** The `UserCtx` produced by `current_user` is what the search chokepoint (ADR-0001 §9, ADR-0003 §3) consumes. For a guest, `is_unsam=False, user_id=None` collapses the predicate to `WHERE visibility = 'publico' AND soft_deleted_at IS NULL` (the `interno` branch evaluates false, and the `document_authors EXISTS` subquery returns no rows for a `NULL` user id). No new SQL, no new branch, no `if guest:` in feature code — the predicate written for ADR-0001 already handles this case.
12. **`/api/me`.** Returns `{ user_id, role, name, picture_url, hd }` (200) or `401` if the request is anonymous. The frontend's `useUser()` hook fetches it on mount; the SSR `/docs/[id]` Server Component does *not* call it — it just forwards the cookie per ADR-0004 §4 and trusts the backend.
13. **Logout.** `POST /api/auth/logout`, guarded by `require_authenticated`. Deletes the `sessions` row by `sid` and emits `Set-Cookie: sid=; Max-Age=0`. Per-device: logging out on one browser does not log out other devices (one user can have many session rows).
14. **Invalid/expired session on read paths.** Treated as Guest, not 401. The cookie is silently ignored and `current_user` returns `GUEST`. A user mid-read of a `público` page keeps reading; their next write attempt 401s, the frontend re-authenticates, and they resume.
15. **CSRF posture.** Reliance on `SameSite=Lax` + the same-origin reverse proxy (ADR-0004 §2). No CSRF tokens at MVP. Documented assumption: every mutating endpoint is reachable only from `buscasam.unsam.edu.ar`. Any future cross-origin client (mobile app, partner integration) requires re-opening this ADR.
16. **Rate limiting.** Out of scope. Deferred to ADR-0009 (deploy topology owns the reverse proxy, which is the right place for guest and auth-endpoint throttling).

## Consequences

- **Auth is decoupled from UNSAM IT.** No integration meeting, no service registration, no certs to renew. The dependency we acquire instead is on UNSAM keeping both domains on Google Workspace; the day UNSAM migrates institutional email off Google, this ADR is reopened — replace the Authlib Google provider with the new IdP, keep the `hd`-equivalent claim, the `users` table, the `UserCtx` plumbing, and the chokepoint.
- **Role is permanently a function of the email domain.** A teaching docente whose Workspace account is ever moved to `@estudiantes.unsam.edu.ar` would silently become an estudiante on next login. Workspace-administration question, not an application question. The CI grep on `ROLE_BY_HD` (§3) prevents the role-mapping from growing a side door.
- **Moderation surface = `@unsam.edu.ar` holders.** That includes admin, library, IT, and gestión — not strictly teaching faculty (`CONTEXT.md` records this as the canonical meaning of *Docente*). If a specific person ever needs to be excluded from moderation, we re-open this ADR rather than smuggle an ad-hoc check; the right fix is the permissions table this ADR rejected.
- **SPEC §Perfil and §Primer ingreso degrade.** Google OIDC delivers `sub`, `email`, `hd`, `name`, and `picture` — no Escuela, no carrera, no cursos. The `users` table holds none of these fields at MVP, and the SPEC promise that "recomendaciones funcionan desde el primer día con datos del SSO" is partially broken: fresh users see generic recommendations until they search or set `intereses`. `SPEC.md` is amended in the same PR as this ADR.
- **The visibility predicate stays exactly as written in ADR-0001 §9.** Adding auth was strictly additive to the predicate's existing inputs — a UX milestone, not an architectural one. The Guest-as-first-class-`UserCtx` trick is the load-bearing payoff: no new SQL, no new branch, no leak surface introduced.
- **Three dependencies are exhaustive.** Every endpoint declares exactly one of `current_user` / `require_authenticated` / `require_docente`. Ownership checks happen inside handlers against `current_user.user_id`. If a fourth tier becomes common (e.g., "co-author only"), re-open this ADR rather than introducing a fourth dependency ad-hoc.
- **Session-state lives in Postgres.** Adds one indexed `SELECT` + one `UPDATE` per authenticated request. Sub-millisecond at MVP scale. Flagged if it ever shows up in profiling; mitigation would be batching `last_seen_at` writes or moving sessions to Redis, neither needed at MVP.
- **No password recovery, no MFA toggle, no email confirmation.** Google owns identity end-to-end. If a user can't sign in, the recovery path is Google's. Explicit non-feature.
- **Guests can crawl `público` content.** SPEC accepts this (público = SEO target, ADR-0004 §3). Rate limiting at the reverse proxy (ADR-0009) is the right knob if abuse appears.
- **CSRF posture is "SameSite + same origin", not tokens.** A future API consumer on a different origin breaks this assumption; §15 must be revisited before any such consumer ships.
- **One CI grep, three chokepoints.** Auth (this ADR §3), search (ADR-0003 §3), embed (ADR-0002 §3). The pattern is established: load-bearing-for-correctness logic lives in one named module, and CI keeps the rest of the codebase from reaching around it.
