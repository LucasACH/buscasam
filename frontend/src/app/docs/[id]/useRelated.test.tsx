import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

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

function fakeResponse(status: number): Response {
  return { status, ok: status >= 200 && status < 300 } as Response;
}

describe("useRelated", () => {
  beforeEach(() => {
    apiGet.mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("returns related rows on 200", async () => {
    apiGet.mockResolvedValue({
      data: RELATED_BODY,
      error: undefined,
      response: fakeResponse(200),
    });

    const { result } = renderHook(() => useRelated(42), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.related).toEqual(RELATED_BODY);
    expect(result.current.isError).toBe(false);
  });

  it("returns empty array when the source has no neighbours", async () => {
    apiGet.mockResolvedValue({
      data: [],
      error: undefined,
      response: fakeResponse(200),
    });

    const { result } = renderHook(() => useRelated(42), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.related).toEqual([]);
  });

  it("sets isError on 404 (degenerate path; page already handled it)", async () => {
    apiGet.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: fakeResponse(404),
    });

    const { result } = renderHook(() => useRelated(99), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.related).toBeUndefined();
  });

  it("hits /api/docs/{doc_id}/related with the docId in the path params", async () => {
    apiGet.mockResolvedValue({
      data: [],
      error: undefined,
      response: fakeResponse(200),
    });

    const { result } = renderHook(() => useRelated(123), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(apiGet).toHaveBeenCalledWith("/api/docs/{doc_id}/related", {
      params: { path: { doc_id: 123 } },
    });
  });
});
