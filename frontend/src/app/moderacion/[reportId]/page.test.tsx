import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

const { useUserMock } = vi.hoisted(() => ({ useUserMock: vi.fn() }));
vi.mock("@/lib/useUser", () => ({ useUser: () => useUserMock() }));

const { useInspectMock, hide, unhide, dismiss } = vi.hoisted(() => ({
  useInspectMock: vi.fn(),
  hide: vi.fn(),
  unhide: vi.fn(),
  dismiss: vi.fn(),
}));
vi.mock("./useInspect", () => ({ useInspect: () => useInspectMock() }));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

const replace = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ reportId: "42" }),
  useRouter: () => ({ replace, push }),
}));

import InspectPage from "./page";

const META = {
  titulo: "Tesis reportada",
  abstract: "Un resumen del trabajo",
  palabras_clave: ["redes", "seguridad"],
  autores: [
    { display_name: "Ana Pérez", user_id: 1 },
    { display_name: "Beto Díaz", user_id: null },
  ],
  tipo: "tesis",
  area_path: "ingenieria.sistemas",
  report_reasons: ["spam", "plagio"],
};

function docente() {
  useUserMock.mockReturnValue({
    user: { user_id: 1, role: "docente" },
    isInvitado: false,
    isLoading: false,
    isError: false,
  });
}

function inspect(over: Record<string, unknown> = {}) {
  useInspectMock.mockReturnValue({
    metadata: META,
    isLoading: false,
    isError: false,
    hide,
    unhide,
    dismiss,
    ...over,
  });
}

describe("/moderacion/[reportId] inspect view", () => {
  beforeEach(() => {
    replace.mockReset();
    push.mockReset();
    toastError.mockReset();
    useUserMock.mockReset();
    useInspectMock.mockReset();
    hide.mockReset().mockResolvedValue(undefined);
    unhide.mockReset().mockResolvedValue(undefined);
    dismiss.mockReset().mockResolvedValue(undefined);
    docente();
    inspect();
  });
  afterEach(() => cleanup());

  it("renders the reported document's metadata", () => {
    render(<InspectPage />);

    expect(screen.getByText("Tesis reportada")).toBeInTheDocument();
    expect(screen.getByText("Un resumen del trabajo")).toBeInTheDocument();
    expect(screen.getByText(/redes, seguridad/)).toBeInTheDocument();
    expect(screen.getByText(/Ana Pérez/)).toBeInTheDocument();
    expect(screen.getByText(/Beto Díaz/)).toBeInTheDocument();
    expect(screen.getByText(/tesis/)).toBeInTheDocument();
    expect(screen.getByText(/ingenieria\.sistemas/)).toBeInTheDocument();
  });

  it("links to the current main-file download", () => {
    render(<InspectPage />);

    expect(
      screen.getByRole("link", { name: /descargar/i }),
    ).toHaveAttribute("href", "/api/moderation/reports/42/download");
  });

  it("shows why the document was reported", () => {
    render(<InspectPage />);

    expect(screen.getByText("Reportado por")).toBeInTheDocument();
    expect(screen.getByText("Spam, Plagio")).toBeInTheDocument();
  });

  it("allows Ocultar without a motivo (it is an optional note)", () => {
    render(<InspectPage />);

    expect(screen.getByRole("button", { name: /ocultar/i })).toBeEnabled();
  });

  it("hides with the reason and returns to the queue on success", async () => {
    render(<InspectPage />);

    fireEvent.change(screen.getByLabelText(/motivo/i), {
      target: { value: "plagio comprobado" },
    });
    fireEvent.click(screen.getByRole("button", { name: /ocultar/i }));

    await waitFor(() =>
      expect(hide).toHaveBeenCalledWith("plagio comprobado"),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/moderacion"));
  });

  it.each([
    ["mostrar", () => unhide],
    ["descartar", () => dismiss],
  ] as const)("%s acts with an empty reason and returns to the queue", async (name, getFn) => {
    render(<InspectPage />);

    const btn = screen.getByRole("button", { name: new RegExp(name, "i") });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);

    await waitFor(() => expect(getFn()).toHaveBeenCalledWith(""));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/moderacion"));
  });

  it("toasts and stays on the page when hiding fails", async () => {
    hide.mockResolvedValue("action_failed");
    render(<InspectPage />);

    fireEvent.change(screen.getByLabelText(/motivo/i), {
      target: { value: "x" },
    });
    fireEvent.click(screen.getByRole("button", { name: /ocultar/i }));

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it("shows a not-found message when the inspect load fails", () => {
    inspect({ metadata: null, isError: true });

    render(<InspectPage />);

    expect(screen.getByText(/no se pudo cargar el reporte/i)).toBeInTheDocument();
  });

  it("redirects an invitado to login, preserving the next path", () => {
    useUserMock.mockReturnValue({
      user: null,
      isInvitado: true,
      isLoading: false,
      isError: false,
    });

    render(<InspectPage />);

    expect(replace).toHaveBeenCalledWith("/login?next=/moderacion/42");
  });

  it("redirects a non-Docente to home", () => {
    useUserMock.mockReturnValue({
      user: { user_id: 2, role: "estudiante" },
      isInvitado: false,
      isLoading: false,
      isError: false,
    });

    render(<InspectPage />);

    expect(replace).toHaveBeenCalledWith("/");
  });
});
