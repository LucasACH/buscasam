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
  stage: CandidateDTO["index_stage"];
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
  generated_abstract: DraftStateDTO["generated_abstract"];
  generated_keywords: DraftStateDTO["generated_keywords"];
  generated_fecha: DraftStateDTO["generated_fecha"];
  lifecycle: {
    formSeedKey: string;
    statusLabel: string;
    stage: DraftStateDTO["index_stage"];
    queued: boolean;
    showSuggestionsSpinner: boolean;
    gateMessage: string | null;
    canPublish: boolean;
    initialPhase: "indexing" | "failed" | "ready";
  };
  isOwner: boolean;
  visibility: DraftStateDTO["visibility"];
  area_path: DraftStateDTO["area_path"];
  candidate: Candidate | null;
  versions: DraftVersion[];
  attachments: DraftAttachment[];
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

export type PublishMutationResult =
  | "published"
  | "refreshed"
  | "publish_failed";

export type DiscardMutationError = "discard_failed";

export type SoftDeleteMutationError = "delete_failed";

export type DraftWorkspaceActions = {
  publish: () => Promise<PublishMutationResult>;
  replace: (file: File) => Promise<ReplaceMutationError | undefined>;
  discard: () => Promise<DiscardMutationError | undefined>;
  softDelete: () => Promise<SoftDeleteMutationError | undefined>;
  attachments: {
    add: (file: File) => Promise<AttachmentMutationError | undefined>;
    remove: (
      attachment: DraftAttachment,
    ) => Promise<AttachmentMutationError | undefined>;
  };
};

// Only used while shouldPoll() is true (pending/processing/reindexing), so this
// is the active-processing cadence — kept snappy so progress checkpoints surface
// promptly rather than lagging a step behind.
export const POLL_INTERVAL_MS = 1500;

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
    // A freshly created draft starts at "pending" before the worker picks it
    // up; the editar page blocks on it (initialPhase === "indexing"), so we
    // must poll it too or the loader never clears.
    state?.index_status === "pending" ||
    state?.index_status === "processing" ||
    state?.publish_gate_reason === "reindexing_headline" ||
    state?.candidate?.status === "processing"
  );
}

function projectCandidate(c: CandidateDTO): Candidate {
  return {
    status: c.status,
    statusLabel: CANDIDATE_STATUS_LABEL[c.status],
    stage: c.index_stage,
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
    // The indexing copy invites the author to close the tab and come back;
    // keep polling while backgrounded so the page reflects live progress on
    // return instead of freezing at the last foreground poll.
    refetchIntervalInBackground: true,
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

// The initial-publication path blocks the whole edit page until the first
// version finishes indexing; once any published version exists the page is
// driven by the candidate flow instead and is never blocked.
function initialPhase(state: DraftStateDTO): "indexing" | "failed" | "ready" {
  if (state.versions.length > 0) return "ready";
  if (state.index_status === "pending" || state.index_status === "processing")
    return "indexing";
  if (state.index_status === "failed") return "failed";
  return "ready";
}

function projectDraftState(state: DraftStateDTO): DraftState {
  return {
    title: state.title,
    staged_abstract: state.staged_abstract,
    staged_keywords: state.staged_keywords,
    staged_fecha: state.staged_fecha,
    generated_abstract: state.generated_abstract,
    generated_keywords: state.generated_keywords,
    generated_fecha: state.generated_fecha,
    lifecycle: {
      formSeedKey: state.index_status,
      statusLabel: STATUS_PILL[state.index_status] ?? state.index_status,
      stage: state.index_stage,
      queued: state.index_status === "pending",
      showSuggestionsSpinner: state.index_status === "processing",
      gateMessage: state.publish_gate_reason
        ? (GATE_COPY[state.publish_gate_reason] ?? state.publish_gate_reason)
        : null,
      canPublish: state.publish_gate_reason === null && state.is_owner,
      initialPhase: initialPhase(state),
    },
    isOwner: state.is_owner,
    visibility: state.visibility,
    area_path: state.area_path,
    candidate: state.candidate ? projectCandidate(state.candidate) : null,
    versions: state.versions,
    attachments: state.attachments,
  };
}

export function useDraftState(docId: number) {
  const query = useDraftQuery(docId);
  const queryClient = useQueryClient();

  async function publish(): Promise<PublishMutationResult> {
    try {
      const { error, response } = await api.POST(
        "/api/documents/{doc_id}/publish",
        { params: { path: { doc_id: docId } } },
      );
      if (error) {
        if (response?.status === 409) {
          await queryClient.invalidateQueries({
            queryKey: draftQueryKey(docId),
          });
          return "refreshed";
        }
        return "publish_failed";
      }
      await queryClient.invalidateQueries({ queryKey: draftQueryKey(docId) });
      // The publish flow routes to Mis trabajos; invalidate the list so the
      // freshly published doc shows without a manual refresh.
      await queryClient.invalidateQueries({ queryKey: ["me", "documents"] });
      return "published";
    } catch {
      return "publish_failed";
    }
  }

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

  async function softDelete(): Promise<SoftDeleteMutationError | undefined> {
    const { error } = await api.DELETE("/api/documents/{doc_id}", {
      params: { path: { doc_id: docId } },
    });
    if (error) return "delete_failed";
    // The doc leaves Mis trabajos (manageable_where excludes soft-deleted); the
    // page routes there, so invalidating the list is enough to drop the row.
    await queryClient.invalidateQueries({ queryKey: ["me", "documents"] });
    return undefined;
  }

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

  const actions: DraftWorkspaceActions = {
    publish,
    replace,
    discard,
    softDelete,
    attachments: {
      add: addAttachment,
      remove: removeAttachment,
    },
  };

  return {
    state: query.data ? projectDraftState(query.data) : undefined,
    isLoading: query.isLoading,
    isError: query.isError,
    refresh: async () => {
      await queryClient.invalidateQueries({ queryKey: draftQueryKey(docId) });
    },
    actions,
  };
}
