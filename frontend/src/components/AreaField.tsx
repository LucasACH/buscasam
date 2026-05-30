"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

type Area = components["schemas"]["AreaDTO"];

async function fetchAreas(): Promise<Area[]> {
  const { data, error } = await api.GET("/api/areas");
  if (error) throw error;
  return data ?? [];
}

// Read-only Escuela › Carrera › Materia breadcrumb. area_path is an ltree leaf
// (e.g. "escuela.carrera.materia"); resolve each ancestor segment to its
// display_name from /api/areas, falling back to the raw segment.
export function AreaField({ areaPath }: { areaPath: string }) {
  const { data } = useQuery({ queryKey: ["areas"], queryFn: fetchAreas });
  const byPath = new Map((data ?? []).map((a) => [a.area_path, a.display_name]));
  const segments = areaPath.split(".");
  const label = segments
    .map((_, i) => byPath.get(segments.slice(0, i + 1).join(".")) ?? segments[i])
    .join(" › ");
  return (
    <div className="space-y-1">
      <span className="text-sm font-medium">Área</span>
      <p className="text-muted-foreground text-sm">{label}</p>
    </div>
  );
}
