import "server-only";

import type { MetadataRoute } from "next";

// Never prerender at build time: the backend is unreachable during the image
// build, which would bake an empty sitemap and cache it. Query live like
// robots.ts (the fetch below keeps its own 1h ISR cache).
export const dynamic = "force-dynamic";

// ADR-0004 §3–4: SSR sitemap from a public-only FastAPI endpoint; never queries
// Postgres directly. The backend applies `invitado_where`, so only `publico`
// documents appear.
function internalApiBase(): string {
  const internal = process.env.BUSCASAM_INTERNAL_API_URL;
  if (internal) return internal.replace(/\/$/, "");
  const fallback = process.env.BUSCASAM_API_URL ?? "http://127.0.0.1:8000";
  return `${fallback.replace(/\/$/, "")}/api`;
}

function publicBase(): string {
  return (process.env.BUSCASAM_BASE_URL ?? "http://localhost:3000").replace(
    /\/$/,
    "",
  );
}

type SitemapEntry = { id: number; lastmod: string | null };

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  let entries: SitemapEntry[];
  try {
    // Degrade to an empty sitemap if the backend is unreachable (e.g. at build
    // time): the route is ISR (revalidate:3600) and refills from the live API.
    const r = await fetch(`${internalApiBase()}/sitemap`, {
      next: { revalidate: 3600 },
    });
    if (!r.ok) return [];
    entries = (await r.json()) as SitemapEntry[];
  } catch {
    return [];
  }
  const base = publicBase();
  return [
    { url: `${base}/buscar`, changeFrequency: "daily", priority: 1 },
    ...entries.map((e) => ({
      url: `${base}/docs/${e.id}`,
      lastModified: e.lastmod ? new Date(e.lastmod) : undefined,
    })),
  ];
}
