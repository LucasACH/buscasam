"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type InspectMetadata = components["schemas"]["InspectMetadataDTO"];
export type ActionError = "action_failed";

const QUEUE_KEY = ["moderation", "queue"] as const;

export function useInspect(reportId: number) {
  const queryClient = useQueryClient();
  const query = useQuery<InspectMetadata | null>({
    queryKey: ["moderation", "inspect", reportId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/moderation/reports/{report_id}/document",
        { params: { path: { report_id: reportId } } },
      );
      if (error) throw error;
      return data ?? null;
    },
  });

  // Acting resolves every open report on the document, so the inspected entry
  // leaves the queue — invalidate it so the list reflects the resolution.
  async function settle(error: unknown): Promise<ActionError | undefined> {
    if (error) return "action_failed";
    await queryClient.invalidateQueries({ queryKey: QUEUE_KEY });
    return undefined;
  }

  const params = { path: { report_id: reportId } } as const;

  async function hide(reason: string) {
    const { error } = await api.POST(
      "/api/moderation/reports/{report_id}/hide",
      { params, body: { reason } },
    );
    return settle(error);
  }

  async function unhide(reason: string) {
    const { error } = await api.POST(
      "/api/moderation/reports/{report_id}/unhide",
      { params, body: { reason } },
    );
    return settle(error);
  }

  async function dismiss(reason: string) {
    const { error } = await api.POST(
      "/api/moderation/reports/{report_id}/dismiss",
      { params, body: { reason } },
    );
    return settle(error);
  }

  return {
    metadata: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    hide,
    unhide,
    dismiss,
  };
}
