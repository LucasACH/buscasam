"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type PopularResult = components["schemas"]["PopularResultDTO"];
type PopularResponse = components["schemas"]["PopularResponse"];

export function useMostRead() {
  const query = useQuery<PopularResponse>({
    queryKey: ["popular"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/docs/popular");
      if (error) throw error;
      if (!data) throw new Error("empty popular response");
      return data;
    },
  });
  return {
    results: query.data?.results ?? [],
    publicTotal: query.data?.public_total ?? 0,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
