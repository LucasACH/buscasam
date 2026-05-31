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

// Resolve an ltree leaf path (e.g. "escuela.carrera.materia") to an
// Escuela › Carrera › Materia breadcrumb, mapping each ancestor segment to its
// display_name from /api/areas and falling back to the raw segment.
export function useAreaLabel(areaPath: string): string {
  const { data } = useQuery({ queryKey: ["areas"], queryFn: fetchAreas });
  const byPath = new Map((data ?? []).map((a) => [a.area_path, a.display_name]));
  const segments = areaPath.split(".");
  return segments
    .map((_, i) => byPath.get(segments.slice(0, i + 1).join(".")) ?? segments[i])
    .join(" › ");
}

// Read-only Escuela › Carrera › Materia breadcrumb.
export function AreaField({ areaPath }: { areaPath: string }) {
  const label = useAreaLabel(areaPath);
  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium">Área</span>
      <div className="text-muted-foreground rounded-lg border border-border bg-neutral-50 px-3 py-2.5 text-sm">
        {label}
      </div>
    </div>
  );
}
