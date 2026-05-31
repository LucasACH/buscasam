"use client";

import { useAreaLabel } from "@/lib/useAreas";

// Re-exported so moderation keeps importing it from here.
export { useAreaLabel };

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
