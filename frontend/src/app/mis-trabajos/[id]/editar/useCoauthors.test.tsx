import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}));
vi.mock("@/api/client", () => ({
  api: { GET: apiGet, POST: apiPost, DELETE: apiDelete },
}));

import type { components } from "@/api/schema";
import { useCoauthors } from "./useCoauthors";

type DraftStateDTO = components["schemas"]["DraftStateDTO"];

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = "Wrapper";
  return Wrapper;
}

function returns(overrides: Partial<DraftStateDTO> = {}) {
  const body: DraftStateDTO = {
    title: "t",
    index_status: "indexed",
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
    attachments: [],
    coauthors: [
      { user_id: 1, display_name: "Ada", email_local: "ada", email: null, status: "owner" },
    ],
    versions: [],
    candidate: null,
    ...overrides,
  };
  apiGet.mockResolvedValue({ data: body, error: undefined });
}

describe("useCoauthors", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiDelete.mockReset();
  });
  afterEach(() => cleanup());

  it("surfaces is_owner and the coauthors list from the draft channel", async () => {
    returns({
      is_owner: true,
      coauthors: [
        { user_id: 1, display_name: "Ada", email_local: "ada", email: null, status: "owner" },
        { user_id: 2, display_name: "Bob", email_local: "bob", email: null, status: "pending" },
      ],
    });
    const { result } = renderHook(() => useCoauthors(1), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isOwner).toBe(true);
    expect(result.current.coauthors?.map((c) => c.display_name)).toEqual([
      "Ada",
      "Bob",
    ]);
  });

  it("invite POSTs the user_id and invalidates the draft query", async () => {
    returns();
    apiPost.mockResolvedValue({ error: undefined });
    const { result } = renderHook(() => useCoauthors(7), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const initialGets = apiGet.mock.calls.length;
    const err = await result.current.invite(99);

    expect(err).toBeUndefined();
    expect(apiPost).toHaveBeenCalledWith(
      "/api/documents/{doc_id}/coauthors",
      { params: { path: { doc_id: 7 } }, body: { user_id: 99 } },
    );
    await waitFor(() =>
      expect(apiGet.mock.calls.length).toBeGreaterThan(initialGets),
    );
  });

  it("invite surfaces 409 as already_listed", async () => {
    returns();
    apiPost.mockResolvedValue({
      error: { detail: "x" },
      response: { status: 409 },
    });
    const { result } = renderHook(() => useCoauthors(1), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const err = await result.current.invite(99);

    expect(err).toEqual({ kind: "already_listed" });
  });

  it("invite surfaces 403 as forbidden", async () => {
    returns();
    apiPost.mockResolvedValue({
      error: { detail: "x" },
      response: { status: 403 },
    });
    const { result } = renderHook(() => useCoauthors(1), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(await result.current.invite(99)).toEqual({ kind: "forbidden" });
  });

  it("invite surfaces other errors as network", async () => {
    returns();
    apiPost.mockResolvedValue({
      error: { detail: "x" },
      response: { status: 500 },
    });
    const { result } = renderHook(() => useCoauthors(1), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(await result.current.invite(99)).toEqual({ kind: "network" });
  });

  it("revoke DELETEs the user_id and invalidates the draft query", async () => {
    returns();
    apiDelete.mockResolvedValue({ error: undefined });
    const { result } = renderHook(() => useCoauthors(7), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const initialGets = apiGet.mock.calls.length;
    expect(await result.current.revoke(99)).toBeUndefined();
    expect(apiDelete).toHaveBeenCalledWith(
      "/api/documents/{doc_id}/coauthors/{user_id}",
      { params: { path: { doc_id: 7, user_id: 99 } } },
    );
    await waitFor(() =>
      expect(apiGet.mock.calls.length).toBeGreaterThan(initialGets),
    );
  });
});
