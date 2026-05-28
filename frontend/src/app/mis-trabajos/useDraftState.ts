"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

type DraftStateDTO = components["schemas"]["DraftStateDTO"];
export type DraftAttachment = DraftStateDTO["attachments"][number];
export type DraftVersion = DraftStateDTO["versions"][number];
type CandidateDTO = NonNullable<DraftStateDTO["candidate"]>;

export type Candidate = {
  status: CandidateDTO["status"];
  statusLabel: string;
  stagedAbstract: CandidateDTO["staged_abstract"];
  stagedKeywords: CandidateDTO["staged_keywords"];
  stagedFecha: CandidateDTO["staged_fecha"];
  canPublish: boolean;
  canDiscard: boolean;
  error: string | null;
};

export type DraftState = {
  title: DraftStateDTO["title"];
  staged_abstract: DraftStateDTO["staged_abstract"];
  staged_keywords: DraftStateDTO["staged_keywords"];
  staged_fecha: DraftStateDTO["staged_fecha"];
  lifecycle: {
    formSeedKey: string;
    statusLabel: string;
    showSuggestionsSpinner: boolean;
    gateMessage: string | null;
    canPublish: boolean;
  };
  isOwner: boolean;
  candidate: Candidate | null;
  versions: DraftVersion[];
};

export type AttachmentMutationError =
  | "too_large"
  | "unsupported_type"
  | "upload_failed"
  | "remove_failed";

export type ReplaceMutationError =
  | "too_large"
  | "unsupported_type"
  | "no_published_version"
  | "replace_failed";

export type DiscardMutationError = "discard_failed";

export const POLL_INTERVAL_MS = 3000;

const MAX_ATTACHMENTS = 5;

const STATUS_PILL: Record<string, string> = {
  pending: "Procesando…",
  processing: "Procesando…",
  indexed: "Listo para publicar",
  failed: "Falló el procesamiento",
};

const GATE_COPY: Record<string, string> = {
  processing: "Procesando…",
  reindexing_headline: "Reindexando título…",
  processing_failed: "Falló el procesamiento — revisá tu archivo",
};

const CANDIDATE_STATUS_LABEL: Record<Candidate["status"], string> = {
  processing: "Procesando…",
  ready: "Listo para publicar",
  failed: "Falló el procesamiento",
};

const draftQueryKey = (docId: number) => ["draft", docId] as const;

function shouldPoll(state: DraftStateDTO | undefined): boolean {
  return (
    state?.index_status === "processing" ||
    state?.publish_gate_reason === "reindexing_headline" ||
    state?.candidate?.status === "processing"
  );
}

function projectCandidate(c: CandidateDTO): Candidate {
  return {
    status: c.status,
    statusLabel: CANDIDATE_STATUS_LABEL[c.status],
    stagedAbstract: c.staged_abstract,
    stagedKeywords: c.staged_keywords,
    stagedFecha: c.staged_fecha,
    canPublish: c.can_publish,
    canDiscard: c.can_discard,
    error: c.error,
  };
}

function useDraftQuery(docId: number) {
  return useQuery<DraftStateDTO>({
    queryKey: draftQueryKey(docId),
    refetchInterval: (q) =>
      shouldPoll(q.state.data) ? POLL_INTERVAL_MS : false,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/documents/{doc_id}/draft", {
        params: { path: { doc_id: docId } },
      });
      if (error) throw error;
      if (!data) throw new Error("empty draft state");
      return data;
    },
  });
}

function projectDraftState(state: DraftStateDTO): DraftState {
  return {
    title: state.title,
    staged_abstract: state.staged_abstract,
    staged_keywords: state.staged_keywords,
    staged_fecha: state.staged_fecha,
    lifecycle: {
      formSeedKey: state.index_status,
      statusLabel: STATUS_PILL[state.index_status] ?? state.index_status,
      showSuggestionsSpinner: state.index_status === "processing",
      gateMessage: state.publish_gate_reason
        ? (GATE_COPY[state.publish_gate_reason] ?? state.publish_gate_reason)
        : null,
      canPublish: state.publish_gate_reason === null && state.is_owner,
    },
    isOwner: state.is_owner,
    candidate: state.candidate ? projectCandidate(state.candidate) : null,
    versions: state.versions,
  };
}

