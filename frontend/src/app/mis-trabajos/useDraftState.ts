"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type DraftStateDTO = components["schemas"]["DraftStateDTO"];

export const POLL_INTERVAL_MS = 3000;

function shouldPoll(state: DraftStateDTO | undefined): boolean {
  return (
    state?.index_status === "processing" ||
    state?.publish_gate_reason === "reindexing_headline"
  );
}

export function useDraftState(docId: number) {
  const query = useQuery<DraftStateDTO>({
    queryKey: ["draft", docId],
    refetchInterval: (q) => (shouldPoll(q.state.data) ? POLL_INTERVAL_MS : false),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/documents/{doc_id}/draft", {
        params: { path: { doc_id: docId } },
      });
      if (error) throw error;
      if (!data) throw new Error("empty draft state");
      return data;
    },
  });
  return {
    state: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
