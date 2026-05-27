import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { POST: apiPost } }));

import { useCoauthorInvitation } from "./useCoauthorInvitation";

function harness() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

describe("useCoauthorInvitation", () => {
  beforeEach(() => apiPost.mockReset());
  afterEach(() => cleanup());

  it("accept: posts to the accept endpoint and invalidates bandeja + doc-detail", async () => {
    apiPost.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: { status: 204 },
    });
    const { client, wrapper } = harness();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useCoauthorInvitation(), { wrapper });

    let err;
    await act(async () => {
      err = await result.current.accept(7);
    });

    expect(err).toBeUndefined();
    expect(apiPost).toHaveBeenCalledWith(
      "/api/coauthor_invitations/{doc_id}/accept",
      { params: { path: { doc_id: 7 } } },
    );
    const invalidatedKeys = invalidate.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidatedKeys).toContainEqual(["notifications"]);
    expect(invalidatedKeys).toContainEqual(["notifications", "unread_count"]);
    expect(invalidatedKeys).toContainEqual(["doc-detail", 7]);
  });

  it("decline: posts to the decline endpoint", async () => {
    apiPost.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: { status: 204 },
    });
    const { wrapper } = harness();
    const { result } = renderHook(() => useCoauthorInvitation(), { wrapper });

    await act(async () => {
      await result.current.decline(7);
    });

    expect(apiPost).toHaveBeenCalledWith(
      "/api/coauthor_invitations/{doc_id}/decline",
      { params: { path: { doc_id: 7 } } },
    );
  });

  it("404 returns {kind:'gone'} and still invalidates so the stale item refreshes", async () => {
    apiPost.mockResolvedValue({
      error: { detail: "not_found" },
      response: { status: 404 },
    });
    const { client, wrapper } = harness();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useCoauthorInvitation(), { wrapper });

    let err;
    await act(async () => {
      err = await result.current.accept(7);
    });

    expect(err).toEqual({ kind: "gone" });
    const invalidatedKeys = invalidate.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidatedKeys).toContainEqual(["notifications"]);
  });

  it("non-404 error returns {kind:'network'} and does not invalidate", async () => {
    apiPost.mockResolvedValue({
      error: { detail: "boom" },
      response: { status: 500 },
    });
    const { client, wrapper } = harness();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useCoauthorInvitation(), { wrapper });

    let err;
    await act(async () => {
      err = await result.current.accept(7);
    });

    expect(err).toEqual({ kind: "network" });
    expect(invalidate).not.toHaveBeenCalled();
  });
});
