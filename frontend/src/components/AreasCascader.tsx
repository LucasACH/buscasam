"use client";

import { useState } from "react";
import { Check, ChevronLeft, ChevronRight, MapPin, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAreas } from "@/lib/useAreas";

function levelOf(area_path: string): number {
  return area_path.split(".").length;
}

function parentOf(area_path: string): string {
  const parts = area_path.split(".");
  parts.pop();
  return parts.join(".");
}

export type AreasCascaderProps = {
  onChange: (area_path: string | null) => void;
  value?: string | null;
};

// Drill-down Escuela › Carrera › Materia cascader. Only leaves (the deepest
// level under a branch) are selectable; branch rows drill into their children.
export function AreasCascader({ onChange, value }: AreasCascaderProps) {
  const { data } = useAreas();
  const rows = data ?? [];
  const byPath = new Map(rows.map((a) => [a.area_path, a.display_name]));

  // `nav` is the parent path whose children are listed; "" lists the escuelas.
  const [nav, setNav] = useState<string>(() => (value ? parentOf(value) : ""));

  const children = rows.filter((a) => parentOf(a.area_path) === nav);
  const isLeaf = (path: string) =>
    !rows.some((a) => parentOf(a.area_path) === path);

  const depth = nav ? levelOf(nav) : 0;

  return (
    <div className="flex flex-col">
      <div className="flex min-h-[42px] items-center gap-2 border-b border-border px-3 py-2.5">
        {nav && (
          <button
            type="button"
            aria-label="Volver"
            onClick={() => setNav(parentOf(nav))}
            className="grid size-[26px] place-items-center rounded-md text-muted-foreground hover:bg-neutral-100"
          >
            <ChevronLeft className="size-4" />
          </button>
        )}
        <div className="flex-1 truncate text-xs text-muted-foreground">
          {depth === 0 ? (
            <span>Elegí una Escuela</span>
          ) : (
            <b className="text-foreground">{byPath.get(nav)}</b>
          )}
        </div>
      </div>

      <div className="max-h-[280px] overflow-y-auto p-1.5">
        {children.map((a) => {
          const leaf = isLeaf(a.area_path);
          const selected = leaf && value === a.area_path;
          return (
            <button
              key={a.area_path}
              type="button"
              onClick={() =>
                leaf ? onChange(a.area_path) : setNav(a.area_path)
              }
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2.5 py-2.5 text-left text-sm text-foreground",
                selected ? "bg-primary-tint" : "hover:bg-neutral-100",
              )}
            >
              {leaf && (
                <MapPin className="size-3.5 flex-none text-muted-foreground" />
              )}
              <span className="flex-1 truncate">{a.display_name}</span>
              {!leaf && (
                <ChevronRight className="size-[15px] text-muted-foreground" />
              )}
              {selected && (
                <Check className="size-[15px] text-primary" strokeWidth={2.5} />
              )}
            </button>
          );
        })}
      </div>

      {value && (
        <div className="border-t border-border p-2">
          <button
            type="button"
            onClick={() => onChange(null)}
            className="flex w-full items-center justify-center gap-1.5 rounded-md px-2.5 py-2 text-sm text-destructive hover:bg-neutral-100"
          >
            <X className="size-3.5" />
            Quitar área
          </button>
        </div>
      )}
    </div>
  );
}
