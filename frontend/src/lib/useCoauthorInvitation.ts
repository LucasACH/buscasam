"use client";

import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import {
  NOTIFICATIONS_QUERY_KEY,
  UNREAD_COUNT_QUERY_KEY,
} from "@/lib/useNotifications";

export type InvitationMutationError = { kind: "gone" } | { kind: "network" };

export function useCoauthorInvitation() {
  const qc = useQueryClient();

  function invalidate(docId: number) {
    // Bandeja item transitions to read state; /docs/{id} refetches (full
    // reader view on accept, 404 envelope on decline).
    qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    qc.invalidateQueries({ queryKey: UNREAD_COUNT_QUERY_KEY });
    qc.invalidateQueries({ queryKey: ["doc-detail", docId] });
  }

  async function accept(
    docId: number,
  ): Promise<InvitationMutationError | undefined> {
    const { error, response } = await api.POST(
      "/api/coauthor_invitations/{doc_id}/accept",
      { params: { path: { doc_id: docId } } },
    );
    if (error)
      return response?.status === 404 ? { kind: "gone" } : { kind: "network" };
    invalidate(docId);
    return undefined;
  }

  async function decline(
    docId: number,
  ): Promise<InvitationMutationError | undefined> {
    const { error, response } = await api.POST(
      "/api/coauthor_invitations/{doc_id}/decline",
      { params: { path: { doc_id: docId } } },
    );
    if (error)
      return response?.status === 404 ? { kind: "gone" } : { kind: "network" };
    invalidate(docId);
    return undefined;
  }

  return { accept, decline };
}
