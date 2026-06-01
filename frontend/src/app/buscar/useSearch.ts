"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components, operations } from "@/api/schema";

type SearchQuery = NonNullable<
  operations["search_endpoint_api_search_get"]["parameters"]["query"]
>;
export type Tipo = NonNullable<SearchQuery["tipo"]>[number];
export type Orden = NonNullable<SearchQuery["orden"]>;

export type SearchParams = {
  q: string;
  pagina: number;
  area: string | null;
  tipos: Tipo[];
  desde: number | null;
  hasta: number | null;
  orden: Orden;
};

export type SearchResponse = components["schemas"]["SearchResponse"];

export function useSearch(params: SearchParams) {
  const enabled = params.q.length > 0 || params.orden === "recientes";
  const query = useQuery<SearchResponse>({
    queryKey: [
      "search",
      params.q,
      params.pagina,
      params.area,
      params.tipos,
      params.desde,
      params.hasta,
      params.orden,
    ],
    enabled,
    queryFn: async () => {
      const search: SearchQuery = {
        q: params.q,
        pagina: params.pagina,
        orden: params.orden,
      };
      if (params.area) search.area = params.area;
      if (params.tipos.length) search.tipo = params.tipos;
      if (params.desde !== null) search.desde = params.desde;
      if (params.hasta !== null) search.hasta = params.hasta;
      const { data, error } = await api.GET("/api/search", {
        params: { query: search },
      });
      if (error) throw error;
      if (!data) throw new Error("empty search response");
      return data;
    },
  });
  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
