import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthNav } from "./AuthNav";

const replace = vi.fn();
const pathname = vi.fn(() => "/buscar");

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname(),
}));

// The mounted NotificationBell pulls these; stub them so AuthNav tests stay
// hermetic and don't reach the network through the typed client.
vi.mock("@/lib/useNotifications", () => ({
  NOTIFICATIONS_QUERY_KEY: ["notifications"],
  useUnreadCount: () => ({ count: 0, isLoading: false }),
  useNotifications: () => ({
    items: [],
    isLoading: false,
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  }),
}));

function renderWith(fetchImpl: typeof fetch) {
  vi.spyOn(global, "fetch").mockImplementation(fetchImpl);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthNav />
    </QueryClientProvider>,
  );
}

describe("AuthNav", () => {
  beforeEach(() => {
    replace.mockReset();
    pathname.mockReturnValue("/buscar");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("invitado: shows login link with encoded next", async () => {
    renderWith(async () => new Response(null, { status: 401 }));

    const link = await screen.findByRole("link", {
      name: /Iniciar sesión con UNSAM/i,
    });
    expect(link.getAttribute("href")).toBe(
      "/login?next=" + encodeURIComponent("/buscar"),
    );
  });

  it("authenticated: shows avatar + role label + logout", async () => {
    const user = {
      user_id: 7,
      role: "docente",
      name: "Ada Lovelace",
      picture_url: "https://example.test/a.png",
      hd: "unsam.edu.ar",
    };
    renderWith(async (input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/me"))
        return new Response(JSON.stringify(user), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      return new Response(null, { status: 204 });
    });

    expect(
      await screen.findByText("Docente", { exact: false }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Cerrar sesión/i }),
    ).toBeInTheDocument();
  });

  it("logout POSTs /api/auth/logout then router.replace('/')", async () => {
    const user = {
      user_id: 7,
      role: "estudiante",
      name: "Ada Lovelace",
      picture_url: null,
      hd: "estudiantes.unsam.edu.ar",
    };
    const logout = vi.fn(
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    );
    renderWith(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/auth/logout")) return logout(input, init);
      if (url.endsWith("/api/me"))
        return new Response(JSON.stringify(user), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      return new Response(null, { status: 204 });
    });

    const btn = await screen.findByRole("button", { name: /Cerrar sesión/i });
    await userEvent.click(btn);

    expect(logout).toHaveBeenCalledTimes(1);
    const init = logout.mock.calls[0]![1];
    expect(init?.method).toBe("POST");
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("logout evicts the notifications cache", async () => {
    const removeQueries = vi.spyOn(QueryClient.prototype, "removeQueries");
    const user = {
      user_id: 7,
      role: "estudiante",
      name: "Ada Lovelace",
      picture_url: null,
      hd: "estudiantes.unsam.edu.ar",
    };
    renderWith(async (input) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/me"))
        return new Response(JSON.stringify(user), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      return new Response(null, { status: 204 });
    });

    const btn = await screen.findByRole("button", { name: /Cerrar sesión/i });
    await userEvent.click(btn);

    expect(removeQueries).toHaveBeenCalledWith({
      queryKey: ["notifications"],
    });
  });
});
