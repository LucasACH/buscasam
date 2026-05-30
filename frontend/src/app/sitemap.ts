import "server-only";

import type { MetadataRoute } from "next";

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
  const r = await fetch(`${internalApiBase()}/sitemap`, { cache: "no-store" });
  if (!r.ok) return [];
  const entries = (await r.json()) as SitemapEntry[];
  const base = publicBase();
  return entries.map((e) => ({
    url: `${base}/docs/${e.id}`,
    lastModified: e.lastmod ? new Date(e.lastmod) : undefined,
  }));
}
