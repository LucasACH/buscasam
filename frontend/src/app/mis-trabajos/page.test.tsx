import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { useUserMock } = vi.hoisted(() => ({
  useUserMock: vi.fn(() => ({
    user: { user_id: 1, role: "estudiante" },
    isInvitado: false,
    isLoading: false,
    isError: false,
  })),
}));
vi.mock("@/lib/useUser", () => ({
  useUser: () => useUserMock(),
}));
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

import MisTrabajosPage from "./page";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("/mis-trabajos page", () => {
  beforeEach(() => {
    replace.mockReset();
    useUserMock.mockReset();
    useUserMock.mockReturnValue({
      user: { user_id: 1, role: "estudiante" },
      isInvitado: false,
      isLoading: false,
      isError: false,
    });
    apiGet.mockReset();
  });
  afterEach(() => {
    cleanup();
  });

  it("lists Borradores from /api/me/documents with a link to /editar", async () => {
    apiGet.mockResolvedValue({
      data: [
        { id: 7, title: "Mi tesis", publication_status: "draft", visibility: "interno" },
      ],
    });

    wrap(<MisTrabajosPage />);

    const row = await screen.findByRole("link", { name: /Mi tesis/ });
    expect(row).toHaveAttribute("href", "/mis-trabajos/7/editar");
    // Belongs under the Borradores section.
    const section = row.closest("section");
    expect(section).toHaveTextContent(/Borradores/);
  });

  it("separates Publicados rows from Borradores rows", async () => {
    apiGet.mockResolvedValue({
      data: [
        { id: 7, title: "Borrador X", publication_status: "draft", visibility: "interno" },
        { id: 8, title: "Publicado Y", publication_status: "published", visibility: "publico" },
      ],
    });

    wrap(<MisTrabajosPage />);

    const pub = await screen.findByRole("link", { name: /Publicado Y/ });
    expect(pub.closest("section")).toHaveTextContent(/Publicados/);
    const bor = screen.getByRole("link", { name: /Borrador X/ });
    expect(bor.closest("section")).toHaveTextContent(/Borradores/);
  });

  it("shows the publish timestamp on a Publicados row", async () => {
    apiGet.mockResolvedValue({
      data: [
        {
          id: 8,
          title: "Publicado Y",
          publication_status: "published",
          visibility: "publico",
          published_at: "2024-03-01T12:00:00Z",
        },
      ],
    });

    wrap(<MisTrabajosPage />);

    const pub = await screen.findByRole("link", { name: /Publicado Y/ });
    expect(pub).toHaveTextContent(/2024/);
  });

  it("links to the Papelera", async () => {
    apiGet.mockResolvedValue({ data: [] });

    wrap(<MisTrabajosPage />);

    const link = await screen.findByRole("link", { name: /Papelera/ });
    expect(link).toHaveAttribute("href", "/mis-trabajos/papelera");
  });

  it("renders the empty-state copy in each section when the user has no documents", async () => {
    apiGet.mockResolvedValue({ data: [] });

    wrap(<MisTrabajosPage />);

    await waitFor(() =>
      expect(
        screen.queryAllByText(
          /Aún no subiste ningún trabajo — empezá con Nuevo trabajo/,
        ).length,
      ).toBe(2),
    );
  });

  it("does not flash empty-state copy while the docs query is still pending", async () => {
    // Resolve never — query stays pending.
    apiGet.mockReturnValue(new Promise(() => {}));

    wrap(<MisTrabajosPage />);

    // Page chrome renders, but the empty-state copy must not appear during load.
    await screen.findByRole("heading", { name: /Mis trabajos/ });
    expect(
      screen.queryByText(/Aún no subiste ningún trabajo/),
    ).toBeNull();
  });
});
