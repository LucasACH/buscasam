import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useDocDetail } from "./useDocDetail";

const DETAIL_BODY = {
  doc_id: 42,
  titulo: "Búsqueda híbrida",
  autores: [{ display_name: "Ada Lovelace", user_id: 7 }],
  area_path: "escuela_ciencia",
  tipo: "tesis",
  fecha: "2024-03-15",
  visibility: "publico",
  abstract: "Resumen.",
  palabras_clave: ["bd", "ir"],
  archivo_principal: {
    original_filename: "tesis.pdf",
    size_bytes: 2048,
    mime: "application/pdf",
  },
  adjuntos: [],
  manageable: false,
};

function wrapper(opts: { retryDelay?: number } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: opts.retryDelay ?? 0 },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = "TestQueryWrapper";
  return Wrapper;
}

describe("useDocDetail", () => {
  beforeEach(() => {
    vi.spyOn(global, "fetch").mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("sets is404 and does not retry on 404", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response("", { status: 404 }));

    const { result } = renderHook(() => useDocDetail(99), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.is404).toBe(true));
    expect(result.current.detail).toBeUndefined();
    // isError reflects "unrecoverable non-404 failure" — a 404 is not an error
    // from the page's perspective (it has a dedicated empty state).
    expect(result.current.isError).toBe(false);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("retries on transient (non-404) errors and caps at 3 retries", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(new Response("", { status: 500 }));

    const { result } = renderHook(() => useDocDetail(7), {
      wrapper: wrapper(),
    });

    // After exhausting retries the query settles into the error state.
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.is404).toBe(false);
    // 1 initial + 3 retries; the predicate must not retry past failureCount=3.
    expect(fetchSpy).toHaveBeenCalledTimes(4);
  });

  it("returns detail on 200", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(DETAIL_BODY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { result } = renderHook(() => useDocDetail(42), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.detail).toEqual(DETAIL_BODY);
    expect(result.current.is404).toBe(false);
    expect(result.current.isError).toBe(false);
  });
});
