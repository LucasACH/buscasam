import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

import { useDraftState, type DraftStateDTO } from "./useDraftState";

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

function returns(state: Partial<DraftStateDTO>) {
  const body: DraftStateDTO = {
    title: "Doc",
    index_status: "indexed",
    staged_abstract: null,
    staged_keywords: [],
    staged_fecha: null,
    index_error: null,
    publish_gate_reason: null,
    is_owner: true,
    ...state,
  };
  apiGet.mockResolvedValue({ data: body, error: undefined });
}

describe("useDraftState", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    apiGet.mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("polls every 3s while processing", async () => {
    returns({ index_status: "processing", publish_gate_reason: "processing" });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(3000);

    expect(apiGet.mock.calls.length).toBeGreaterThan(initial);
  });

  it("polls while reindexing_headline", async () => {
    returns({ index_status: "indexed", publish_gate_reason: "reindexing_headline" });
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
    returns({ index_status: "failed", publish_gate_reason: "processing_failed" });
    renderHook(() => useDraftState(1), { wrapper: wrapper() });

    await vi.advanceTimersByTimeAsync(0);
    const initial = apiGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(9000);

    expect(apiGet.mock.calls.length).toBe(initial);
  });
});
