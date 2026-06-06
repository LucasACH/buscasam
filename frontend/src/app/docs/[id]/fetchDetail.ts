import "server-only";

import { cache } from "react";
import { headers } from "next/headers";

import type { DocDetail } from "./types";

function internalApiBase(): string {
  const internal = process.env.BUSCASAM_INTERNAL_API_URL;
  if (internal) return internal.replace(/\/$/, "");
  // Local-dev fallback: the proxy var that next.config.ts already reads.
  const fallback = process.env.BUSCASAM_API_URL ?? "http://127.0.0.1:8000";
  return `${fallback.replace(/\/$/, "")}/api`;
}

async function fetchDocDetailUncached(
  docId: number,
): Promise<DocDetail | null> {
  const cookie = (await headers()).get("cookie") ?? "";
  const r = await fetch(`${internalApiBase()}/docs/${docId}`, {
    cache: "no-store",
    headers: cookie ? { cookie } : undefined,
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`detail fetch failed: ${r.status}`);
  return (await r.json()) as DocDetail;
}

export const fetchDocDetail = cache(fetchDocDetailUncached);

export async function recordSearchClick(
  searchId: string,
  docId: number,
  rank: number,
  cookie: string,
): Promise<void> {
  // Best-effort relevance instrumentation: attribute this doc view to the
  // search that produced it. Never throws — a logging failure must not break
  // the page render. Idempotent server-side per (search_id, doc_id). `cookie`
  // is passed in (read during render): request APIs like headers() can't be
  // called from the after() callback this runs inside.
  try {
    await fetch(`${internalApiBase()}/search/click`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        ...(cookie ? { cookie } : {}),
      },
      body: JSON.stringify({ search_id: searchId, doc_id: docId, rank }),
    });
  } catch {
    // swallow — instrumentation is non-critical
  }
}

export type Area = { area_path: string; display_name: string };

async function fetchAreasUncached(): Promise<Area[]> {
  const r = await fetch(`${internalApiBase()}/areas`, {
    next: { revalidate: 300 },
  });
  if (!r.ok) return [];
  return (await r.json()) as Area[];
}

export const fetchAreas = cache(fetchAreasUncached);
