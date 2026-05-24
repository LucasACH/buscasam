# Next.js App Router, SSR scoped to doc detail + sitemap

## Status

Accepted

## Decision

Next.js App Router is deployed as a single Node process in the same Compose network as FastAPI. A reverse proxy fronts both processes on one origin: HTML routes go to Next, `/api/*` goes to FastAPI. SSR is used for public document detail and crawler metadata; interactive MVP flows are client-rendered. A typed client generated from FastAPI's OpenAPI schema is the only seam between the processes.

## Locked

1. Framework: Next.js **App Router** (`app/` directory), pinned to an exact tested version in `frontend/package.json` and lockfile. `output: 'standalone'`.
2. Process topology: one Node process for Next.js on the same VM as the backend. Memory budget ~200 MB. Reverse proxy routes `/api/*` to FastAPI on `:8000` and everything else to Next on `:3000`. TLS terminates at the proxy.
3. SSR surface: `app/docs/[id]/page.tsx`, `app/sitemap.ts`, and `app/robots.ts`. Other MVP pages may use Server Components for static layout but perform authenticated mutations/interactions client-side.
4. Container-safe SSR. `BUSCASAM_INTERNAL_API_URL=http://api:8000/api` is available only to the Node server. `/docs/[id]` forwards the incoming `Cookie` header to `${BUSCASAM_INTERNAL_API_URL}/docs/{id}` with `cache: 'no-store'`; FastAPI applies ADR-0010 access. On 404, call `notFound()`. Sitemap calls a public-only FastAPI sitemap endpoint; it never queries Postgres directly.
5. No BFF. No `app/api/*` route handlers that proxy or wrap FastAPI endpoints. Browser fetches go through the reverse proxy directly to FastAPI; Server Components use `BUSCASAM_INTERNAL_API_URL`.
6. API client. `openapi-typescript` regenerates `frontend/src/api/schema.d.ts` from FastAPI's `/openapi.json` as a CI step. `openapi-fetch` is the typed client. TanStack Query is used for search, draft status/publish, co-author invitations, and moderation only.
7. No SSR caching at MVP. Doc-detail Server Component uses `cache: 'no-store'`. `Cache-Control: private, no-store` on the response.
8. Forms: React Hook Form + Zod for client-side validation. Forms submit directly to FastAPI through the reverse proxy. No Server Actions. Main-file upload is `multipart/form-data` straight to FastAPI, returns 202, and enters ADR-0010 `processing`; attachment uploads are separate capped requests.
9. Styling: Tailwind CSS; shadcn/ui for accessible primitives (Radix-based, copy-pasted source under `frontend/src/components/ui/`). No runtime CSS-in-JS. No second component library.
10. Repo layout: monorepo at the repo root: `backend/` and `frontend/`. Top-level CI runs both pipelines. The OpenAPI codegen job boots FastAPI, hits `/openapi.json`, regenerates `frontend/src/api/schema.d.ts`, and fails the PR if the diff is uncommitted.
11. Toolchain: pnpm (`packageManager` field); Node LTS pinned via `.nvmrc`. Next's default ESLint config + Prettier. Vitest for unit/component; Playwright for E2E smoke (visibility-aware search, staged publish, doc-detail/download, moderation). `tsc --noEmit` is a required CI gate.
12. i18n: none. UI strings are Spanish, written inline.
13. Client state: local component state (`useState`, `useReducer`) + TanStack Query for server state. No Zustand, Redux, Jotai. If cross-component client state need emerges, introduce the smallest scoped Context.