export function useDraftState(docId: number) {
  const query = useDraftQuery(docId);
  const queryClient = useQueryClient();

  async function replace(
    file: File,
  ): Promise<ReplaceMutationError | undefined> {
    // Generated multipart bodies model the file as a string placeholder, so
    // the runtime File upload stays a direct browser request to FastAPI.
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`/api/documents/${docId}/replace`, {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    if (response.status === 413) return "too_large";
    if (response.status === 415) return "unsupported_type";
    if (response.status === 409) return "no_published_version";
    if (response.status !== 202) return "replace_failed";
    // Optimistically poke the panel into its processing state; the next poll
    // picks up the real candidate row.
    await queryClient.invalidateQueries({ queryKey: draftQueryKey(docId) });
    return undefined;
  }

  async function discard(): Promise<DiscardMutationError | undefined> {
    // Optimistically drop the candidate so the panel snaps back to the
    // no-candidate state (Reemplazar re-enabled) without waiting for a poll.
    queryClient.setQueryData<DraftStateDTO>(draftQueryKey(docId), (current) =>
      current ? { ...current, candidate: null } : current,
    );
    const { error, response } = await api.DELETE(
      "/api/documents/{doc_id}/candidate",
      { params: { path: { doc_id: docId } } },
    );
    if (error) {
      // 404 is a race — the candidate was already discarded/published. The
      // optimistic removal already reflects that; just re-sync. Any other
      // failure also re-syncs so the panel matches the server.
      await queryClient.invalidateQueries({ queryKey: draftQueryKey(docId) });
      if (response?.status === 404) return undefined;
      return "discard_failed";
    }
    return undefined;
  }

  return {
    state: query.data ? projectDraftState(query.data) : undefined,
    isLoading: query.isLoading,
    isError: query.isError,
    refresh: async () => {
      await queryClient.invalidateQueries({ queryKey: draftQueryKey(docId) });
    },
    replace,
    discard,
  };
}

export function useDraftAttachments(docId: number) {
  const query = useDraftQuery(docId);
  const queryClient = useQueryClient();
  const attachments = query.data?.attachments ?? [];

  function updateAttachments(
    update: (current: DraftAttachment[]) => DraftAttachment[],
  ) {
    queryClient.setQueryData<DraftStateDTO>(draftQueryKey(docId), (current) =>
      current
        ? { ...current, attachments: update(current.attachments) }
        : current,
    );
  }

  async function addAttachment(
    file: File,
  ): Promise<AttachmentMutationError | undefined> {
    // Generated multipart bodies model the file as a string placeholder, so
    // runtime File upload stays a direct browser request to FastAPI.
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`/api/documents/${docId}/attachments`, {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    if (response.status === 413) return "too_large";
    if (response.status === 415) return "unsupported_type";
    if (response.status !== 201) return "upload_failed";

    const created = (await response.json()) as DraftAttachment;
    updateAttachments((current) => [...current, created]);
    return undefined;
  }

  async function removeAttachment(
    attachment: DraftAttachment,
  ): Promise<AttachmentMutationError | undefined> {
    updateAttachments((current) =>
      current.filter((item) => item.id !== attachment.id),
    );
    const { error } = await api.DELETE(
      "/api/documents/{doc_id}/attachments/{att_id}",
      { params: { path: { doc_id: docId, att_id: attachment.id } } },
    );
    if (error) {
      updateAttachments((current) =>
        current.some((item) => item.id === attachment.id)
          ? current
          : [...current, attachment],
      );
      return "remove_failed";
    }
    return undefined;
  }

  return {
    attachments,
    atCapacity: attachments.length >= MAX_ATTACHMENTS,
    addAttachment,
    removeAttachment,
  };
}
