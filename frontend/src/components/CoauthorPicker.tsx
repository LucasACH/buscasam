"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

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
      <span className="text-sm font-medium">{label}</span>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          aria-label="Coautores"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="h-10 w-full rounded-lg border border-border-strong bg-card pl-9 pr-3 text-sm outline-none hover:border-neutral-400 focus:border-primary focus:ring-[3px] focus:ring-primary-tint transition"
          placeholder="Buscá por nombre…"
        />

        {hits && hits.length > 0 && (
          <ul
            role="listbox"
            className="absolute left-0 right-0 top-[calc(100%+4px)] z-30 max-h-56 overflow-y-auto rounded-lg border border-border bg-card p-1 shadow-md"
          >
            {hits.map((hit) => (
              <li
                key={hit.user_id}
                role="option"
                aria-selected={value.includes(hit.user_id)}
                aria-label={hit.name}
                className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 hover:bg-neutral-100 transition"
                onClick={() => pick(hit)}
              >
                <span className="flex size-7 flex-none items-center justify-center rounded-full bg-primary-tint text-[11px] font-medium text-primary">
                  {initials(hit.name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {hit.name}
                  </span>
                  <span className="block truncate text-[11px] text-muted-foreground">
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
              className="inline-flex items-center gap-1 rounded-full bg-primary-tint border border-primary-tint-2 px-2.5 py-0.5 text-xs font-medium text-primary"
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
  return { user_id: id, name: `Usuario #${id}`, email_local: "", picture_url: null };
}
