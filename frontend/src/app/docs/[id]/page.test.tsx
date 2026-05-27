import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

import DocDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "42" }),
}));

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  {
    area_path: "escuela_ciencia.carrera_informatica",
    display_name: "Ing. Informática",
  },
];

const PUBLICO_DETAIL = {
  doc_id: 42,
  titulo: "Búsqueda híbrida en repositorios académicos",
  autores: [
    { display_name: "Ada Lovelace", user_id: 7 },
    { display_name: "Grace Hopper", user_id: null },
  ],
  area_path: "escuela_ciencia.carrera_informatica",
  tipo: "tesis",
  fecha: "2024-03-15",
  visibility: "publico",
  abstract: "Resumen del trabajo.",
  palabras_clave: ["busqueda", "hibrida"],
  archivo_principal: {
    original_filename: "tesis.pdf",
    size_bytes: 2048,
    mime: "application/pdf",
  },
  adjuntos: [
    {
      id: 101,
      original_filename: "datos.csv",
      size_bytes: 512,
      mime: "text/csv",
    },
  ],
  manageable: false,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchByUrl(routes: Record<string, () => Response>) {
  vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    for (const prefix of Object.keys(routes)) {
      if (url.includes(prefix)) return routes[prefix]();
    }
    return new Response("", { status: 404 });
  });
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DocDetailPage />
    </QueryClientProvider>,
  );
}

describe("/docs/[id] page", () => {
  beforeEach(() => {
    document.title = "BUSCASAM";
    apiGet.mockReset();
    apiGet.mockResolvedValue({ data: AREAS });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    document.title = "BUSCASAM";
  });

  it("renders metadata, abstract, palabras clave, archivo principal, adjuntos", async () => {
    mockFetchByUrl({
      "/api/docs/42": () => jsonResponse(PUBLICO_DETAIL),
      "/api/areas": () => jsonResponse(AREAS),
    });

    renderPage();

    await screen.findByText("Búsqueda híbrida en repositorios académicos");
    expect(screen.getByText("Ada Lovelace, Grace Hopper")).toBeInTheDocument();
    // The áreas tree resolves via a second query, so wait for the display name
    // to replace the raw area_path.
    await screen.findByText("Ing. Informática");
    expect(screen.getByText("Tesis")).toBeInTheDocument();
    expect(screen.getByText("2024-03-15")).toBeInTheDocument();
    expect(screen.getByText("Resumen del trabajo.")).toBeInTheDocument();
    expect(screen.getByText("busqueda")).toBeInTheDocument();
    expect(screen.getByText("hibrida")).toBeInTheDocument();
    expect(screen.getByText("tesis.pdf")).toBeInTheDocument();
    expect(screen.getByText("datos.csv")).toBeInTheDocument();

    // Download links point at the backend endpoints.
    const mainDl = screen.getByRole("link", { name: /descargar archivo principal/i });
    expect(mainDl).toHaveAttribute("href", "/api/docs/42/download");
    const attDl = screen.getByRole("link", { name: /descargar datos\.csv/i });
    expect(attDl).toHaveAttribute("href", "/api/docs/42/attachments/101");
  });

  it("sets document.title to detail.titulo and reverts on unmount", async () => {
    mockFetchByUrl({
      "/api/docs/42": () => jsonResponse(PUBLICO_DETAIL),
      "/api/areas": () => jsonResponse(AREAS),
    });

    const initialTitle = document.title;
    const { unmount } = renderPage();
    await waitFor(() =>
      expect(document.title).toBe(
        "Búsqueda híbrida en repositorios académicos",
      ),
    );
    unmount();
    expect(document.title).toBe(initialTitle);
  });

  it("renders the Spanish empty state on 404", async () => {
    mockFetchByUrl({
      "/api/docs/42": () => new Response("", { status: 404 }),
      "/api/areas": () => jsonResponse(AREAS),
    });

    renderPage();

    await screen.findByText("No encontramos este documento");
    // No metadata leak — none of the public-detail fields are rendered.
    expect(screen.queryByText("Descargar archivo principal")).toBeNull();
  });

  it("does not render the interno badge for publico but renders it for non-publico", async () => {
    mockFetchByUrl({
      "/api/docs/42": () =>
        jsonResponse({ ...PUBLICO_DETAIL, visibility: "interno" }),
      "/api/areas": () => jsonResponse(AREAS),
    });
    renderPage();
    await screen.findByText("Búsqueda híbrida en repositorios académicos");
    expect(screen.getByText("Interno")).toBeInTheDocument();
  });
});
