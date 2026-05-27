"use client";

import { useQuery } from "@tanstack/react-query";

export type AuthorDisplay = {
  display_name: string;
  user_id: number | null;
};

export type MainFile = {
  original_filename: string;
  size_bytes: number;
  mime: string;
};

export type Attachment = {
  id: number;
  original_filename: string;
  size_bytes: number;
  mime: string | null;
};

export type DocDetail = {
  doc_id: number;
  titulo: string;
  autores: AuthorDisplay[];
  area_path: string;
  tipo: string;
  fecha: string | null;
  visibility: string;
  abstract: string;
  palabras_clave: string[];
  archivo_principal: MainFile;
  adjuntos: Attachment[];
  manageable: boolean;
};

class HttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function fetchDocDetail(docId: number): Promise<DocDetail> {
  const r = await fetch(`/api/docs/${docId}`, { credentials: "same-origin" });
  if (!r.ok) throw new HttpError(r.status);
  return (await r.json()) as DocDetail;
}

export function useDocDetail(docId: number) {
  const query = useQuery<DocDetail, HttpError>({
    queryKey: ["doc-detail", docId],
    queryFn: () => fetchDocDetail(docId),
    retry: (failureCount, err) => err.status !== 404 && failureCount < 3,
  });
  const is404 = query.isError && query.error?.status === 404;
  return {
    detail: query.data,
    isLoading: query.isLoading,
    isError: query.isError && !is404,
    is404,
  };
}
