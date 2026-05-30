import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiDelete, apiGet, apiPost } = vi.hoisted(() => ({
  apiDelete: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));
vi.mock("@/api/client", () => ({
  api: { DELETE: apiDelete, GET: apiGet, POST: apiPost },
}));

import type { components } from "@/api/schema";
import { useDraftState } from "./useDraftState";

type DraftStateDTO = components["schemas"]["DraftStateDTO"];

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = "TestQueryWrapper";
  return Wrapper;
}

type CandidateDTO = NonNullable<DraftStateDTO["candidate"]>;

function candidate(over: Partial<CandidateDTO> = {}): CandidateDTO {
  return {
    status: "processing",
    index_stage: null,
    staged_abstract: null,
    staged_keywords: [],
    staged_fecha: null,
    can_publish: false,
    can_discard: true,
    indexed_at: null,
    error: null,
    ...over,
  };
}

function returns(state: Partial<DraftStateDTO>) {
  const body: DraftStateDTO = {
    title: "Doc",
    index_status: "indexed",
    index_stage: null,
    staged_abstract: null,
    staged_keywords: [],
    staged_fecha: null,
    generated_abstract: null,
    generated_keywords: [],
    generated_fecha: null,
    index_error: null,
    publish_gate_reason: null,
    is_owner: true,
    visibility: "publico",
    area_path: "escuela.carrera.materia",
    attachments: [],
    coauthors: [],
    versions: [],
    candidate: null,
    ...state,
  };
  apiGet.mockResolvedValue({ data: body, error: undefined });
}

