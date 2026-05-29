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
import { useInspect } from "./useInspect";

type InspectMetadataDTO = components["schemas"]["InspectMetadataDTO"];

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

const META: InspectMetadataDTO = {
  titulo: "Tesis reportada",
  abstract: "Un resumen",
  palabras_clave: ["a", "b"],
  autores: [{ display_name: "Ana", user_id: 1 }],
  tipo: "tesis",
  area_path: "ing.sistemas",
};

describe("useInspect", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
  });
  afterEach(() => cleanup());

  it("fetches the report-scoped document metadata", async () => {
    apiGet.mockResolvedValue({ data: META, error: undefined });

    const { result } = renderHook(() => useInspect(42), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.metadata).toEqual(META);
    expect(apiGet).toHaveBeenCalledWith(
      "/api/moderation/reports/{report_id}/document",
      { params: { path: { report_id: 42 } } },
    );
  });

  it.each([
    ["hide", "/api/moderation/reports/{report_id}/hide"],
    ["unhide", "/api/moderation/reports/{report_id}/unhide"],
    ["dismiss", "/api/moderation/reports/{report_id}/dismiss"],
  ] as const)("%s POSTs the reason to its endpoint and invalidates the queue", async (action, path) => {
    apiGet.mockResolvedValue({ data: META, error: undefined });
    apiPost.mockResolvedValue({ error: undefined });
    const { result } = renderHook(() => useInspect(42), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    const err = await result.current[action]("una razón");

    expect(err).toBeUndefined();
    expect(apiPost).toHaveBeenCalledWith(path, {
      params: { path: { report_id: 42 } },
      body: { reason: "una razón" },
    });
    expect(invalidate.mock.calls.map((c) => c[0]?.queryKey)).toContainEqual([
      "moderation",
      "queue",
    ]);
  });

  it("surfaces a failed action as action_failed without invalidating", async () => {
    apiGet.mockResolvedValue({ data: META, error: undefined });
    apiPost.mockResolvedValue({ error: { detail: "x" } });
    const { result } = renderHook(() => useInspect(42), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(await result.current.hide("r")).toBe("action_failed");
  });
});
