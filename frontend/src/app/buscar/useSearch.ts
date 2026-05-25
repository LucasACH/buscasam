"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type SearchParams = {
  q: string;
  pagina: number;
};

export type SearchResponse = components["schemas"]["SearchResponse"];

export function useSearch(params: SearchParams) {
  const enabled = params.q.length > 0;
  const query = useQuery<SearchResponse>({
    queryKey: ["search", params.q, params.pagina],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/search", {
        params: { query: { q: params.q, pagina: params.pagina } },
      });
      if (error) throw error;
      return data!;
    },
  });
  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    isLexicalFallback: query.data?.lexical_fallback ?? false,
  };
}
