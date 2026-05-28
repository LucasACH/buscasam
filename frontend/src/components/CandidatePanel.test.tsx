import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { POST: apiPost } }));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { CandidatePanel } from "./CandidatePanel";

const DOC_ID = 7;
const replace = vi.fn();
const discard = vi.fn();
const refresh = vi.fn();

type Candidate = {
  status: "processing" | "ready" | "failed";
  statusLabel: string;
  stagedAbstract: string | null;
  stagedKeywords: string[];
  stagedFecha: string | null;
  canPublish: boolean;
  canDiscard: boolean;
  error: string | null;
};

function candidate(over: Partial<Candidate> = {}): Candidate {
  return {
    status: "processing",
    statusLabel: "Procesando…",
    stagedAbstract: null,
    stagedKeywords: [],
    stagedFecha: null,
    canPublish: false,
    canDiscard: true,
    error: null,
    ...over,
  };
}

function wrap(cand: Candidate | null, canPublish = true) {
  return render(
    <CandidatePanel
      docId={DOC_ID}
      canPublish={canPublish}
      candidate={cand}
      replace={replace}
      discard={discard}
      refresh={refresh}
    />,
  );
}

describe("CandidatePanel", () => {
  beforeEach(() => {
    replace.mockReset();
    replace.mockResolvedValue(undefined);
    discard.mockReset();
    discard.mockResolvedValue(undefined);
    refresh.mockReset();
    refresh.mockResolvedValue(undefined);
    apiPost.mockReset();
    apiPost.mockResolvedValue({ error: undefined, response: { status: 204 } });
    toastError.mockReset();
  });
  afterEach(() => cleanup());

  it("offers Reemplazar + the previous-version helper when there is no candidate", () => {
    wrap(null);

    expect(
      screen.getByLabelText("Reemplazar archivo principal"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "La versión previa permanece pública hasta que publiques la nueva.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the processing pill and a Reemplazar affordance while processing", () => {
    wrap(candidate({ status: "processing", statusLabel: "Procesando…" }));

    expect(screen.getByText("Procesando…")).toBeInTheDocument();
    expect(screen.getByLabelText("Reemplazar")).toBeInTheDocument();
  });

  it("shows the ready pill, staged metadata and an enabled Publicar for an owner", () => {
    wrap(
      candidate({
        status: "ready",
        statusLabel: "Listo para publicar",
        canPublish: true,
        stagedAbstract: "Nuevo resumen",
      }),
      true,
    );

    expect(screen.getByText("Listo para publicar")).toBeInTheDocument();
    expect(screen.getByText("Nuevo resumen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publicar" })).toBeEnabled();
  });

  it("disables Publicar when the viewer is not the owner", () => {
    wrap(
      candidate({ status: "ready", statusLabel: "Listo para publicar", canPublish: true }),
      false,
    );

    expect(screen.getByRole("button", { name: "Publicar" })).toBeDisabled();
  });

  it("renders the failure pill with the inline error", () => {
    wrap(
      candidate({
        status: "failed",
        statusLabel: "Falló el procesamiento",
        error: "No se pudo extraer el texto",
      }),
    );

    expect(screen.getByText("Falló el procesamiento")).toBeInTheDocument();
    expect(screen.getByText("No se pudo extraer el texto")).toBeInTheDocument();
  });

  it("delegates a picked file to replace()", async () => {
    const user = userEvent.setup();
    wrap(null);

    const file = new File(["%PDF-1.4"], "nueva.pdf", {
      type: "application/pdf",
    });
    await user.upload(
      screen.getByLabelText("Reemplazar archivo principal"),
      file,
    );

    expect(replace).toHaveBeenCalledWith(file);
  });

  it("surfaces the oversize message inline on a rejected replace", async () => {
    const user = userEvent.setup();
    replace.mockResolvedValue("too_large");
    wrap(null);

    const file = new File(["x"], "big.pdf", { type: "application/pdf" });
    await user.upload(
      screen.getByLabelText("Reemplazar archivo principal"),
      file,
    );

    await waitFor(() =>
      expect(
        screen.getByText("Este archivo supera los 50 MB"),
      ).toBeInTheDocument(),
    );
  });

  it("publishes through the existing publish route and refreshes", async () => {
    const user = userEvent.setup();
    wrap(
      candidate({ status: "ready", statusLabel: "Listo para publicar", canPublish: true }),
      true,
    );

    await user.click(screen.getByRole("button", { name: "Publicar" }));

    expect(apiPost).toHaveBeenCalledWith("/api/documents/{doc_id}/publish", {
      params: { path: { doc_id: DOC_ID } },
    });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it.each(["processing", "ready", "failed"] as const)(
    "offers Descartar in the %s state when canDiscard",
    (status) => {
      wrap(candidate({ status, canDiscard: true, canPublish: status === "ready" }));

      expect(
        screen.getByRole("button", { name: "Descartar" }),
      ).toBeInTheDocument();
    },
  );

  it("hides Descartar when canDiscard is false", () => {
    wrap(candidate({ status: "processing", canDiscard: false }));

    expect(
      screen.queryByRole("button", { name: "Descartar" }),
    ).not.toBeInTheDocument();
  });

  it("delegates a Descartar click to discard()", async () => {
    const user = userEvent.setup();
    wrap(candidate({ status: "failed", canDiscard: true }));

    await user.click(screen.getByRole("button", { name: "Descartar" }));

    expect(discard).toHaveBeenCalledOnce();
  });

  it("toasts when discard() fails", async () => {
    const user = userEvent.setup();
    discard.mockResolvedValue("discard_failed");
    wrap(candidate({ status: "failed", canDiscard: true }));

    await user.click(screen.getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("No se pudo descartar"));
  });
});
