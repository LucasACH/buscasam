import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const { useDraftStateMock, apiPatch, apiPost, toastError, invalidateQueries } = vi.hoisted(() => ({
  useDraftStateMock: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
  toastError: vi.fn(),
  invalidateQueries: vi.fn(),
}));
vi.mock("../../useDraftState", () => ({
  useDraftState: () => useDraftStateMock(),
  draftQueryKey: (docId: number) => ["draft", docId],
}));
vi.mock("@/api/client", () => ({ api: { PATCH: apiPatch, POST: apiPost } }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ invalidateQueries }) }));
vi.mock("@/lib/useUser", () => ({
  useUser: () => ({ user: { user_id: 1 }, isInvitado: false, isLoading: false, isError: false }),
}));
const replace = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "7" }),
  useRouter: () => ({ replace, push }),
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
      is_owner: true,
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
    apiPost.mockReset();
    apiPost.mockResolvedValue({ error: undefined, response: { status: 204 } });
    toastError.mockReset();
    invalidateQueries.mockReset();
    push.mockReset();
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

  it("publish button is enabled when publishable and the user is the owner", () => {
    useDraftStateMock.mockReturnValue(draft({ publish_gate_reason: null, is_owner: true }));
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeEnabled();
  });

  it("publish button is disabled for a non-owner even when publishable", () => {
    useDraftStateMock.mockReturnValue(draft({ publish_gate_reason: null, is_owner: false }));
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeDisabled();
  });

  it("publishes and navigates to /mis-trabajos on success", async () => {
    useDraftStateMock.mockReturnValue(draft({ publish_gate_reason: null, is_owner: true }));
    render(<EditarPage />);
    fireEvent.click(screen.getByRole("button", { name: /publicar/i }));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    const [path, opts] = apiPost.mock.calls[0]!;
    expect(path).toBe("/api/documents/{doc_id}/publish");
    expect(opts.params.path).toMatchObject({ doc_id: 7 });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mis-trabajos"));
  });

  it("on a 409 race, refetches the draft instead of navigating", async () => {
    apiPost.mockResolvedValue({ error: { detail: "conflict" }, response: { status: 409 } });
    useDraftStateMock.mockReturnValue(draft({ publish_gate_reason: null, is_owner: true }));
    render(<EditarPage />);
    fireEvent.click(screen.getByRole("button", { name: /publicar/i }));
    await waitFor(() =>
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["draft", 7] }),
    );
    expect(push).not.toHaveBeenCalled();
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

  it("re-seeds editable inputs when processing finishes", () => {
    useDraftStateMock.mockReturnValue(
      draft({ index_status: "processing", staged_abstract: null }),
    );
    const { rerender } = render(<EditarPage />);
    expect(screen.getByLabelText("Resumen")).toHaveValue("");

    useDraftStateMock.mockReturnValue(
      draft({ index_status: "indexed", staged_abstract: "resumen extraído" }),
    );
    rerender(<EditarPage />);
    expect(screen.getByLabelText("Resumen")).toHaveValue("resumen extraído");
  });

  it("toasts when a save-on-blur PATCH fails", async () => {
    apiPatch.mockResolvedValue({ error: { detail: "boom" } });
    useDraftStateMock.mockReturnValue(draft({ title: "Mi tesis" }));
    render(<EditarPage />);
    const input = screen.getByLabelText("Título");
    fireEvent.change(input, { target: { value: "Nuevo" } });
    fireEvent.blur(input);
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it("refetches draft state after a successful save so a new gate is observed", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Viejo", publish_gate_reason: null }));
    render(<EditarPage />);
    const input = screen.getByLabelText("Título");
    fireEvent.change(input, { target: { value: "Nuevo título" } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["draft", 7] }),
    );
  });

  it("does not PATCH when a field is blurred without changes", async () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    fireEvent.blur(screen.getByLabelText("Título"));
    fireEvent.blur(screen.getByLabelText("Resumen"));
    await Promise.resolve();
    expect(apiPatch).not.toHaveBeenCalled();
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
