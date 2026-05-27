"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

type UserHit = {
  user_id: number;
  name: string;
  email_local: string;
  picture_url: string | null;
};

const DEBOUNCE_MS = 250;

async function fetchUsersSearch(q: string): Promise<UserHit[]> {
  const r = await fetch(`/api/users/search?q=${encodeURIComponent(q)}`, {
    credentials: "same-origin",
  });
  if (!r.ok) throw new Error(`/api/users/search ${r.status}`);
  return (await r.json()) as UserHit[];
}

export type CoauthorPickerProps = {
  value: number[];
  onChange: (ids: number[]) => void;
};

export function CoauthorPicker({ value, onChange }: CoauthorPickerProps) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selected, setSelected] = useState<UserHit[]>([]);

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
    const nextIds = [...value, hit.user_id];
    const nextSelected = [...selected, hit];
    setSelected(nextSelected);
    onChange(nextIds);
    setQuery("");
  }

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

      {selected.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {selected.map((s) => (
            <span
              key={s.user_id}
              className="bg-muted inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs"
            >
              {s.name}
              <button
                type="button"
                aria-label={`Quitar ${s.name}`}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => {
                  const nextSelected = selected.filter((x) => x.user_id !== s.user_id);
                  setSelected(nextSelected);
                  onChange(value.filter((id) => id !== s.user_id));
                }}
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
