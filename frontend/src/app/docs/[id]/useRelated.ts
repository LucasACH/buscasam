"use client";

import { useQuery } from "@tanstack/react-query";

import type { AuthorDisplay } from "./types";

export type Related = {
  doc_id: number;
  titulo: string;
  autores: AuthorDisplay[];
  area_path: string;
  tipo: string;
  fecha: string | null;
};

class HttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function fetchRelated(docId: number): Promise<Related[]> {
  const r = await fetch(`/api/docs/${docId}/related`, {
    credentials: "same-origin",
  });
  if (!r.ok) throw new HttpError(r.status);
  return (await r.json()) as Related[];
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
