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

const MANAGEABLE_DETAIL = {
  ...PUBLICO_DETAIL,
  visibility: "privado",
  manageable: true,
  versions: [
    {
      n: 1,
      original_filename: "tesis_v1.pdf",
      mime: "application/pdf",
      size_bytes: 1000,
      indexed_at: "2024-01-01T10:00:00+00:00",
      is_current: false,
    },
    {
      n: 2,
      original_filename: "tesis_v2.pdf",
      mime: "application/pdf",
      size_bytes: 2048,
      indexed_at: "2024-02-01T10:00:00+00:00",
      is_current: true,
    },
  ],
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
    const path = new URL(url, "http://localhost").pathname;
    if (routes[path]) return routes[path]();
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

    // Publico carries no visibility badge — the badge only renders for
    // non-publico tiers (interno/privado).
    expect(screen.queryByText("Interno")).toBeNull();
    expect(screen.queryByText("Privado")).toBeNull();
    expect(screen.queryByText("Visibilidad")).toBeNull();
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

  it("renders the Editar CTA and Versiones panel when manageable", async () => {
    mockFetchByUrl({
      "/api/docs/42": () => jsonResponse(MANAGEABLE_DETAIL),
      "/api/areas": () => jsonResponse(AREAS),
    });

    renderPage();

    const editar = await screen.findByRole("link", { name: /editar/i });
    expect(editar).toHaveAttribute("href", "/mis-trabajos/42/editar");
    expect(screen.getByText("Versiones anteriores")).toBeInTheDocument();
    expect(screen.getByText(/tesis_v2\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/tesis_v1\.pdf/)).toBeInTheDocument();
  });

  it("hides the Editar CTA and Versiones panel for non-managers", async () => {
    mockFetchByUrl({
      "/api/docs/42": () => jsonResponse(PUBLICO_DETAIL),
      "/api/areas": () => jsonResponse(AREAS),
    });

    renderPage();

    await screen.findByText("Búsqueda híbrida en repositorios académicos");
    expect(screen.queryByRole("link", { name: /editar/i })).toBeNull();
    expect(screen.queryByText("Versiones anteriores")).toBeNull();
  });

  it("renders the trabajos relacionados rail with up to 5 cards", async () => {
    const related = [
      {
        doc_id: 100,
        titulo: "Vecino A",
        autores: [{ display_name: "Ada", user_id: 1 }],
        area_path: "escuela_ciencia",
        tipo: "paper",
        fecha: "2024-01-15",
        similarity: 0.93,
      },
      {
        doc_id: 101,
        titulo: "Vecino B",
        autores: [{ display_name: "Bob", user_id: 2 }],
        area_path: "escuela_ciencia",
        tipo: "tesis",
        fecha: "2023-09-01",
        similarity: 0.82,
      },
    ];
    mockFetchByUrl({
      "/api/docs/42/related": () => jsonResponse(related),
      "/api/docs/42": () => jsonResponse(PUBLICO_DETAIL),
      "/api/areas": () => jsonResponse(AREAS),
    });

    renderPage();

    await screen.findByText("Vecino A");
    expect(screen.getByText("Vecino B")).toBeInTheDocument();
    // Title links go to the detail page; rail cards are reachable by click.
    expect(screen.getByRole("link", { name: "Vecino A" })).toHaveAttribute(
      "href",
      "/docs/100",
    );
    // No snippet text leaks into the rail cards.
    expect(screen.queryByText(/<mark>/)).toBeNull();
  });

  it("hides the related rail entirely when the list is empty", async () => {
    mockFetchByUrl({
      "/api/docs/42/related": () => jsonResponse([]),
      "/api/docs/42": () => jsonResponse(PUBLICO_DETAIL),
      "/api/areas": () => jsonResponse(AREAS),
    });

    renderPage();

    await screen.findByText("Búsqueda híbrida en repositorios académicos");
    // The rail's header must not render when there are no neighbours.
    expect(screen.queryByText(/trabajos relacionados/i)).toBeNull();
  });

  it("does not fetch related when the detail itself 404s", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.includes("/api/docs/42/related"))
        return jsonResponse([{ doc_id: 9, titulo: "Should not appear" }]);
      if (url.includes("/api/docs/42"))
        return new Response("", { status: 404 });
      if (url.includes("/api/areas")) return jsonResponse(AREAS);
      return new Response("", { status: 404 });
    });

    renderPage();

    await screen.findByText("No encontramos este documento");
    expect(screen.queryByText("Should not appear")).toBeNull();
    const calls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes("/api/docs/42/related"))).toBe(false);
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
