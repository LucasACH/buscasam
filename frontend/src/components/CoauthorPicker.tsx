"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

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
};

export function CoauthorPicker({ value, onChange }: CoauthorPickerProps) {
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
    <label className="flex flex-col gap-1 text-sm">
      <span>Coautores</span>
      <input
        aria-label="Coautores"
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="border-input bg-background h-9 rounded-md border px-2"
        placeholder="Buscá por nombre…"
      />

      {hits && hits.length > 0 && (
        <ul role="listbox" className="border-input rounded-md border">
          {hits.map((hit) => (
            <li
              key={hit.user_id}
              role="option"
              aria-selected={value.includes(hit.user_id)}
              aria-label={hit.name}
              className="hover:bg-muted cursor-pointer px-2 py-1"
              onClick={() => pick(hit)}
            >
              {hit.name} · {hit.email_local}
            </li>
          ))}
        </ul>
      )}

      {chips.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {chips.map((s) => (
            <span
              key={s.user_id}
              className="bg-muted inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs"
            >
              {s.name}
              <button
                type="button"
                aria-label={`Quitar ${s.name}`}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => remove(s.user_id)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </label>
  );
}

function placeholder(id: number): UserHit {
  return { user_id: id, name: `Usuario #${id}`, email_local: "", picture_url: null };
}
