"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Calendar, Check, ChevronDown, Layers, X } from "lucide-react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { AreasCascader } from "@/components/AreasCascader";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const FILTER_BASE =
  "inline-flex h-8 items-center gap-1.5 rounded-lg border bg-card px-2.5 text-[13px] font-medium transition-colors";
const FILTER_IDLE =
  "border-border-strong text-foreground hover:border-neutral-400 hover:bg-neutral-50";
const FILTER_SET = "border-primary bg-primary-tint text-primary-hover";

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
  const [areaOpen, setAreaOpen] = useState(false);
  const [desdeInput, setDesdeInput] = useState(desde?.toString() ?? "");
  const [hastaInput, setHastaInput] = useState(hasta?.toString() ?? "");
  const hasFilters =
    area !== null || tipos.length > 0 || desde !== null || hasta !== null;

  useEffect(() => setDesdeInput(desde?.toString() ?? ""), [desde]);
  useEffect(() => setHastaInput(hasta?.toString() ?? ""), [hasta]);

  function commitYear(key: "desde" | "hasta", raw: string) {
    const n = Number(raw);
    const valid = raw && Number.isInteger(n) && n >= 1000 && n <= 9999;
    onChange({ [key]: valid ? n : null });
  }

  function toggleTipo(t: Tipo) {
    onChange({
      tipos: tipos.includes(t)
        ? tipos.filter((x) => x !== t)
        : [...tipos, t],
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Orden */}
      <div className="border-border bg-neutral-100 inline-flex gap-0.5 rounded-lg border p-[3px]">
        {(["relevancia", "recientes"] as const).map((o) => (
          <button
            key={o}
            type="button"
            aria-pressed={orden === o}
            onClick={() => onChange({ orden: o })}
            className={cn(
              "rounded-[7px] px-3.5 py-[7px] text-[13px] tracking-tight transition-all",
              orden === o
                ? "bg-card text-primary font-semibold shadow-[0_1px_2px_rgba(23,23,23,0.06)]"
                : "text-muted-foreground hover:text-foreground font-medium",
            )}
          >
            {o === "relevancia" ? "Relevancia" : "Recientes"}
          </button>
        ))}
      </div>

      {/* Área */}
      <Popover open={areaOpen} onOpenChange={setAreaOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(FILTER_BASE, area ? FILTER_SET : FILTER_IDLE)}
          >
            <Layers className="size-[15px]" />
            <span className="max-w-[180px] truncate">
              {areaLabel ?? "Área"}
            </span>
            <ChevronDown className="size-3.5 opacity-70" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[300px] overflow-hidden p-0">
          <AreasCascader
            key={area ?? "none"}
            value={area}
            onChange={(a) => {
              onChange({ area: a });
              setAreaOpen(false);
            }}
          />
        </PopoverContent>
      </Popover>

      {/* Tipo */}
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(FILTER_BASE, tipos.length ? FILTER_SET : FILTER_IDLE)}
          >
            Tipo
            {tipos.length > 0 && (
              <span className="bg-primary inline-grid h-[17px] min-w-[17px] place-items-center rounded-full px-1 text-[11px] font-bold text-white">
                {tipos.length}
              </span>
            )}
            <ChevronDown className="size-3.5 opacity-70" />
          </button>
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
                className="hover:bg-neutral-100 flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm"
              >
                <span
                  className={cn(
                    "flex size-[17px] items-center justify-center rounded-[5px] border-[1.5px] transition-colors",
                    checked
                      ? "border-primary bg-primary text-white"
                      : "border-border-strong",
                  )}
                >
                  {checked && <Check className="size-3" strokeWidth={3} />}
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
          <button
            type="button"
            className={cn(
              FILTER_BASE,
              desde || hasta ? FILTER_SET : FILTER_IDLE,
            )}
          >
            <Calendar className="size-[15px]" />
            {desde || hasta ? `${desde ?? "…"}–${hasta ?? "…"}` : "Año"}
            <ChevronDown className="size-3.5 opacity-70" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-56 p-3">
          <div className="flex items-center gap-2.5">
            <label className="flex flex-1 flex-col gap-1.5 text-xs">
              <span className="text-foreground font-medium">Desde</span>
              <input
                type="number"
                inputMode="numeric"
                min={1000}
                max={9999}
                placeholder="1990"
                value={desdeInput}
                onChange={(e) => setDesdeInput(e.target.value)}
                onBlur={(e) => commitYear("desde", e.target.value)}
                className="border-border-strong bg-background focus:border-primary focus:ring-primary-tint h-9 rounded-lg border px-2.5 text-sm outline-none focus:ring-[3px]"
              />
            </label>
            <label className="flex flex-1 flex-col gap-1.5 text-xs">
              <span className="text-foreground font-medium">Hasta</span>
              <input
                type="number"
                inputMode="numeric"
                min={1000}
                max={9999}
                placeholder="2026"
                value={hastaInput}
                onChange={(e) => setHastaInput(e.target.value)}
                onBlur={(e) => commitYear("hasta", e.target.value)}
                className="border-border-strong bg-background focus:border-primary focus:ring-primary-tint h-9 rounded-lg border px-2.5 text-sm outline-none focus:ring-[3px]"
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
          <X data-icon="inline-start" />
          Limpiar
        </Button>
      )}
    </div>
  );
}
