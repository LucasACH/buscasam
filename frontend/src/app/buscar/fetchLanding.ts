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

// Both fetches degrade to empty on any failure (including a backend that is
// unreachable at build time): the page prerenders empty and ISR (revalidate:300)
// repopulates from the live API at runtime, so the build stays hermetic.
export async function fetchPopular(): Promise<PopularResponse> {
  try {
    const r = await fetch(`${internalApiBase()}/docs/popular?limit=3`, {
      next: { revalidate: 300 },
    });
    if (!r.ok) return { results: [], public_total: 0 };
    return (await r.json()) as PopularResponse;
  } catch {
    return { results: [], public_total: 0 };
  }
}

export async function fetchAreas(): Promise<Area[]> {
  try {
    const r = await fetch(`${internalApiBase()}/areas`, {
      next: { revalidate: 300 },
    });
    if (!r.ok) return [];
    return (await r.json()) as Area[];
  } catch {
    return [];
  }
}
