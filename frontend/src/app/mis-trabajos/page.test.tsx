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

import MisTrabajosPage from "./page";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function mockDocs(body: unknown) {
  return vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
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
    vi.spyOn(global, "fetch").mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("lists Borradores from /api/me/documents with a link to /editar", async () => {
    mockDocs([
      { id: 7, title: "Mi tesis", publication_status: "draft", visibility: "interno" },
    ]);

    wrap(<MisTrabajosPage />);

    const row = await screen.findByRole("link", { name: /Mi tesis/ });
    expect(row).toHaveAttribute("href", "/mis-trabajos/7/editar");
    // Belongs under the Borradores section.
    const section = row.closest("section");
    expect(section).toHaveTextContent(/Borradores/);
  });

  it("separates Publicados rows from Borradores rows", async () => {
    mockDocs([
      { id: 7, title: "Borrador X", publication_status: "draft", visibility: "interno" },
      { id: 8, title: "Publicado Y", publication_status: "published", visibility: "publico" },
    ]);

    wrap(<MisTrabajosPage />);

    const pub = await screen.findByRole("link", { name: /Publicado Y/ });
    expect(pub.closest("section")).toHaveTextContent(/Publicados/);
    const bor = screen.getByRole("link", { name: /Borrador X/ });
    expect(bor.closest("section")).toHaveTextContent(/Borradores/);
  });

  it("renders the empty-state copy in each section when the user has no documents", async () => {
    mockDocs([]);

    wrap(<MisTrabajosPage />);

    await waitFor(() =>
      expect(
        screen.queryAllByText(
          /Aún no subiste ningún trabajo — empezá con Nuevo trabajo/,
        ).length,
      ).toBe(2),
    );
  });
});
