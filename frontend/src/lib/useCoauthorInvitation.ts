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

  function invalidate() {
    // Bandeja item transitions to read state. The /docs/{id} surface is SSR
    // (no TanStack query): CoauthorInvitationBanner triggers router.refresh()
    // on its own after the mutation resolves.
    qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    qc.invalidateQueries({ queryKey: UNREAD_COUNT_QUERY_KEY });
  }

  async function accept(
    docId: number,
  ): Promise<InvitationMutationError | undefined> {
    const { error, response } = await api.POST(
      "/api/coauthor_invitations/{doc_id}/accept",
      { params: { path: { doc_id: docId } } },
    );
    if (error && response?.status !== 404) return { kind: "network" };
    // Success or a 404 (row already transitioned / revoked) both mean the
    // server truth moved: refresh so the stale invite leaves its actionable
    // state instead of dead-ending on repeat 404s.
    invalidate();
    return error ? { kind: "gone" } : undefined;
  }

  async function decline(
    docId: number,
  ): Promise<InvitationMutationError | undefined> {
    const { error, response } = await api.POST(
      "/api/coauthor_invitations/{doc_id}/decline",
      { params: { path: { doc_id: docId } } },
    );
    if (error && response?.status !== 404) return { kind: "network" };
    invalidate();
    return error ? { kind: "gone" } : undefined;
  }

  return { accept, decline };
}
