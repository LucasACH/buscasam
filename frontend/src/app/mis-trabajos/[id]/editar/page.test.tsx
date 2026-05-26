import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const { useDraftStateMock, apiPatch } = vi.hoisted(() => ({
  useDraftStateMock: vi.fn(),
  apiPatch: vi.fn(),
}));
vi.mock("../../useDraftState", () => ({ useDraftState: () => useDraftStateMock() }));
vi.mock("@/api/client", () => ({ api: { PATCH: apiPatch } }));
vi.mock("@/lib/useUser", () => ({
  useUser: () => ({ user: { user_id: 1 }, isInvitado: false, isLoading: false, isError: false }),
}));
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "7" }),
  useRouter: () => ({ replace }),
}));

import EditarPage from "./page";

function draft(over: Record<string, unknown>) {
  return {
    state: {
      title: "Mi tesis",
      index_status: "indexed",
      staged_abstract: "resumen extraído",
      staged_keywords: ["redes", "grafos"],
      staged_fecha: "2024-03-01",
      index_error: null,
      publish_gate_reason: null,
      ...over,
    },
    isLoading: false,
    isError: false,
  };
}

describe("editar page", () => {
  beforeEach(() => {
    useDraftStateMock.mockReset();
    apiPatch.mockReset();
    apiPatch.mockResolvedValue({ error: undefined });
  });
  afterEach(() => cleanup());

  it("shows 'Listo para publicar' pill when indexed", () => {
    useDraftStateMock.mockReturnValue(draft({ index_status: "indexed" }));
    render(<EditarPage />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent("Listo para publicar");
  });

  it("shows 'Procesando…' pill while processing", () => {
    useDraftStateMock.mockReturnValue(
      draft({ index_status: "processing", publish_gate_reason: "processing" }),
    );
    render(<EditarPage />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent("Procesando…");
  });

  it("shows 'Falló el procesamiento' pill when failed", () => {
    useDraftStateMock.mockReturnValue(
      draft({ index_status: "failed", publish_gate_reason: "processing_failed" }),
    );
    render(<EditarPage />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent("Falló el procesamiento");
  });

  it("publish button is disabled and echoes the gate reason", () => {
    useDraftStateMock.mockReturnValue(draft({ publish_gate_reason: "reindexing_headline" }));
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeDisabled();
    expect(screen.getByTestId("gate-reason")).toHaveTextContent("Reindexando título…");
  });

  it("publish button stays disabled even when publishable (slice 4)", () => {
    useDraftStateMock.mockReturnValue(draft({ publish_gate_reason: null }));
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeDisabled();
  });

  it("renders the staged suggestions", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(screen.getByTestId("suggestion-abstract")).toHaveTextContent("resumen extraído");
    expect(screen.getByTestId("suggestion-keywords")).toHaveTextContent("redes");
    expect(screen.getByTestId("suggestion-fecha")).toHaveTextContent("2024-03-01");
  });

  it("shows a spinner over the suggestions while processing", () => {
    useDraftStateMock.mockReturnValue(
      draft({ index_status: "processing", staged_abstract: null, staged_keywords: [], staged_fecha: null }),
    );
    render(<EditarPage />);
    expect(screen.getByTestId("suggestions-spinner")).toBeInTheDocument();
  });

  it("PATCHes title on blur", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Viejo" }));
    render(<EditarPage />);
    const input = screen.getByLabelText("Título");
    fireEvent.change(input, { target: { value: "Nuevo título" } });
    fireEvent.blur(input);
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const opts = apiPatch.mock.calls[0]![1];
    expect(opts.body).toMatchObject({ title: "Nuevo título" });
  });

  it("PATCHes keywords as an array on blur", async () => {
    useDraftStateMock.mockReturnValue(draft({ staged_keywords: ["a"] }));
    render(<EditarPage />);
    const input = screen.getByLabelText("Palabras clave");
    fireEvent.change(input, { target: { value: "redes, grafos" } });
    fireEvent.blur(input);
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const opts = apiPatch.mock.calls[0]![1];
    expect(opts.body).toMatchObject({ keywords: ["redes", "grafos"] });
  });
});
