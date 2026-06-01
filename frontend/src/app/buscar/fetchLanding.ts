import "server-only";

import type { Area } from "@/lib/useAreas";

import type { PopularResult } from "./useMostRead";

type PopularResponse = { results: PopularResult[]; public_total: number };

function internalApiBase(): string {
  const internal = process.env.BUSCASAM_INTERNAL_API_URL;
  if (internal) return internal.replace(/\/$/, "");
  const fallback = process.env.BUSCASAM_API_URL ?? "http://127.0.0.1:8000";
  return `${fallback.replace(/\/$/, "")}/api`;
}

export async function fetchPopular(): Promise<PopularResponse> {
  const r = await fetch(`${internalApiBase()}/docs/popular?limit=3`, {
    next: { revalidate: 300 },
  });
  if (!r.ok) throw new Error(`popular fetch failed: ${r.status}`);
  return (await r.json()) as PopularResponse;
}

export async function fetchAreas(): Promise<Area[]> {
  const r = await fetch(`${internalApiBase()}/areas`, {
    next: { revalidate: 300 },
  });
  if (!r.ok) return [];
  return (await r.json()) as Area[];
}
