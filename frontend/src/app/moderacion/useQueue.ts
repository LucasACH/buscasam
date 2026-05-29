"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type QueueEntry = components["schemas"]["QueueEntryDTO"];

const QUEUE_KEY = ["moderation", "queue"] as const;

export function useQueue(enabled: boolean) {
  const query = useQuery<QueueEntry[]>({
    queryKey: QUEUE_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/moderation/queue");
      if (error) throw error;
      return data?.items ?? [];
    },
    enabled,
  });
  return { entries: query.data ?? [], isLoading: query.isLoading };
}
