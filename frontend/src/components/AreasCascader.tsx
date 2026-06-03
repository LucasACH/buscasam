"use client";

import { useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
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

function isMateria(area_path: string): boolean {
  return area_path.split(".").pop()!.startsWith("materia_");
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

// Drill-down Escuela › Área › Carrera › Materia cascader. Only Materias (the
// leaves) are selectable; branch rows drill into their children. The search
// placeholder names the level being shown, indexed by drill depth.
const SEARCH_PLACEHOLDER = [
  "Buscar escuela…",
  "Buscar área…",
  "Buscar carrera…",
  "Buscar materia…",
];

const REPORT_URL =
  "https://github.com/LucasACH/buscasam/issues/new?title=" +
  encodeURIComponent("Falta una escuela, área, carrera o materia") +
  "&body=" +
  encodeURIComponent(
    "Indicá qué falta y dónde debería ubicarse:\n\n" +
      "- Escuela:\n- Área:\n- Carrera:\n- Materia:\n\n" +
      "Detalle adicional:\n",
  );

export function AreasCascader({ onChange, value }: AreasCascaderProps) {
  const { data } = useAreas();
  // Only Materias are selectable; prune branches that lead to none (e.g. a
  // Carrera with no Materia) so they never surface as dead-end leaves.
  const keep = new Set<string>();
  for (const a of data ?? []) {
    if (!isMateria(a.area_path)) continue;
    const parts = a.area_path.split(".");
    for (let i = 1; i <= parts.length; i++)
      keep.add(parts.slice(0, i).join("."));
  }
  const rows = (data ?? []).filter((a) => keep.has(a.area_path));
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
          placeholder={SEARCH_PLACEHOLDER[depth] ?? "Buscar…"}
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

      <div className="border-border border-t px-3 py-2">
        <a
          href={REPORT_URL}
          target="_blank"
          rel="noreferrer"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-xs"
        >
          <ExternalLink className="size-3.5 flex-none" />
          ¿Falta una escuela, área, carrera o materia? Reportala
        </a>
      </div>
    </div>
  );
}
