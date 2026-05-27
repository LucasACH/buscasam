"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

type DraftStateDTO = components["schemas"]["DraftStateDTO"];
export type CoauthorRow = DraftStateDTO["coauthors"][number];

export type CoauthorMutationError =
  | { kind: "already_listed" }
  | { kind: "forbidden" }
  | { kind: "network" };

const draftQueryKey = (docId: number) => ["draft", docId] as const;

export function useCoauthors(docId: number) {
  const qc = useQueryClient();
  const query = useQuery<DraftStateDTO>({
    queryKey: draftQueryKey(docId),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/documents/{doc_id}/draft", {
        params: { path: { doc_id: docId } },
      });
      if (error) throw error;
      if (!data) throw new Error("empty draft state");
      return data;
    },
  });

  function invalidate() {
    qc.invalidateQueries({ queryKey: draftQueryKey(docId) });
  }

  async function invite(
    userId: number,
  ): Promise<CoauthorMutationError | undefined> {
    const { error, response } = await api.POST(
      "/api/documents/{doc_id}/coauthors",
      { params: { path: { doc_id: docId } }, body: { user_id: userId } },
    );
    if (error) {
      if (response?.status === 409) return { kind: "already_listed" };
      if (response?.status === 403) return { kind: "forbidden" };
      return { kind: "network" };
    }
    invalidate();
    return undefined;
  }

  async function revoke(
    userId: number,
  ): Promise<CoauthorMutationError | undefined> {
    const { error, response } = await api.DELETE(
      "/api/documents/{doc_id}/coauthors/{user_id}",
      { params: { path: { doc_id: docId, user_id: userId } } },
    );
    if (error) {
      if (response?.status === 403) return { kind: "forbidden" };
      return { kind: "network" };
    }
    invalidate();
    return undefined;
  }

  return {
    isOwner: query.data?.is_owner ?? false,
    coauthors: query.data?.coauthors,
    isLoading: query.isLoading,
    isError: query.isError,
    invite,
    revoke,
  };
}
