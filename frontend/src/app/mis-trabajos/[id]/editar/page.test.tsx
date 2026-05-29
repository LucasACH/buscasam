import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

const {
  useDraftStateMock,
  apiPatch,
  toastError,
  refreshDraft,
  publishMock,
  softDeleteMock,
  attachmentActions,
} = vi.hoisted(() => ({
  useDraftStateMock: vi.fn(),
  apiPatch: vi.fn(),
  toastError: vi.fn(),
  refreshDraft: vi.fn(),
  publishMock: vi.fn(),
  softDeleteMock: vi.fn(),
  attachmentActions: { add: vi.fn(), remove: vi.fn() },
}));
vi.mock("../../useDraftState", () => ({
  useDraftState: () => useDraftStateMock(),
}));
vi.mock("@/api/client", () => ({ api: { PATCH: apiPatch } }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));
vi.mock("@/components/CoauthorsPanel", () => ({
  CoauthorsPanel: () => null,
}));
const { attachmentsPanelMock, candidatePanelMock, versionsPanelMock } =
  vi.hoisted(() => ({
    attachmentsPanelMock: vi.fn<(props: unknown) => null>(() => null),
    candidatePanelMock: vi.fn<(props: unknown) => null>(() => null),
    versionsPanelMock: vi.fn<(props: unknown) => null>(() => null),
  }));
vi.mock("@/components/AttachmentsPanel", () => ({
  AttachmentsPanel: (props: unknown) => attachmentsPanelMock(props),
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
      generated_abstract: "resumen extraído",
      generated_keywords: ["redes", "grafos"],
      generated_fecha: "2024-03-01",
      isOwner: true,
      candidate: null,
      versions: [],
      attachments: [],
      ...over,
      lifecycle: {
        formSeedKey: "indexed",
        statusLabel: "Listo para publicar",
        showSuggestionsSpinner: false,
        gateMessage: null,
        canPublish: true,
        initialPhase: "ready",
        ...lifecycle,
      },
    },
    isLoading: false,
    isError: false,
    refresh: refreshDraft,
    actions: {
      publish: publishMock,
      softDelete: softDeleteMock,
      attachments: attachmentActions,
      replace: vi.fn(),
      discard: vi.fn(),
    },
  };
}

