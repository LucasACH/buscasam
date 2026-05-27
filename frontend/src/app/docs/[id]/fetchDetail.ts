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

type AreaRow = { area_path: string; display_name: string };

async function fetchAreasUncached(): Promise<AreaRow[]> {
  const r = await fetch(`${internalApiBase()}/areas`, { cache: "no-store" });
  if (!r.ok) return [];
  return (await r.json()) as AreaRow[];
}

export const fetchAreas = cache(fetchAreasUncached);