describe("useDraftState", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    apiDelete.mockReset();
    apiDelete.mockResolvedValue({ error: undefined });
    apiGet.mockReset();
    apiPost.mockReset();
    apiPost.mockResolvedValue({ error: undefined, response: { status: 204 } });
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("projects the generated snapshot alongside staged values", async () => {
    returns({
      staged_abstract: "resumen editado",
      generated_abstract: "resumen del extractor",
      generated_keywords: ["extractor"],
      generated_fecha: "2022-07-01",
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state!.staged_abstract).toBe("resumen editado");
    expect(result.current.state!.generated_abstract).toBe(
      "resumen del extractor",
    );
    expect(result.current.state!.generated_keywords).toEqual(["extractor"]);
    expect(result.current.state!.generated_fecha).toBe("2022-07-01");
  });

  it("interprets a publishable owner draft for page consumers", async () => {
    returns({
      index_status: "indexed",
      publish_gate_reason: null,
      is_owner: true,
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle).toEqual({
      formSeedKey: "indexed",
      statusLabel: "Listo para publicar",
      stage: null,
      showSuggestionsSpinner: false,
      gateMessage: null,
      canPublish: true,
      initialPhase: "ready",
    });
  });

  it("projects initialPhase for an initial draft still indexing", async () => {
    returns({ index_status: "processing", versions: [] });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle.initialPhase).toBe("indexing");
  });

  it("projects initialPhase as indexing while pending", async () => {
    returns({ index_status: "pending", versions: [] });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle.initialPhase).toBe("indexing");
  });

  it("projects initialPhase as failed for a failed initial draft", async () => {
    returns({ index_status: "failed", versions: [] });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle.initialPhase).toBe("failed");
  });

  it("projects initialPhase as ready once indexed", async () => {
    returns({ index_status: "indexed", versions: [] });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle.initialPhase).toBe("ready");
  });

  it("projects initialPhase as ready while a published version exists", async () => {
    returns({
      index_status: "processing",
      versions: [
        {
          n: 1,
          original_filename: "v1.pdf",
          mime: "application/pdf",
          size_bytes: 10,
          indexed_at: null,
          is_current: true,
        },
      ],
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle.initialPhase).toBe("ready");
  });

  it("interprets reindexing as blocked publication with Spanish copy", async () => {
    returns({
      index_status: "indexed",
      publish_gate_reason: "reindexing_headline",
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.lifecycle).toMatchObject({
      statusLabel: "Listo para publicar",
      gateMessage: "Reindexando título…",
      canPublish: false,
    });
  });

  it("polls every 3s while processing", async () => {
    returns({ index_status: "processing", publish_gate_reason: "processing" });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(3000);

    expect(apiGet.mock.calls.length).toBeGreaterThan(initial);
  });

  // The editar page blocks on pending (initialPhase === "indexing"), so polling
  // must clear it; otherwise the loader never advances to processing.
  it("polls while pending", async () => {
    returns({ index_status: "pending", versions: [] });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(3000);

    expect(apiGet.mock.calls.length).toBeGreaterThan(initial);
  });

  it("polls while reindexing_headline", async () => {
    returns({
      index_status: "indexed",
      publish_gate_reason: "reindexing_headline",
    });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(3000);

    expect(apiGet.mock.calls.length).toBeGreaterThan(initial);
  });

  it("stays idle when indexed and publishable", async () => {
    returns({ index_status: "indexed", publish_gate_reason: null });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(9000);

    expect(apiGet.mock.calls.length).toBe(initial);
  });

  it("stays idle when processing failed", async () => {
    returns({
      index_status: "failed",
      publish_gate_reason: "processing_failed",
    });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(9000);

    expect(apiGet.mock.calls.length).toBe(initial);
  });

  it("projects a ready candidate to Spanish label", async () => {
    returns({
      candidate: candidate({
        status: "ready",
        can_publish: true,
        staged_abstract: "Nuevo resumen",
      }),
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.candidate).toMatchObject({
      status: "ready",
      statusLabel: "Listo para publicar",
      canPublish: true,
      stagedAbstract: "Nuevo resumen",
    });
  });

  it("exposes a null candidate when none is in flight", async () => {
    returns({ candidate: null });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });

    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.state?.candidate).toBeNull();
  });

  it("polls every 3s while a candidate is processing", async () => {
    returns({
      index_status: "indexed",
      publish_gate_reason: null,
      candidate: candidate({ status: "processing" }),
    });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(3000);

    expect(apiGet.mock.calls.length).toBeGreaterThan(initial);
  });

  it("replace posts multipart and invalidates the draft query", async () => {
    returns({});
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 202 });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    const file = new File(["%PDF-1.4"], "nueva.pdf", {
      type: "application/pdf",
    });
    const error = await result.current.actions.replace(file);

    expect(error).toBeUndefined();
    expect(fetch).toHaveBeenCalledWith(
      "/api/documents/1/replace",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("replace maps rejection statuses to typed errors", async () => {
    returns({});
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);
    const file = new File(["x"], "f.pdf", { type: "application/pdf" });

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 413 });
    expect(await result.current.actions.replace(file)).toBe("too_large");
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 415 });
    expect(await result.current.actions.replace(file)).toBe("unsupported_type");
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 409 });
    expect(await result.current.actions.replace(file)).toBe(
      "no_published_version",
    );
  });

  it("publish posts through the draft action interface", async () => {
    returns({});
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(await result.current.actions.publish()).toBe("published");
    expect(apiPost).toHaveBeenCalledWith("/api/documents/{doc_id}/publish", {
      params: { path: { doc_id: 1 } },
    });
  });

  it("publish absorbs a 409 race by refreshing draft state", async () => {
    returns({});
    apiPost.mockResolvedValue({
      error: { detail: "conflict" },
      response: { status: 409 },
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    const callsBeforePublish = apiGet.mock.calls.length;

    expect(await result.current.actions.publish()).toBe("refreshed");
    await vi.advanceTimersByTimeAsync(0);
    expect(apiGet.mock.calls.length).toBeGreaterThan(callsBeforePublish);
  });

  it("discard optimistically removes the candidate on success", async () => {
    returns({ candidate: candidate({ status: "failed" }) });
    apiDelete.mockResolvedValue({
      error: undefined,
      response: { status: 204 },
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(result.current.state?.candidate).not.toBeNull();

    const error = await result.current.actions.discard();

    expect(error).toBeUndefined();
    expect(apiDelete).toHaveBeenCalledWith(
      "/api/documents/{doc_id}/candidate",
      { params: { path: { doc_id: 1 } } },
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(result.current.state?.candidate).toBeNull();
  });

  it("discard treats a 404 race as success", async () => {
    returns({ candidate: candidate({ status: "failed" }) });
    apiDelete.mockResolvedValue({
      error: { detail: "x" },
      response: { status: 404 },
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(await result.current.actions.discard()).toBeUndefined();
  });

  it("discard surfaces a typed error on other failures", async () => {
    returns({ candidate: candidate({ status: "failed" }) });
    apiDelete.mockResolvedValue({
      error: { detail: "boom" },
      response: { status: 500 },
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(await result.current.actions.discard()).toBe("discard_failed");
  });

  it("softDelete deletes the document through the typed endpoint", async () => {
    returns({});
    apiDelete.mockResolvedValue({
      error: undefined,
      response: { status: 204 },
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    const error = await result.current.actions.softDelete();

    expect(error).toBeUndefined();
    expect(apiDelete).toHaveBeenCalledWith("/api/documents/{doc_id}", {
      params: { path: { doc_id: 1 } },
    });
  });

  it("softDelete surfaces a typed error on failure", async () => {
    returns({});
    apiDelete.mockResolvedValue({
      error: { detail: "boom" },
      response: { status: 500 },
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(await result.current.actions.softDelete()).toBe("delete_failed");
  });
});

describe("draft attachment actions", () => {
  beforeEach(() => {
    apiDelete.mockReset();
    apiDelete.mockResolvedValue({ error: undefined });
    apiGet.mockReset();
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("appends a successful upload through its interface", async () => {
    returns({ attachments: [] });
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 201,
      json: async () => ({
        id: 9,
        original_filename: "new.csv",
        size_bytes: 10,
        mime: "text/csv",
      }),
    });
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.state?.attachments).toEqual([]));

    await result.current.actions.attachments.add(
      new File(["a,b\n"], "new.csv", { type: "text/csv" }),
    );

    expect(fetch).toHaveBeenCalledWith(
      "/api/documents/1/attachments",
      expect.objectContaining({ method: "POST" }),
    );
    await waitFor(() =>
      expect(
        result.current.state?.attachments.map(
          (attachment) => attachment.original_filename,
        ),
      ).toEqual(["new.csv"]),
    );
  });

  it("removes optimistically and restores a failed deletion", async () => {
    returns({
      attachments: [
        {
          id: 2,
          original_filename: "data.csv",
          size_bytes: 10,
          mime: "text/csv",
        },
      ],
    });
    let resolveDelete:
      | ((value: { error: { detail: string } }) => void)
      | undefined;
    apiDelete.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDelete = resolve;
        }),
    );
    const { result } = renderHook(() => useDraftState(1), {
      wrapper: wrapper(),
    });
    await waitFor(() =>
      expect(result.current.state?.attachments).toHaveLength(1),
    );

    const deleting = result.current.actions.attachments.remove(
      result.current.state?.attachments[0]!,
    );
    await waitFor(() => expect(result.current.state?.attachments).toEqual([]));
    expect(apiDelete).toHaveBeenCalledWith(
      "/api/documents/{doc_id}/attachments/{att_id}",
      { params: { path: { doc_id: 1, att_id: 2 } } },
    );
    resolveDelete?.({ error: { detail: "failed" } });
    await deleting;

    await waitFor(() =>
      expect(result.current.state?.attachments).toHaveLength(1),
    );
  });
});
