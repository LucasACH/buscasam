"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

type DeletedDocDTO = components["schemas"]["DeletedDocDTO"];

export type DeletedDoc = {
  id: number;
  title: string;
  daysRemaining: number;
};

export type RestoreMutationError = "restore_failed";

const DELETED_KEY = ["me", "documents", "deleted"] as const;
const MS_PER_DAY = 1000 * 60 * 60 * 24;

// Days until purge, derived client-side by diffing purge_at against now — the
// 180-día retention constant stays server-side in the purge_at projection. Ceil
// so the countdown only reads "0 días" once the purge instant has passed.
function daysRemaining(purgeAt: string, now: number): number {
  return Math.max(0, Math.ceil((new Date(purgeAt).getTime() - now) / MS_PER_DAY));
}

function project(dto: DeletedDocDTO, now: number): DeletedDoc {
  return {
    id: dto.id,
    title: dto.title,
    daysRemaining: daysRemaining(dto.purge_at, now),
  };
}

export function useDeletedDocuments() {
  const queryClient = useQueryClient();
  const query = useQuery<DeletedDocDTO[]>({
    queryKey: DELETED_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/me/documents/deleted");
      if (error) throw error;
      return data ?? [];
    },
  });

  async function restore(
    id: number,
  ): Promise<RestoreMutationError | undefined> {
    const { error } = await api.POST("/api/documents/{doc_id}/restore", {
      params: { path: { doc_id: id } },
    });
    if (error) return "restore_failed";
    // The restored doc leaves the Papelera and returns to Mis trabajos.
    await queryClient.invalidateQueries({ queryKey: DELETED_KEY });
    await queryClient.invalidateQueries({ queryKey: ["me", "documents"] });
    return undefined;
  }

  // Captured once on mount (lazy initializer keeps the impure read off the
  // pure render path); a refetch/remount recomputes the day counts.
  const [now] = useState(() => Date.now());
  return {
    documents: (query.data ?? []).map((d) => project(d, now)),
    isLoading: query.isLoading,
    isError: query.isError,
    restore,
  };
}
