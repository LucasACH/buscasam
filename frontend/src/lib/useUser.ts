"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type User = components["schemas"]["MeResponse"];

export const ME_QUERY_KEY = ["me"] as const;

async function fetchMe(): Promise<User | null> {
  const { data, response } = await api.GET("/api/me");
  // 401 is the documented unauthenticated state — surfaced as `null`
  // (→ invitado), not an error. Any other non-2xx propagates.
  if (response.status === 401) return null;
  if (!response.ok) throw new Error(`/api/me ${response.status}`);
  return data ?? null;
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
    // Only treat the user as invitado on a confirmed 401 (data === null).
    // Errors propagate via `isError` — the network being down is not the
    // same as the server saying "no session".
    isInvitado: !query.isLoading && !query.isError && query.data === null,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