describe("editar page", () => {
  beforeEach(() => {
    useDraftStateMock.mockReset();
    apiPatch.mockReset();
    apiPatch.mockResolvedValue({ error: undefined });
    toastError.mockReset();
    refreshDraft.mockReset();
    refreshDraft.mockResolvedValue(undefined);
    publishMock.mockReset();
    publishMock.mockResolvedValue("published");
    softDeleteMock.mockReset();
    softDeleteMock.mockResolvedValue(undefined);
    attachmentActions.add.mockReset();
    attachmentActions.remove.mockReset();
    push.mockReset();
    attachmentsPanelMock.mockClear();
    candidatePanelMock.mockClear();
    versionsPanelMock.mockClear();
  });
  afterEach(() => cleanup());

  it("blocks the page with a loader while the initial version is indexing", () => {
    useDraftStateMock.mockReturnValue(
      draft(
        { staged_abstract: null, staged_keywords: [], staged_fecha: null },
        {
          initialPhase: "indexing",
          statusLabel: "Procesando…",
          canPublish: false,
        },
      ),
    );
    render(<EditarPage />);

    expect(screen.getByTestId("status-pill")).toHaveTextContent("Procesando…");
    expect(screen.getByTestId("indexing-block")).toBeInTheDocument();
    expect(screen.queryByLabelText("Título")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /publicar/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /eliminar/i }),
    ).not.toBeInTheDocument();
    expect(candidatePanelMock).not.toHaveBeenCalled();
    expect(versionsPanelMock).not.toHaveBeenCalled();
    expect(attachmentsPanelMock).not.toHaveBeenCalled();
  });

  it("shows the failure message and Eliminar for a failed initial draft", () => {
    useDraftStateMock.mockReturnValue(
      draft(
        { isOwner: true },
        {
          initialPhase: "failed",
          statusLabel: "Falló el procesamiento",
          gateMessage: "Falló el procesamiento — revisá tu archivo",
          canPublish: false,
        },
      ),
    );
    render(<EditarPage />);

    expect(screen.getByTestId("failed-block")).toHaveTextContent(
      "Falló el procesamiento — revisá tu archivo",
    );
    expect(
      screen.getByRole("button", { name: /eliminar/i }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Título")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /publicar/i }),
    ).not.toBeInTheDocument();
    expect(candidatePanelMock).not.toHaveBeenCalled();
    expect(attachmentsPanelMock).not.toHaveBeenCalled();
  });

  it("dismisses the loader and shows the prefilled form once indexing finishes", () => {
    useDraftStateMock.mockReturnValue(
      draft(
        { staged_abstract: null, staged_keywords: [], staged_fecha: null },
        { initialPhase: "indexing", statusLabel: "Procesando…" },
      ),
    );
    const { rerender } = render(<EditarPage />);
    expect(screen.getByTestId("indexing-block")).toBeInTheDocument();

    useDraftStateMock.mockReturnValue(
      draft({ title: "Mi tesis", staged_abstract: "resumen extraído" }),
    );
    rerender(<EditarPage />);

    expect(screen.queryByTestId("indexing-block")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Título")).toHaveValue("Mi tesis");
    expect(screen.getByLabelText("Resumen")).toHaveValue("resumen extraído");
  });

  it("mounts presentational panels with projected draft state and actions", () => {
    const versions = [
      {
        n: 1,
        original_filename: "v1.pdf",
        mime: "application/pdf",
        size_bytes: 10,
        indexed_at: null,
        is_current: true,
      },
    ];
    const attachments = [
      {
        id: 2,
        original_filename: "data.csv",
        mime: "text/csv",
        size_bytes: 10,
      },
    ];
    useDraftStateMock.mockReturnValue(
      draft({
        isOwner: true,
        versions,
        attachments,
      }),
    );
    render(<EditarPage />);

    expect(candidatePanelMock).toHaveBeenCalledWith(
      expect.objectContaining({
        candidate: null,
        actions: expect.objectContaining({ publish: publishMock }),
      }),
    );
    expect(versionsPanelMock).toHaveBeenCalledWith(
      expect.objectContaining({ docId: 7, versions, canManage: true }),
    );
    expect(attachmentsPanelMock).toHaveBeenCalledWith(
      expect.objectContaining({
        attachments,
        actions: attachmentActions,
        canManage: true,
      }),
    );
  });

  it("hides the form Publicar once the doc has a published version", () => {
    // CandidatePanel owns the candidate Publicar after the first publish; the
    // form button is the initial-publication affordance only.
    useDraftStateMock.mockReturnValue(
      draft({
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

    expect(
      screen.queryByRole("button", { name: /publicar/i }),
    ).not.toBeInTheDocument();
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
    await waitFor(() => expect(publishMock).toHaveBeenCalled());
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mis-trabajos"));
  });

  it("stays put when the draft action refreshes after a publish race", async () => {
    publishMock.mockResolvedValue("refreshed");
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    fireEvent.click(screen.getByRole("button", { name: /publicar/i }));
    await waitFor(() => expect(publishMock).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("toasts and re-enables the Publicar button if the publish request rejects", async () => {
    publishMock.mockRejectedValue(new Error("network down"));
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    const btn = screen.getByRole("button", { name: /publicar/i });
    fireEvent.click(btn);
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(btn).toBeEnabled();
    expect(push).not.toHaveBeenCalled();
  });

  it("toasts when the draft action returns a publish failure", async () => {
    publishMock.mockResolvedValue("publish_failed");
    useDraftStateMock.mockReturnValue(draft());
    render(<EditarPage />);
    fireEvent.click(screen.getByRole("button", { name: /publicar/i }));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("No se pudo publicar"),
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("no longer renders the 'Sugerencias del extractor' panel", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(
      screen.queryByText("Sugerencias del extractor"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("suggestion-abstract")).not.toBeInTheDocument();
  });

  it("hides Restaurar when staged equals the generated snapshot", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(screen.queryByTestId("restore-abstract")).not.toBeInTheDocument();
    expect(screen.queryByTestId("restore-keywords")).not.toBeInTheDocument();
    expect(screen.queryByTestId("restore-fecha")).not.toBeInTheDocument();
  });

  it("shows Restaurar only for fields whose staged value diverges", () => {
    useDraftStateMock.mockReturnValue(
      draft({
        staged_abstract: "resumen editado",
        staged_keywords: ["editado"],
        // staged_fecha unchanged from generated → no Restaurar
      }),
    );
    render(<EditarPage />);
    expect(screen.getByTestId("restore-abstract")).toBeInTheDocument();
    expect(screen.getByTestId("restore-keywords")).toBeInTheDocument();
    expect(screen.queryByTestId("restore-fecha")).not.toBeInTheDocument();
  });

  it("never offers Restaurar for título (author-entered, not generated)", () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Otro título" }));
    render(<EditarPage />);
    expect(screen.queryByTestId("restore-titulo")).not.toBeInTheDocument();
  });

  it("Restaurar reverts the field to the generated value and PATCHes it", async () => {
    useDraftStateMock.mockReturnValue(
      draft({
        staged_abstract: "resumen editado",
        generated_abstract: "resumen del extractor",
      }),
    );
    render(<EditarPage />);
    expect(screen.getByLabelText("Resumen")).toHaveValue("resumen editado");

    fireEvent.click(screen.getByTestId("restore-abstract"));

    await waitFor(() =>
      expect(screen.getByLabelText("Resumen")).toHaveValue(
        "resumen del extractor",
      ),
    );
    const opts = apiPatch.mock.calls[0]![1];
    expect(opts.body).toMatchObject({ abstract: "resumen del extractor" });
    await waitFor(() => expect(refreshDraft).toHaveBeenCalled());
  });

  it("Restaurar for keywords PATCHes the generated array", async () => {
    useDraftStateMock.mockReturnValue(
      draft({
        staged_keywords: ["editado"],
        generated_keywords: ["redes", "grafos"],
      }),
    );
    render(<EditarPage />);
    fireEvent.click(screen.getByTestId("restore-keywords"));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const opts = apiPatch.mock.calls[0]![1];
    expect(opts.body).toMatchObject({ keywords: ["redes", "grafos"] });
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

  it("shows the Eliminar affordance to the owner", () => {
    useDraftStateMock.mockReturnValue(draft({ isOwner: true }));
    render(<EditarPage />);
    expect(
      screen.getByRole("button", { name: /eliminar/i }),
    ).toBeInTheDocument();
  });

  it("hides Eliminar from a non-owner", () => {
    useDraftStateMock.mockReturnValue(draft({ isOwner: false }));
    render(<EditarPage />);
    expect(
      screen.queryByRole("button", { name: /eliminar/i }),
    ).not.toBeInTheDocument();
  });

  it("deletes and navigates to /mis-trabajos on success", async () => {
    useDraftStateMock.mockReturnValue(draft({ isOwner: true }));
    render(<EditarPage />);
    await confirmDelete();
    await waitFor(() => expect(softDeleteMock).toHaveBeenCalled());
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mis-trabajos"));
  });

  it("toasts and stays on the page if the delete fails", async () => {
    softDeleteMock.mockResolvedValue("delete_failed");
    useDraftStateMock.mockReturnValue(draft({ isOwner: true }));
    render(<EditarPage />);
    await confirmDelete();
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
  });
});

// Eliminar lives behind an AlertDialog: open it, then click the confirm action.
async function confirmDelete() {
  fireEvent.click(screen.getByRole("button", { name: /eliminar/i }));
  const buttons = await screen.findAllByRole("button", { name: /eliminar/i });
  fireEvent.click(buttons[buttons.length - 1]!);
}
