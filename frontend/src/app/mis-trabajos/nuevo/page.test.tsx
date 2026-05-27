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

import NuevoPage from "./page";

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  { area_path: "escuela_ciencia.carrera_informatica", display_name: "Ing. Informática" },
  {
    area_path: "escuela_ciencia.carrera_informatica.materia_bd",
    display_name: "Bases de Datos",
  },
];

type Handler = (url: string, init: RequestInit | undefined) => Response | Promise<Response>;

function setupFetch(handlers: Record<string, Handler>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    for (const [key, h] of Object.entries(handlers)) {
      if (url.includes(key)) return h(url, init);
    }
    return new Response("not mocked", { status: 500 });
  });
}

function jsonResp(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
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
    vi.spyOn(global, "fetch").mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("submits the draft + upload and navigates to /editar/{id}", async () => {
    const spy = setupFetch({
      "/api/areas": () => jsonResp(AREAS),
      "/api/users/search": () => jsonResp([]),
      "/api/documents/42/upload": () => new Response("", { status: 202 }),
      "/api/documents": (url, init) => {
        if (init?.method === "POST") return jsonResp({ id: 42 }, 201);
        return new Response("", { status: 404 });
      },
    });

    wrap(<NuevoPage />);

    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/mis-trabajos/42/editar"));

    const createCall = spy.mock.calls.find(([u, i]) => {
      const url = typeof u === "string" ? u : (u as Request).url;
      return url.endsWith("/api/documents") && (i as RequestInit | undefined)?.method === "POST";
    });
    expect(createCall).toBeTruthy();
    const body = JSON.parse((createCall![1] as RequestInit).body as string);
    expect(body).toMatchObject({
      title: "Mi tesis sobre BD",
      area_path: "escuela_ciencia.carrera_informatica.materia_bd",
      document_type: "tesis",
      visibility: "publico",
    });
  });

  it("surfaces the 415 detail inline when the upload is rejected", async () => {
    setupFetch({
      "/api/areas": () => jsonResp(AREAS),
      "/api/users/search": () => jsonResp([]),
      "/api/documents/42/upload": () =>
        jsonResp(
          {
            detail:
              "Este PDF está protegido por contraseña — quitá la protección y reintentá",
          },
          415,
        ),
      "/api/documents": (url, init) => {
        if (init?.method === "POST") return jsonResp({ id: 42 }, 201);
        return new Response("", { status: 404 });
      },
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
    setupFetch({
      "/api/areas": () => jsonResp(AREAS),
      "/api/users/search": () => jsonResp([]),
      "/api/documents/42/upload": () =>
        jsonResp({ detail: "El archivo supera los 50 MB" }, 413),
      "/api/documents": (url, init) => {
        if (init?.method === "POST") return jsonResp({ id: 42 }, 201);
        return new Response("", { status: 404 });
      },
    });

    wrap(<NuevoPage />);
    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/50 MB/);
    expect(replace).not.toHaveBeenCalled();
  });

  it("surfaces the 422 detail inline when create_draft fails (e.g. unknown coauthor)", async () => {
    setupFetch({
      "/api/areas": () => jsonResp(AREAS),
      "/api/users/search": () => jsonResp([]),
      "/api/documents": (url, init) => {
        if (init?.method === "POST")
          return jsonResp({ detail: "Unknown coauthor user_id(s): [99]" }, 422);
        return new Response("", { status: 404 });
      },
    });

    wrap(<NuevoPage />);
    const user = await fillRequiredFields();
    await user.click(screen.getByRole("button", { name: /subir/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/coauthor/i);
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects to /login when the user is invitado", async () => {
    useUserMock.mockReturnValueOnce({
      user: null,
      isInvitado: true,
      isLoading: false,
      isError: false,
    });
    setupFetch({});

    wrap(<NuevoPage />);

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/login?next=/mis-trabajos/nuevo"),
    );
  });
});
