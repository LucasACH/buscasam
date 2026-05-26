import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { useUserMock, apiGet, apiPost } = vi.hoisted(() => ({
  useUserMock: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock("@/lib/useUser", () => ({ useUser: () => useUserMock() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet, POST: apiPost } }));

import { useNotifications, useUnreadCount } from "./useNotifications";

function notif(id: number, read: boolean) {
  return {
    id,
    kind: "coauthor_invite",
    payload: { doc_title: `Doc ${id}`, inviter: "Ada" },
    read_at: read ? "2026-01-01T00:00:00Z" : null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function harness() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

function authenticated() {
  useUserMock.mockReturnValue({
    user: { user_id: 1 },
    isInvitado: false,
    isLoading: false,
    isError: false,
  });
}

function invitado() {
  useUserMock.mockReturnValue({
    user: null,
    isInvitado: true,
    isLoading: false,
    isError: false,
  });
}

describe("useNotifications hooks", () => {
  beforeEach(() => {
    useUserMock.mockReset();
    apiGet.mockReset();
    apiPost.mockReset();
  });
  afterEach(() => cleanup());

  it("invitado: short-circuits to empty without fetching", async () => {
    invitado();
    const { wrapper } = harness();

    const { result } = renderHook(
      () => ({ list: useNotifications(), count: useUnreadCount() }),
      { wrapper },
    );

    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.list.items).toEqual([]);
    expect(result.current.count.count).toBe(0);
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("authenticated: exposes items and unread count from the API", async () => {
    authenticated();
    apiGet.mockImplementation((path: string) => {
      if (path === "/api/notifications")
        return Promise.resolve({ data: { items: [notif(1, false), notif(2, true)] } });
      return Promise.resolve({ data: { count: 1 } });
    });
    const { wrapper } = harness();

    const { result } = renderHook(
      () => ({ list: useNotifications(), count: useUnreadCount() }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.list.items).toHaveLength(2));
    expect(result.current.count.count).toBe(1);
  });

  async function seeded() {
    authenticated();
    apiGet.mockImplementation((path: string) => {
      if (path === "/api/notifications")
        return Promise.resolve({
          data: { items: [notif(1, false), notif(2, false)] },
        });
      return Promise.resolve({ data: { count: 2 } });
    });
    const { wrapper } = harness();
    const { result } = renderHook(
      () => ({ list: useNotifications(), count: useUnreadCount() }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.list.items).toHaveLength(2));
    await waitFor(() => expect(result.current.count.count).toBe(2));
    return result;
  }

  it("markRead optimistically flips the row and decrements the count", async () => {
    const result = await seeded();
    // never resolves: the optimistic state must hold while in-flight
    apiPost.mockReturnValue(new Promise(() => {}));

    act(() => result.current.list.markRead(1));

    await waitFor(() => expect(result.current.count.count).toBe(1));
    const items = result.current.list.items;
    expect(items.find((n) => n.id === 1)!.read_at).not.toBeNull();
    expect(items.find((n) => n.id === 2)!.read_at).toBeNull();
  });

  it("markRead rolls back the optimistic flip on mutation error", async () => {
    const result = await seeded();
    apiPost.mockResolvedValue({ error: { detail: "boom" } });

    act(() => result.current.list.markRead(1));

    await waitFor(() => expect(result.current.count.count).toBe(2));
    expect(result.current.list.items.find((n) => n.id === 1)!.read_at).toBeNull();
  });

  it("markAllRead optimistically flips every unread row and zeroes the count", async () => {
    const result = await seeded();
    apiPost.mockReturnValue(new Promise(() => {}));

    act(() => result.current.list.markAllRead());

    await waitFor(() => expect(result.current.count.count).toBe(0));
    expect(
      result.current.list.items.every((n) => n.read_at !== null),
    ).toBe(true);
  });

  it("markAllRead rolls back on mutation error", async () => {
    const result = await seeded();
    apiPost.mockResolvedValue({ error: { detail: "boom" } });

    act(() => result.current.list.markAllRead());

    await waitFor(() => expect(result.current.count.count).toBe(2));
    expect(
      result.current.list.items.every((n) => n.read_at === null),
    ).toBe(true);
  });
});
