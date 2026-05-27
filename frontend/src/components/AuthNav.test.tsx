import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const replace = vi.fn();
const pathname = vi.fn(() => "/buscar");

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname(),
}));

const { useUserMock, apiPost } = vi.hoisted(() => ({
  useUserMock: vi.fn(),
  apiPost: vi.fn(),
}));
vi.mock("@/lib/useUser", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/useUser")>();
  return { ...mod, useUser: () => useUserMock() };
});
vi.mock("@/api/client", () => ({ api: { POST: apiPost } }));

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

import { AuthNav } from "./AuthNav";

function renderAuthNav() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthNav />
    </QueryClientProvider>,
  );
}

function asInvitado() {
  useUserMock.mockReturnValue({
    user: null,
    isInvitado: true,
    isLoading: false,
    isError: false,
  });
}

function asAuthenticated(user: {
  user_id: number;
  role: "estudiante" | "docente";
  name: string;
  picture_url: string | null;
  hd: string;
}) {
  useUserMock.mockReturnValue({
    user,
    isInvitado: false,
    isLoading: false,
    isError: false,
  });
}

describe("AuthNav", () => {
  beforeEach(() => {
    replace.mockReset();
    pathname.mockReturnValue("/buscar");
    useUserMock.mockReset();
    apiPost.mockReset();
    apiPost.mockResolvedValue({ data: undefined, error: undefined });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("invitado: shows login link with encoded next", async () => {
    asInvitado();
    renderAuthNav();

    const link = await screen.findByRole("link", {
      name: /Iniciar sesión con UNSAM/i,
    });
    expect(link.getAttribute("href")).toBe(
      "/login?next=" + encodeURIComponent("/buscar"),
    );
  });

  it("authenticated: shows avatar + role label + logout", async () => {
    asAuthenticated({
      user_id: 7,
      role: "docente",
      name: "Ada Lovelace",
      picture_url: "https://example.test/a.png",
      hd: "unsam.edu.ar",
    });
    renderAuthNav();

    expect(
      await screen.findByText("Docente", { exact: false }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Cerrar sesión/i }),
    ).toBeInTheDocument();
  });

  it("logout POSTs /api/auth/logout then router.replace('/')", async () => {
    asAuthenticated({
      user_id: 7,
      role: "estudiante",
      name: "Ada Lovelace",
      picture_url: null,
      hd: "estudiantes.unsam.edu.ar",
    });
    renderAuthNav();

    const btn = await screen.findByRole("button", { name: /Cerrar sesión/i });
    await userEvent.click(btn);

    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(apiPost).toHaveBeenCalledWith("/api/auth/logout");
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("logout evicts the notifications cache", async () => {
    const removeQueries = vi.spyOn(QueryClient.prototype, "removeQueries");
    asAuthenticated({
      user_id: 7,
      role: "estudiante",
      name: "Ada Lovelace",
      picture_url: null,
      hd: "estudiantes.unsam.edu.ar",
    });
    renderAuthNav();

    const btn = await screen.findByRole("button", { name: /Cerrar sesión/i });
    await userEvent.click(btn);

    expect(removeQueries).toHaveBeenCalledWith({
      queryKey: ["notifications"],
    });
  });
});
