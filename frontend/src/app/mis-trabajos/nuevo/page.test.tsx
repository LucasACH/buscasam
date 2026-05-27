import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { useUserMock } = vi.hoisted(() => ({
  useUserMock: vi.fn<() => {
    user: { user_id: number; role: string } | null;
    isInvitado: boolean;
    isLoading: boolean;
    isError: boolean;
  }>(() => ({
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
const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: { GET: apiGet, POST: apiPost } }));

import NuevoPage from "./page";

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  { area_path: "escuela_ciencia.carrera_informatica", display_name: "Ing. Informática" },
  {
    area_path: "escuela_ciencia.carrera_informatica.materia_bd",
    display_name: "Bases de Datos",
  },
];

function setupHappyApi() {
  apiGet.mockImplementation(async (path: string) => {
    if (path === "/api/areas") return { data: AREAS };
    if (path === "/api/users/search") return { data: [] };
    return { error: { detail: "not mocked" } };
  });
}

function mockUpload(handler: (url: string) => Response) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    return handler(url);
  });
}

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function fillRequiredFields() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/título/i), "Mi tesis sobre BD");

  // Cascade through Escuela → Carrera → Materia.
  const escuela = await screen.findByRole("combobox", { name: /escuela/i });
  await waitFor(() => expect(escuela).toHaveTextContent(/Ciencia/));
  await user.selectOptions(escuela, "escuela_ciencia");
  await user.selectOptions(
    await screen.findByRole("combobox", { name: /carrera/i }),
    "escuela_ciencia.carrera_informatica",
  );
  await user.selectOptions(
    await screen.findByRole("combobox", { name: /materia/i }),
    "escuela_ciencia.carrera_informatica.materia_bd",
  );

  await user.selectOptions(screen.getByLabelText(/tipo/i), "tesis");
  await user.click(screen.getByLabelText(/público/i));

  const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "tesis.pdf", {
    type: "application/pdf",
  });
  await user.upload(screen.getByLabelText(/archivo/i), file);
  return user;
}

describe("/mis-trabajos/nuevo page", () => {
  beforeEach(() => {
    replace.mockReset();
    apiGet.mockReset();
    apiPost.mockReset();
    setupHappyApi();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("submits the draft + upload and navigates to /editar/{id}", async () => {
    apiPost.mockResolvedValue({ data: { id: 42 } });
    mockUpload((url) => {
      if (url.endsWith("/api/documents/42/upload")) {
        return new Response("", { status: 202 });
      }
      return new Response("", { status: 404 });
    });

    wrap(<NuevoPage />);

    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/mis-trabajos/42/editar"));

    const createCall = apiPost.mock.calls.find(([p]) => p === "/api/documents");
    expect(createCall).toBeTruthy();
    expect(createCall![1]).toMatchObject({
      body: {
        title: "Mi tesis sobre BD",
        area_path: "escuela_ciencia.carrera_informatica.materia_bd",
        document_type: "tesis",
        visibility: "publico",
      },
    });
  });

  it("surfaces the 415 detail inline when the upload is rejected", async () => {
    apiPost.mockResolvedValue({ data: { id: 42 } });
    mockUpload((url) => {
      if (url.endsWith("/api/documents/42/upload")) {
        return new Response(
          JSON.stringify({
            detail:
              "Este PDF está protegido por contraseña — quitá la protección y reintentá",
          }),
          { status: 415, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("", { status: 404 });
    });

    wrap(<NuevoPage />);
    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(/protegido por contraseña/);
    expect(replace).not.toHaveBeenCalled();
  });

  it("surfaces a 413 inline error when the file is too large", async () => {
    apiPost.mockResolvedValue({ data: { id: 42 } });
    mockUpload((url) => {
      if (url.endsWith("/api/documents/42/upload")) {
        return new Response(JSON.stringify({ detail: "El archivo supera los 50 MB" }), {
          status: 413,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("", { status: 404 });
    });

    wrap(<NuevoPage />);
    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/50 MB/);
    expect(replace).not.toHaveBeenCalled();
  });

  it("surfaces the 422 detail inline when create_draft fails (e.g. unknown coauthor)", async () => {
    apiPost.mockResolvedValue({
      error: { detail: "Unknown coauthor user_id(s): [99]" },
    });
    mockUpload(() => new Response("", { status: 404 }));

    wrap(<NuevoPage />);
    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/coauthor/i);
    expect(replace).not.toHaveBeenCalled();
  });

  it("surfaces a generic error when the network is unreachable", async () => {
    apiPost.mockRejectedValue(new TypeError("Failed to fetch"));
    mockUpload(() => new Response("", { status: 404 }));

    wrap(<NuevoPage />);
    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /No se pudo conectar con el servidor/,
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects to /login when the user is invitado", async () => {
    useUserMock.mockReturnValueOnce({
      user: null,
      isInvitado: true,
      isLoading: false,
      isError: false,
    });

    wrap(<NuevoPage />);

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/login?next=/mis-trabajos/nuevo"),
    );
  });
});
