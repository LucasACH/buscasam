# Next.js App Router, SSR scoped to doc detail + sitemap

## Status

Accepted

## Decision

Next.js (App Router, latest stable) deployed as a single Node process on the same VM as FastAPI + TEI + Postgres + worker. A reverse proxy fronts both processes on one origin: HTML routes go to Next, `/api/*` goes to FastAPI. SSR is restricted to `/docs/[id]` (público SEO target) and `/sitemap.xml` / `/robots.txt`. Every other page is client-rendered. A typed client generated from FastAPI's OpenAPI schema is the only seam between the two processes.

## Locked

1. Framework: Next.js, latest stable, **App Router** (`app/` directory). Pinned in `frontend/package.json`. `output: 'standalone'`.
2. Process topology: one Node process for Next.js on the same VM as the backend. Memory budget ~200 MB. Reverse proxy routes `/api/*` to FastAPI on `:8000` and everything else to Next on `:3000`. TLS terminates at the proxy.
3. SSR surface: exactly `app/docs/[id]/page.tsx`, `app/sitemap.ts`, `app/robots.ts`. Every other route is a Client Component with `'use client'` at the top.
4. Cookie-forwarding SSR. The `/docs/[id]` Server Component reads the incoming `Cookie` header via `next/headers` and forwards it on `fetch('http://localhost:8000/docs/{id}', { headers: { cookie }, cache: 'no-store' })`. FastAPI applies the visibility predicate (ADR-0001 §9). On 404, call `notFound()`. Sitemap query is hard-coded to `WHERE visibility = 'publico' AND soft_deleted_at IS NULL`.
5. No BFF. No `app/api/*` route handlers that proxy or wrap FastAPI endpoints. Browser fetches go through the reverse proxy directly to FastAPI; Server Components fetch FastAPI on `localhost`.
6. API client. `openapi-typescript` regenerates `frontend/src/api/schema.d.ts` from FastAPI's `/openapi.json` as a CI step. `openapi-fetch` (~6 KB runtime) is the typed client. TanStack Query is added per-feature for client-side caching/invalidation (search results, comments, favorites) — not blanket.
7. No SSR caching at MVP. Doc-detail Server Component uses `cache: 'no-store'`. `Cache-Control: private, no-store` on the response.
8. Forms: React Hook Form + Zod for client-side validation. Forms submit directly to FastAPI through the reverse proxy. No Server Actions. File upload (publish flow) is `multipart/form-data` straight to FastAPI, which returns 202 and enqueues.
9. Styling: Tailwind CSS; shadcn/ui for accessible primitives (Radix-based, copy-pasted source under `frontend/src/components/ui/`). No runtime CSS-in-JS. No second component library.
10. Repo layout: monorepo at the repo root: `backend/` and `frontend/`. Top-level CI runs both pipelines. The OpenAPI codegen job boots FastAPI, hits `/openapi.json`, regenerates `frontend/src/api/schema.d.ts`, and fails the PR if the diff is uncommitted.
11. Toolchain: pnpm (`packageManager` field); Node LTS pinned via `.nvmrc`. Next's default ESLint config + Prettier. Vitest for unit/component; Playwright for E2E smoke (search, publish, doc-detail). `tsc --noEmit` is a required CI gate.
12. i18n: none. UI strings are Spanish, written inline.
13. Client state: local component state (`useState`, `useReducer`) + TanStack Query for server state. No Zustand, Redux, Jotai. If cross-component client state need emerges, introduce the smallest scoped Context.
