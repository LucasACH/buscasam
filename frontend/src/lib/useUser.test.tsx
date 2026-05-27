import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

import { useUser } from "./useUser";

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

function fakeResponse(status: number): Response {
  return { status, ok: status >= 200 && status < 300 } as Response;
}

describe("useUser", () => {
  beforeEach(() => {
    apiGet.mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("returns invitado on 401", async () => {
    apiGet.mockResolvedValue({
      data: undefined,
      error: undefined,
      response: fakeResponse(401),
    });

    const { result } = renderHook(() => useUser(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
    expect(result.current.isInvitado).toBe(true);
  });

  it("returns the user shape on 200", async () => {
    const body = {
      user_id: 42,
      role: "docente",
      name: "Ada Lovelace",
      picture_url: "https://example.test/a.png",
      hd: "unsam.edu.ar",
    };
    apiGet.mockResolvedValue({
      data: body,
      error: undefined,
      response: fakeResponse(200),
    });

    const { result } = renderHook(() => useUser(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toEqual(body);
    expect(result.current.isInvitado).toBe(false);
  });

  it("throws (isError) on network failure", async () => {
    apiGet.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useUser(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isError).toBe(true);
  });

  it("does NOT treat a network error as invitado", async () => {
    apiGet.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useUser(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isError).toBe(true);
    expect(result.current.isInvitado).toBe(false);
    expect(result.current.user).toBeNull();
  });
});
