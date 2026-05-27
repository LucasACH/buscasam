"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type Related = components["schemas"]["RelatedDTO"];

class HttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function fetchRelated(docId: number): Promise<Related[]> {
  const { data, response } = await api.GET("/api/docs/{doc_id}/related", {
    params: { path: { doc_id: docId } },
  });
  if (!response.ok) throw new HttpError(response.status);
  return data ?? [];
}

export function useRelated(docId: number) {
  const query = useQuery<Related[], HttpError>({
    queryKey: ["doc-related", docId],
    queryFn: () => fetchRelated(docId),
    retry: (failureCount, err) => err.status !== 404 && failureCount < 3,
  });
  return {
    related: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
