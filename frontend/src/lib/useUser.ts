"use client";

import { useQuery } from "@tanstack/react-query";

export type User = {
  user_id: number;
  role: "estudiante" | "docente";
  name: string;
  picture_url: string | null;
  hd: string;
};

export const ME_QUERY_KEY = ["me"] as const;

async function fetchMe(): Promise<User | null> {
  const r = await fetch("/api/me", { credentials: "same-origin" });
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(`/api/me ${r.status}`);
  return (await r.json()) as User;
}

export function useUser() {
  const query = useQuery<User | null>({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  });
  return {
    user: query.data ?? null,
    isInvitado: !query.isLoading && (query.data ?? null) === null,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
