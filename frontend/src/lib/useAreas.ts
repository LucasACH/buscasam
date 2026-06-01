"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type Area = components["schemas"]["AreaDTO"];

async function fetchAreas(): Promise<Area[]> {
  const { data, error } = await api.GET("/api/areas");
  if (error) throw error;
  return data ?? [];
}

export function useAreas() {
  return useQuery({
    queryKey: ["areas"],
    queryFn: fetchAreas,
    staleTime: 60 * 60_000,
    gcTime: 60 * 60_000,
  });
}

// Resolve an ltree leaf path (e.g. "escuela.carrera.materia") to an
// Escuela › Carrera › Materia breadcrumb, mapping each ancestor segment to its
// display_name from /api/areas and falling back to the raw segment. Returns
// null for a null path so callers can render their own placeholder. With
// `collapse`, paths deeper than 2 segments render as first › … › last to avoid
// overflow.
export function useAreaLabel(
  areaPath: string | null,
  collapse = false,
): string | null {
  const { data } = useAreas();
  if (!areaPath) return null;
  const byPath = new Map(
    (data ?? []).map((a) => [a.area_path, a.display_name]),
  );
  const segments = areaPath.split(".");
  const labels = segments.map(
    (_, i) => byPath.get(segments.slice(0, i + 1).join(".")) ?? segments[i],
  );
  if (collapse && labels.length > 2) {
    return [labels[0], "…", labels[labels.length - 1]].join(" › ");
  }
  return labels.join(" › ");
}
