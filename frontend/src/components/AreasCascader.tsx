"use client";

import { useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  MapPin,
  Search,
  X,
} from "lucide-react";

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

function normalize(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
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
  const [query, setQuery] = useState("");

  const isLeaf = (path: string) =>
    !rows.some((a) => parentOf(a.area_path) === path);

  const q = normalize(query.trim());
  const searching = q.length > 0;
  // Search filters only the current level's options, not the whole tree.
  const children = rows.filter((a) => parentOf(a.area_path) === nav);
  const listed = searching
    ? children.filter((a) => normalize(a.display_name).includes(q))
    : children;

  const depth = nav ? levelOf(nav) : 0;

  function goTo(path: string) {
    setNav(path);
    setQuery("");
  }

  function pick(path: string) {
    if (isLeaf(path)) {
      onChange(path);
    } else {
      goTo(path);
    }
  }

  return (
    <div className="flex flex-col">
      <div className="border-border flex items-center gap-2 border-b px-3 py-2">
        <Search className="text-muted-foreground size-4 flex-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar área…"
          className="placeholder:text-muted-foreground flex-1 bg-transparent text-sm outline-none"
        />
        {query && (
          <button
            type="button"
            aria-label="Limpiar búsqueda"
            onClick={() => setQuery("")}
            className="text-muted-foreground grid size-[22px] flex-none place-items-center rounded-md hover:bg-neutral-100"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>

      <div className="border-border flex min-h-[42px] items-center gap-2 border-b px-3 py-2.5">
        {nav && (
          <button
            type="button"
            aria-label="Volver"
            onClick={() => goTo(parentOf(nav))}
            className="text-muted-foreground grid size-[26px] place-items-center rounded-md hover:bg-neutral-100"
          >
            <ChevronLeft className="size-4" />
          </button>
        )}
        <div className="text-muted-foreground flex-1 truncate text-xs">
          {depth === 0 ? (
            <span>Elegí una Escuela</span>
          ) : (
            <b className="text-foreground">{byPath.get(nav)}</b>
          )}
        </div>
      </div>

      <div className="max-h-[280px] overflow-y-auto p-1.5">
        {searching && listed.length === 0 && (
          <div className="text-muted-foreground px-2.5 py-6 text-center text-sm">
            Sin resultados
          </div>
        )}
        {listed.map((a) => {
          const leaf = isLeaf(a.area_path);
          const selected = leaf && value === a.area_path;
          return (
            <button
              key={a.area_path}
              type="button"
              onClick={() => pick(a.area_path)}
              className={cn(
                "text-foreground flex w-full items-center gap-2 rounded-md px-2.5 py-2.5 text-left text-sm",
                selected ? "bg-primary-tint" : "hover:bg-neutral-100",
              )}
            >
              {leaf && (
                <MapPin className="text-muted-foreground size-3.5 flex-none" />
              )}
              <span className="flex-1 truncate">{a.display_name}</span>
              {!leaf && (
                <ChevronRight className="text-muted-foreground size-[15px]" />
              )}
              {selected && (
                <Check className="text-primary size-[15px]" strokeWidth={2.5} />
              )}
            </button>
          );
        })}
      </div>

      {value && (
        <div className="border-border border-t p-2">
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-destructive flex w-full items-center justify-center gap-1.5 rounded-md px-2.5 py-2 text-sm hover:bg-neutral-100"
          >
            <X className="size-3.5" />
            Quitar área
          </button>
        </div>
      )}
    </div>
  );
}
