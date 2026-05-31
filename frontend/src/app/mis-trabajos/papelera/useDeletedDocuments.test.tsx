import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));
vi.mock("@/api/client", () => ({
  api: { GET: apiGet, POST: apiPost },
}));

import type { components } from "@/api/schema";
import { useDeletedDocuments } from "./useDeletedDocuments";

type DeletedDocDTO = components["schemas"]["DeletedDocDTO"];

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

function returns(rows: DeletedDocDTO[]) {
  apiGet.mockResolvedValue({ data: rows, error: undefined });
}

describe("useDeletedDocuments", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    // Freeze only Date.now (not the timers waitFor relies on) so days-remaining
    // is deterministic against a fixed "now".
    vi.spyOn(Date, "now").mockReturnValue(
      new Date("2026-05-28T00:00:00Z").getTime(),
    );
  });
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("lists deleted docs with days-remaining derived from purge_at", async () => {
    returns([
      {
        id: 5,
        title: "Eliminado",
        publication_status: "published",
        purge_at: "2026-05-30T00:00:00Z", // 2 días desde el reloj fijo
      },
    ]);
    const { result } = renderHook(() => useDeletedDocuments(), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.documents).toEqual([
      {
        id: 5,
        title: "Eliminado",
        daysRemaining: 2,
      },
    ]);
    expect(apiGet).toHaveBeenCalledWith("/api/me/documents/deleted");
  });

  it("restore POSTs to the restore endpoint and refetches the deleted list", async () => {
    returns([
      { id: 5, title: "x", publication_status: "draft", purge_at: "2026-06-01T00:00:00Z" },
    ]);
    apiPost.mockResolvedValue({ error: undefined });
    const { result } = renderHook(() => useDeletedDocuments(), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    const err = await result.current.restore(5);

    expect(err).toBeUndefined();
    expect(apiPost).toHaveBeenCalledWith("/api/documents/{doc_id}/restore", {
      params: { path: { doc_id: 5 } },
    });
    // Both keys invalidated: the doc leaves the Papelera and returns to Mis trabajos.
    const keys = invalidate.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(["me", "documents", "deleted"]);
    expect(keys).toContainEqual(["me", "documents"]);
  });

  it("restore surfaces failure as restore_failed", async () => {
    returns([]);
    apiPost.mockResolvedValue({ error: { detail: "x" }, response: { status: 404 } });
    const { result } = renderHook(() => useDeletedDocuments(), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(await result.current.restore(5)).toBe("restore_failed");
  });
});
