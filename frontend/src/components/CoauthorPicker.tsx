"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Info, Search, X } from "lucide-react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type UserHit = components["schemas"]["UserSearchResult"];

const DEBOUNCE_MS = 250;

async function fetchUsersSearch(q: string): Promise<UserHit[]> {
  const { data, error } = await api.GET("/api/users/search", {
    params: { query: { q } },
  });
  if (error) throw error;
  return data ?? [];
}

export type CoauthorPickerProps = {
  value: number[];
  onChange: (ids: number[]) => void;
  label?: string;
};

export function CoauthorPicker({
  value,
  onChange,
  label = "Coautores",
}: CoauthorPickerProps) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [hintOpen, setHintOpen] = useState(false);
  // Display data for ids the user has picked in this session. Chips are derived
  // from `value`; ids the parent passed but we never saw render as a placeholder.
  const [picked, setPicked] = useState<ReadonlyMap<number, UserHit>>(new Map());

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), query ? DEBOUNCE_MS : 0);
    return () => clearTimeout(t);
  }, [query]);

  const { data: hits } = useQuery({
    queryKey: ["users-search", debounced],
    queryFn: () => fetchUsersSearch(debounced),
    enabled: debounced.length > 0,
  });

  function pick(hit: UserHit) {
    if (value.includes(hit.user_id)) return;
    setPicked((prev) => {
      const next = new Map(prev);
      next.set(hit.user_id, hit);
      return next;
    });
    onChange([...value, hit.user_id]);
    setQuery("");
  }

  function remove(id: number) {
    onChange(value.filter((x) => x !== id));
  }

  const chips = value.map((id) => picked.get(id) ?? placeholder(id));

  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-sm font-medium">
        {label}
        <Tooltip open={hintOpen} onOpenChange={setHintOpen} delayDuration={0}>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label="Más información sobre coautores"
              className="text-muted-foreground hover:text-foreground inline-flex"
              onClick={() => setHintOpen((o) => !o)}
            >
              <Info className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent>
            Sólo se pueden encontrar personas con una cuenta. Si todavía no
            tiene, agregala como coautor externo.
          </TooltipContent>
        </Tooltip>
      </span>
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <input
          aria-label="Coautores"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="border-border-strong bg-card focus:border-primary focus:ring-primary-tint h-10 w-full rounded-lg border pr-3 pl-9 text-sm transition outline-none hover:border-neutral-400 focus:ring-[3px]"
          placeholder="Buscá por nombre…"
        />

        {hits && hits.length > 0 && (
          <ul
            role="listbox"
            className="border-border bg-card absolute top-[calc(100%+4px)] right-0 left-0 z-30 max-h-56 overflow-y-auto rounded-lg border p-1 shadow-md"
          >
            {hits.map((hit) => (
              <li
                key={hit.user_id}
                role="option"
                aria-selected={value.includes(hit.user_id)}
                aria-label={hit.name}
                className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 transition hover:bg-neutral-100"
                onClick={() => pick(hit)}
              >
                <span className="bg-primary-tint text-primary flex size-7 flex-none items-center justify-center rounded-full text-[11px] font-medium">
                  {initials(hit.name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-foreground block truncate text-sm font-medium">
                    {hit.name}
                  </span>
                  <span className="text-muted-foreground block truncate text-[11px]">
                    {hit.email_local}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {chips.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {chips.map((s) => (
            <span
              key={s.user_id}
              className="bg-primary-tint border-primary-tint-2 text-primary inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium"
            >
              {s.name}
              <button
                type="button"
                aria-label={`Quitar ${s.name}`}
                className="text-primary/70 hover:text-primary transition"
                onClick={() => remove(s.user_id)}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </label>
  );
}

function initials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function placeholder(id: number): UserHit {
  return {
    user_id: id,
    name: `Usuario #${id}`,
    email_local: "",
    picture_url: null,
  };
}
