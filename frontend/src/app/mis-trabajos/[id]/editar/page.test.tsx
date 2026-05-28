import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

const { useDraftStateMock, apiPatch, apiPost, toastError, refreshDraft } =
  vi.hoisted(() => ({
    useDraftStateMock: vi.fn(),
    apiPatch: vi.fn(),
    apiPost: vi.fn(),
    toastError: vi.fn(),
    refreshDraft: vi.fn(),
  }));
vi.mock("../../useDraftState", () => ({
  useDraftState: () => useDraftStateMock(),
}));
vi.mock("@/api/client", () => ({ api: { PATCH: apiPatch, POST: apiPost } }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));
vi.mock("@/components/AttachmentsPanel", () => ({
  AttachmentsPanel: () => null,
}));
vi.mock("@/components/CoauthorsPanel", () => ({
  CoauthorsPanel: () => null,
}));
const { candidatePanelMock, versionsPanelMock } = vi.hoisted(() => ({
  candidatePanelMock: vi.fn((_props: unknown) => null),
  versionsPanelMock: vi.fn((_props: unknown) => null),
}));
vi.mock("@/components/CandidatePanel", () => ({
  CandidatePanel: (props: unknown) => candidatePanelMock(props),
}));
vi.mock("@/components/VersionsPanel", () => ({
  VersionsPanel: (props: unknown) => versionsPanelMock(props),
}));
vi.mock("@/lib/useUser", () => ({
  useUser: () => ({
    user: { user_id: 1 },
    isInvitado: false,
    isLoading: false,
    isError: false,
  }),
}));
const replace = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "7" }),
  useRouter: () => ({ replace, push }),
}));

import EditarPage from "./page";

function draft(
  over: Record<string, unknown> = {},
  lifecycle: Record<string, unknown> = {},
) {
  return {
    state: {
      title: "Mi tesis",
      staged_abstract: "resumen extraído",
      staged_keywords: ["redes", "grafos"],
      staged_fecha: "2024-03-01",
      isOwner: true,
      candidate: null,
      versions: [],
      ...over,
      lifecycle: {
        formSeedKey: "indexed",
        statusLabel: "Listo para publicar",
        showSuggestionsSpinner: false,
        gateMessage: null,
        canPublish: true,
        ...lifecycle,
      },
    },
    isLoading: false,
    isError: false,
    refresh: refreshDraft,
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
    refreshDraft.mockReset();
    refreshDraft.mockResolvedValue(undefined);
    push.mockReset();
    candidatePanelMock.mockClear();
    versionsPanelMock.mockClear();
  });
  afterEach(() => cleanup());

  it("mounts CandidatePanel with the owner publish flag and VersionsPanel", () => {
    useDraftStateMock.mockReturnValue(
      draft({
        isOwner: true,
        versions: [
          {
            n: 1,
            original_filename: "v1.pdf",
            mime: "application/pdf",
            size_bytes: 10,
            indexed_at: null,
            is_current: true,
          },
        ],
      }),
    );
    render(<EditarPage />);

    expect(candidatePanelMock).toHaveBeenCalledWith(
      expect.objectContaining({ docId: 7, canPublish: true }),
    );
    expect(versionsPanelMock).toHaveBeenCalledWith(
      expect.objectContaining({ docId: 7, canManage: true }),
    );
  });

  it("forwards a non-owner publish flag to CandidatePanel", () => {
    useDraftStateMock.mockReturnValue(draft({ isOwner: false }));
    render(<EditarPage />);

    expect(candidatePanelMock).toHaveBeenCalledWith(
      expect.objectContaining({ docId: 7, canPublish: false }),
    );
  });

  it("shows 'Listo para publicar' pill when indexed", () => {
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent(
      "Listo para publicar",
    );
  });

  it("shows 'Procesando…' pill while processing", () => {
    useDraftStateMock.mockReturnValue(
      draft({}, { statusLabel: "Procesando…", showSuggestionsSpinner: true }),
    );
    render(<EditarPage />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent("Procesando…");
  });

  it("shows 'Falló el procesamiento' pill when failed", () => {
    useDraftStateMock.mockReturnValue(
      draft({}, { statusLabel: "Falló el procesamiento", canPublish: false }),
    );
    render(<EditarPage />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent(
      "Falló el procesamiento",
    );
  });

  it("publish button is disabled and echoes the gate reason", () => {
    useDraftStateMock.mockReturnValue(
      draft({}, { gateMessage: "Reindexando título…", canPublish: false }),
    );
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeDisabled();
    expect(screen.getByTestId("gate-reason")).toHaveTextContent(
      "Reindexando título…",
    );
  });

  it("publish button is enabled when publishable and the user is the owner", () => {
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeEnabled();
  });

  it("publish button is disabled for a non-owner even when publishable", () => {
    useDraftStateMock.mockReturnValue(draft({}, { canPublish: false }));
    render(<EditarPage />);
    expect(screen.getByRole("button", { name: /publicar/i })).toBeDisabled();
  });

  it("publishes and navigates to /mis-trabajos on success", async () => {
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    fireEvent.click(screen.getByRole("button", { name: /publicar/i }));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    const [path, opts] = apiPost.mock.calls[0]!;
    expect(path).toBe("/api/documents/{doc_id}/publish");
    expect(opts.params.path).toMatchObject({ doc_id: 7 });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mis-trabajos"));
  });

  it("on a 409 race, refetches the draft instead of navigating", async () => {
    apiPost.mockResolvedValue({
      error: { detail: "conflict" },
      response: { status: 409 },
    });
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    fireEvent.click(screen.getByRole("button", { name: /publicar/i }));
    await waitFor(() => expect(refreshDraft).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });

  it("toasts and re-enables the Publicar button if the publish request rejects", async () => {
    apiPost.mockRejectedValue(new Error("network down"));
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    const btn = screen.getByRole("button", { name: /publicar/i });
    fireEvent.click(btn);
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(btn).toBeEnabled();
    expect(push).not.toHaveBeenCalled();
  });

  it("renders the staged suggestions", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(screen.getByTestId("suggestion-abstract")).toHaveTextContent(
      "resumen extraído",
    );
    expect(screen.getByTestId("suggestion-keywords")).toHaveTextContent(
      "redes",
    );
    expect(screen.getByTestId("suggestion-fecha")).toHaveTextContent(
      "2024-03-01",
    );
  });

  it("shows a spinner over the suggestions while processing", () => {
    useDraftStateMock.mockReturnValue(
      draft(
        { staged_abstract: null, staged_keywords: [], staged_fecha: null },
        { showSuggestionsSpinner: true, canPublish: false },
      ),
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
      draft({ staged_abstract: null }, { formSeedKey: "processing" }),
    );
    const { rerender } = render(<EditarPage />);
    expect(screen.getByLabelText("Resumen")).toHaveValue("");

    useDraftStateMock.mockReturnValue(
      draft({ staged_abstract: "resumen extraído" }),
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
    expect(refreshDraft).not.toHaveBeenCalled();
  });

  it("refetches draft state after a successful save so a new gate is observed", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Viejo" }));
    render(<EditarPage />);
    const input = screen.getByLabelText("Título");
    fireEvent.change(input, { target: { value: "Nuevo título" } });
    fireEvent.blur(input);
    await waitFor(() => expect(refreshDraft).toHaveBeenCalled());
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
