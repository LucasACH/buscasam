"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, X } from "lucide-react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { AreasCascader } from "@/components/AreasCascader";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

import { TIPO_LABEL } from "./ResultCard";
import type { Orden, Tipo } from "./useSearch";

type Area = components["schemas"]["AreaDTO"];

const TIPO_VALUES = Object.keys(TIPO_LABEL) as Tipo[];

export type FilterPatch = {
  area?: string | null;
  tipos?: Tipo[];
  desde?: number | null;
  hasta?: number | null;
  orden?: Orden;
};

export type SearchFiltersProps = {
  area: string | null;
  tipos: Tipo[];
  desde: number | null;
  hasta: number | null;
  orden: Orden;
  onChange: (patch: FilterPatch) => void;
};

async function fetchAreas(): Promise<Area[]> {
  const { data, error } = await api.GET("/api/areas");
  if (error) throw error;
  return data ?? [];
}

function useAreaLabel(area: string | null): string | null {
  const { data } = useQuery({ queryKey: ["areas"], queryFn: fetchAreas });
  if (!area) return null;
  const byPath = new Map((data ?? []).map((a) => [a.area_path, a.display_name]));
  const segments = area.split(".");
  return segments
    .map((_, i) => byPath.get(segments.slice(0, i + 1).join(".")) ?? segments[i])
    .join(" › ");
}

export function SearchFilters({
  area,
  tipos,
  desde,
  hasta,
  orden,
  onChange,
}: SearchFiltersProps) {
  const areaLabel = useAreaLabel(area);
  const hasFilters =
    area !== null || tipos.length > 0 || desde !== null || hasta !== null;

  function toggleTipo(t: Tipo) {
    onChange({
      tipos: tipos.includes(t)
        ? tipos.filter((x) => x !== t)
        : [...tipos, t],
    });
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {/* Orden */}
      <div className="bg-muted inline-flex rounded-lg p-0.5">
        {(["relevancia", "recientes"] as const).map((o) => (
          <Button
            key={o}
            type="button"
            variant={orden === o ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={orden === o}
            onClick={() => onChange({ orden: o })}
          >
            {o === "relevancia" ? "Relevancia" : "Recientes"}
          </Button>
        ))}
      </div>

      {/* Área */}
      <Popover>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm">
            {areaLabel ?? "Área"}
            <ChevronDown data-icon="inline-end" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72 p-3">
          <AreasCascader
            key={area ?? "none"}
            value={area}
            onChange={(a) => onChange({ area: a })}
          />
          {area && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={() => onChange({ area: null })}
            >
              Quitar área
            </Button>
          )}
        </PopoverContent>
      </Popover>

      {/* Tipo */}
      <Popover>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm">
            {tipos.length ? `Tipo (${tipos.length})` : "Tipo"}
            <ChevronDown data-icon="inline-end" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-1">
          {TIPO_VALUES.map((t) => {
            const checked = tipos.includes(t);
            return (
              <button
                key={t}
                type="button"
                role="menuitemcheckbox"
                aria-checked={checked}
                onClick={() => toggleTipo(t)}
                className="hover:bg-muted flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm"
              >
                <span className="border-input flex size-4 items-center justify-center rounded border">
                  {checked && <Check className="size-3" />}
                </span>
                {TIPO_LABEL[t]}
              </button>
            );
          })}
        </PopoverContent>
      </Popover>

      {/* Año */}
      <Popover>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm">
            {desde || hasta
              ? `Año ${desde ?? "…"}–${hasta ?? "…"}`
              : "Año"}
            <ChevronDown data-icon="inline-end" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-56 p-3">
          <div className="flex items-center gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs">
              <span className="text-muted-foreground">Desde</span>
              <input
                type="number"
                inputMode="numeric"
                min={1000}
                max={9999}
                placeholder="1990"
                value={desde ?? ""}
                onChange={(e) =>
                  onChange({
                    desde: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              />
            </label>
            <label className="flex flex-1 flex-col gap-1 text-xs">
              <span className="text-muted-foreground">Hasta</span>
              <input
                type="number"
                inputMode="numeric"
                min={1000}
                max={9999}
                placeholder="2026"
                value={hasta ?? ""}
                onChange={(e) =>
                  onChange({
                    hasta: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              />
            </label>
          </div>
        </PopoverContent>
      </Popover>

      {hasFilters && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() =>
            onChange({ area: null, tipos: [], desde: null, hasta: null })
          }
        >
          Limpiar
          <X data-icon="inline-end" />
        </Button>
      )}
    </div>
  );
}
