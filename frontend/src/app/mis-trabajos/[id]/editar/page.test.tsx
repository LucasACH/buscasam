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
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));
vi.mock("@/components/CoauthorsPanel", () => ({
  CoauthorsPanel: () => null,
}));
vi.mock("@/components/AreaField", () => ({
  AreaField: () => null,
}));
vi.mock("@/components/DatePicker", () => ({
  DatePicker: ({
    id,
    value,
    onChange,
  }: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
  }) => (
    <input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
  ),
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
      isOwner: true,
      area_path: "escuela.carrera.materia",
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
    replace.mockReset();
    attachmentsPanelMock.mockClear();
    candidatePanelMock.mockClear();
    versionsPanelMock.mockClear();
  });
  afterEach(() => cleanup());

  it("redirects to Mis trabajos when the draft fails to load (e.g. not manageable)", () => {
    useDraftStateMock.mockReturnValue({
      ...draft(),
      state: undefined,
      isError: true,
    });
    render(<EditarPage />);

    expect(replace).toHaveBeenCalledWith("/mis-trabajos");
  });

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
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mis-trabajos"), {
      timeout: 5000,
    });
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
    await waitFor(
      () => expect(toastError).toHaveBeenCalledWith("No se pudo publicar"),
      { timeout: 3000 },
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

  it("hides Restaurar while the form is pristine", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(screen.queryByTestId("restore-titulo")).not.toBeInTheDocument();
    expect(screen.queryByTestId("restore-abstract")).not.toBeInTheDocument();
    expect(screen.queryByTestId("restore-keywords")).not.toBeInTheDocument();
    expect(screen.queryByTestId("restore-fecha")).not.toBeInTheDocument();
  });

  it("shows Restaurar only for fields with unsaved changes", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Resumen"), {
      target: { value: "resumen editado" },
    });
    fireEvent.change(screen.getByLabelText("Palabras clave"), {
      target: { value: "editado" },
    });
    // fecha untouched → no Restaurar
    expect(screen.getByTestId("restore-abstract")).toBeInTheDocument();
    expect(screen.getByTestId("restore-keywords")).toBeInTheDocument();
    expect(screen.queryByTestId("restore-fecha")).not.toBeInTheDocument();
  });

  it("hides Restaurar again when the input is typed back to the saved value", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Resumen"), {
      target: { value: "resumen editado" },
    });
    expect(screen.getByTestId("restore-abstract")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Resumen"), {
      target: { value: "resumen extraído" },
    });
    expect(screen.queryByTestId("restore-abstract")).not.toBeInTheDocument();
  });

  it("Restaurar reverts título to its saved value", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Mi tesis" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Otro título" },
    });

    fireEvent.click(screen.getByTestId("restore-titulo"));

    await waitFor(() =>
      expect(screen.getByLabelText("Título")).toHaveValue("Mi tesis"),
    );
    expect(apiPatch).not.toHaveBeenCalled();
    expect(screen.queryByTestId("restore-titulo")).not.toBeInTheDocument();
  });

  it("Restaurar reverts the field to its seeded value without persisting", async () => {
    useDraftStateMock.mockReturnValue(
      draft({ staged_abstract: "resumen editado" }),
    );
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Resumen"), {
      target: { value: "otro texto" },
    });

    fireEvent.click(screen.getByTestId("restore-abstract"));

    await waitFor(() =>
      expect(screen.getByLabelText("Resumen")).toHaveValue("resumen editado"),
    );
    // Restaurar only resets the input; nothing is PATCHed.
    expect(apiPatch).not.toHaveBeenCalled();
    expect(screen.queryByTestId("restore-abstract")).not.toBeInTheDocument();
  });

  it("Restaurar reverts to the last saved value, not the original seed", async () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Resumen"), {
      target: { value: "resumen guardado" },
    });
    clickSave();
    await waitFor(() => expect(refreshDraft).toHaveBeenCalled());
    // Save re-baselines the form → Restaurar disappears.
    await waitFor(() =>
      expect(screen.queryByTestId("restore-abstract")).not.toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText("Resumen"), {
      target: { value: "otro texto" },
    });
    fireEvent.click(screen.getByTestId("restore-abstract"));
    await waitFor(() =>
      expect(screen.getByLabelText("Resumen")).toHaveValue("resumen guardado"),
    );
  });

  it("PATCHes title on save", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Viejo" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo título" },
    });
    clickSave();
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

  it("toasts when the save PATCH fails", async () => {
    apiPatch.mockResolvedValue({ error: { detail: "boom" } });
    useDraftStateMock.mockReturnValue(draft({ title: "Mi tesis" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo" },
    });
    clickSave();
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(refreshDraft).not.toHaveBeenCalled();
  });

  it("refetches draft state after a successful save so a new gate is observed", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Viejo" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo título" },
    });
    clickSave();
    await waitFor(() => expect(refreshDraft).toHaveBeenCalled());
  });

  it("hides Guardar and does not PATCH without changes", async () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(
      screen.queryByRole("button", { name: /guardar cambios/i }),
    ).not.toBeInTheDocument();
    await Promise.resolve();
    expect(apiPatch).not.toHaveBeenCalled();
  });

  it("PATCHes keywords as an array on save", async () => {
    useDraftStateMock.mockReturnValue(draft({ staged_keywords: ["a"] }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Palabras clave"), {
      target: { value: "redes, grafos" },
    });
    clickSave();
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const opts = apiPatch.mock.calls[0]![1];
    expect(opts.body).toMatchObject({ keywords: ["redes", "grafos"] });
  });

  it("PATCHes fecha staged by the DatePicker on save", async () => {
    useDraftStateMock.mockReturnValue(draft({ staged_fecha: "2024-03-01" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Fecha"), {
      target: { value: "2024-06-15" },
    });
    clickSave();
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    const opts = apiPatch.mock.calls[0]![1];
    expect(opts.body).toMatchObject({ fecha: "2024-06-15" });
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

  it("navigates back directly when there are no unsaved changes", () => {
    useDraftStateMock.mockReturnValue(draft({}));
    render(<EditarPage />);
    expect(screen.getByRole("link", { name: /mis trabajos/i })).toHaveAttribute(
      "href",
      "/mis-trabajos",
    );
  });

  it("warns before leaving via a link with unsaved changes", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Mi tesis" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo" },
    });
    fireEvent.click(screen.getByRole("link", { name: /mis trabajos/i }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: /^salir sin guardar$/i }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/mis-trabajos"));
  });

  it("warns on browser Back with unsaved changes", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Mi tesis" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo" },
    });
    fireEvent.popState(window);
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
    fireEvent.click(
      screen.getByRole("button", { name: /^salir sin guardar$/i }),
    );
    await waitFor(() => expect(back).toHaveBeenCalled());
    back.mockRestore();
  });

  it("reclaims the Back sentinel after saving so Back isn't a dead no-op", async () => {
    useDraftStateMock.mockReturnValue(draft({ title: "Mi tesis" }));
    render(<EditarPage />);
    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Nuevo" },
    });
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
    clickSave();
    // Save clears isDirty → the guard pops its sentinel so the next Back works.
    await waitFor(() => expect(back).toHaveBeenCalledTimes(1));
    // Guard is disarmed: a Back press no longer shows the leave dialog.
    fireEvent.popState(window);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    back.mockRestore();
  });
});

function clickSave() {
  fireEvent.click(screen.getByRole("button", { name: /guardar cambios/i }));
}

// Eliminar lives behind an AlertDialog: open it, then click the confirm action.
async function confirmDelete() {
  fireEvent.click(screen.getByRole("button", { name: /eliminar/i }));
  const buttons = await screen.findAllByRole("button", { name: /eliminar/i });
  fireEvent.click(buttons[buttons.length - 1]!);
}
