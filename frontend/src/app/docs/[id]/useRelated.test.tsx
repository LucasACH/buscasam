import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useRelated } from "./useRelated";

const RELATED_BODY = [
  {
    doc_id: 7,
    titulo: "Sibling",
    autores: [{ display_name: "Ada", user_id: 1 }],
    area_path: "escuela_ciencia",
    tipo: "paper",
    fecha: "2024-01-15",
    similarity: 0.91,
  },
];

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = "TestQueryWrapper";
  return Wrapper;
}

describe("useRelated", () => {
  beforeEach(() => {
    vi.spyOn(global, "fetch").mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("returns related rows on 200", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(RELATED_BODY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { result } = renderHook(() => useRelated(42), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.related).toEqual(RELATED_BODY);
    expect(result.current.isError).toBe(false);
  });

  it("returns empty array when the source has no neighbours", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { result } = renderHook(() => useRelated(42), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.related).toEqual([]);
  });

  it("sets isError on 404 (degenerate path; page already handled it)", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response("", { status: 404 }),
    );

    const { result } = renderHook(() => useRelated(99), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.related).toBeUndefined();
  });

  it("hits /api/docs/{id}/related with the docId in the key", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(
        new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    const { result } = renderHook(() => useRelated(123), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/docs/123/related",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });
});
