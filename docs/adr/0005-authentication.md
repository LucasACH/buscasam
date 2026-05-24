# Google Workspace OIDC, role from `hd`, opaque Postgres sessions

## Status

Accepted

## Decision

Authentication is Google OIDC restricted to UNSAM Workspace tenants. Role derives from the `hd` claim: `estudiantes.unsam.edu.ar` -> `estudiante`, `unsam.edu.ar` -> `docente`. Any other `hd`, missing `hd`, or `email_verified != true` is rejected at the callback. Sessions are opaque server-side rows in Postgres, addressed by a 32-byte random `sid` carried in an `HttpOnly; Secure; SameSite=Lax` cookie, with enforced 30-day idle / 90-day absolute expiry. OAuth callback lands on FastAPI (`/api/auth/google/callback`). Three FastAPI dependencies (`current_user`, `require_authenticated`, `require_docente`) gate every endpoint. Guests are a first-class `UserCtx`. JIT user provisioning runs on every callback via `INSERT ... ON CONFLICT (google_sub) DO UPDATE ...`.

## Locked

1. IdP: Google OIDC via `Authlib`. `client_id` / `client_secret` from `pydantic-settings`.
2. Domain allowlist: `estudiantes.unsam.edu.ar` -> `estudiante`, `unsam.edu.ar` -> `docente`. Frozen `ROLE_BY_HD` mapping in `core/auth.py`. Any other `hd`, missing `hd`, or `email_verified != True` -> 302 to `/login?error=not_unsam`, no session created, no `users` row touched.
3. Auth chokepoint. All `hd` to role mapping, session creation, and `UserCtx` instantiation live in `core/auth.py`; tests cover the accepted and rejected claim combinations.
4. OAuth dance. Initiator: `GET /api/auth/login?next=<path>` issues 302 to Google's authorize endpoint. Callback: `GET /api/auth/google/callback`. State carried in a 10-minute HMAC-signed `oauth_state` cookie (`itsdangerous`) containing `(nonce, next_url, expires_at, pkce_verifier)`. PKCE enabled. `hd=*` hint on the authorize URL; the post-exchange allowlist is the load-bearing check.
5. `next` safety: must satisfy `next.startswith('/') and not next.startswith('//')`; otherwise default to `/`.
6. Sessions table:

   ```
   sessions (
     sid           bytea primary key,                    -- 32 random bytes
     user_id       bigint not null references users(id) on delete cascade,
     created_at    timestamptz not null default now(),
     last_seen_at  timestamptz not null default now(),   -- sliding expiry signal
     expires_at    timestamptz not null,                 -- hard cap, immutable
     user_agent    text,
     ip            inet
   )
   ```

   `sid` is generated with `secrets.token_bytes(32)`. A session is invalid when `expires_at <= now()` or `last_seen_at <= now() - interval '30 days'`; invalid sessions are treated as anonymous and their cookie is cleared. To limit writes, an authenticated request refreshes `last_seen_at` and the cookie only when `last_seen_at < now() - interval '24 hours'`. `expires_at = created_at + 90 days` is never extended.
7. Cookie: `Set-Cookie: sid=<base64url(sid)>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=<min(30 days, hard-cap remaining)>`. Frontend learns identity via `GET /api/me`.
8. Users table:

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

   Immutable: `id`, `google_sub`, `created_at`. Refreshed every login: `email`, `hd`, `role`, `name`, `picture_url`, `last_login_at`.
9. JIT provisioning: single `INSERT … ON CONFLICT (google_sub) DO UPDATE …` at the callback. Race-safe under concurrent first-logins.
10. `UserCtx` and dependencies in `core/auth.py`:

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

    Every business/data endpoint declares the appropriate dependency; health, OpenAPI, login initiator, and OAuth callback are exempt or use their dedicated validation. Document ownership/access checks execute through `core/document_access.py`, not ad hoc handler predicates.
11. Access integration. The `UserCtx` produced by `current_user` is consumed by `core/document_access.py` and search/related queries under ADR-0010. Guests see only published, non-deleted, non-hidden `publico` documents. Pending co-authors do not acquire private access.
12. `/api/me`: returns `{ user_id, role, name, picture_url, hd }` (200) or 401. Frontend's `useUser()` hook fetches on mount. SSR `/docs/[id]` does NOT call it.
13. Logout: `POST /api/auth/logout`, guarded by `require_authenticated`. Deletes the `sessions` row by `sid` and emits `Set-Cookie: sid=; Max-Age=0`. Per-device.
14. Invalid/expired session on read paths: treated as Guest, not 401. Cookie silently ignored.
15. CSRF: `SameSite=Lax` is defense in depth, not the only check. Authenticated unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`) reject requests whose `Origin` is missing or is not exactly `BUSCASAM_BASE_URL`. OAuth uses the signed state cookie and PKCE from section 4.
16. Rate limiting: ADR-0009 applies limits regardless of unvalidated cookie presence.
