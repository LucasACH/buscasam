import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { CandidatePanel } from "./CandidatePanel";

const replace = vi.fn();
const discard = vi.fn();
const publish = vi.fn();
const retryIndexing = vi.fn();

type Candidate = {
  status: "processing" | "ready" | "failed";
  statusLabel: string;
  stage: string | null;
  stagedAbstract: string | null;
  stagedKeywords: string[];
  stagedFecha: string | null;
  canPublish: boolean;
  canDiscard: boolean;
  failureMessage: string | null;
  failureKind: "file" | "system" | null;
  retryAvailableAt: string | null;
  retryRemaining: number;
};

function candidate(over: Partial<Candidate> = {}): Candidate {
  return {
    status: "processing",
    statusLabel: "Procesando…",
    stage: null,
    stagedAbstract: null,
    stagedKeywords: [],
    stagedFecha: null,
    canPublish: false,
    canDiscard: true,
    failureMessage: null,
    failureKind: null,
    retryAvailableAt: null,
    retryRemaining: 3,
    ...over,
  };
}

function wrap(cand: Candidate | null) {
  return render(
    <CandidatePanel
      candidate={cand}
      actions={{ publish, replace, discard, retryIndexing }}
    />,
  );
}

describe("CandidatePanel", () => {
  beforeEach(() => {
    replace.mockReset();
    replace.mockResolvedValue(undefined);
    discard.mockReset();
    discard.mockResolvedValue(undefined);
    publish.mockReset();
    publish.mockResolvedValue("published");
    retryIndexing.mockReset();
    retryIndexing.mockResolvedValue(undefined);
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

  it("shows the progress checkpoint and a Reemplazar affordance while processing", () => {
    wrap(candidate({ status: "processing", stage: "reading" }));

    expect(screen.getByText("Leyendo el documento")).toBeInTheDocument();
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
    );

    expect(screen.getByText("Listo para publicar")).toBeInTheDocument();
    expect(screen.getByText("Nuevo resumen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publicar" })).toBeEnabled();
  });

  it("disables Publicar when the draft action interface marks it blocked", () => {
    wrap(
      candidate({
        status: "ready",
        statusLabel: "Listo para publicar",
        canPublish: false,
      }),
    );

    expect(screen.getByRole("button", { name: "Publicar" })).toBeDisabled();
  });

  it("renders the failure pill with the mapped failure message", () => {
    wrap(
      candidate({
        status: "failed",
        statusLabel: "Falló el procesamiento",
        failureMessage: "Falló el procesamiento — revisá tu archivo",
        failureKind: "file",
      }),
    );

    expect(screen.getByText("Falló el procesamiento")).toBeInTheDocument();
    expect(screen.getByTestId("candidate-error")).toHaveTextContent(
      "Falló el procesamiento — revisá tu archivo",
    );
  });

  it("offers Reintentar only for a system failure", () => {
    wrap(
      candidate({
        status: "failed",
        statusLabel: "Falló el procesamiento",
        failureKind: "system",
      }),
    );

    expect(screen.getByTestId("retry-indexing")).toBeEnabled();
  });

  it("hides Reintentar once no retries remain", () => {
    wrap(
      candidate({
        status: "failed",
        statusLabel: "Falló el procesamiento",
        failureKind: "system",
        retryRemaining: 0,
      }),
    );

    expect(screen.queryByTestId("retry-indexing")).not.toBeInTheDocument();
  });

  it("hides Reintentar for a file failure", () => {
    wrap(
      candidate({
        status: "failed",
        statusLabel: "Falló el procesamiento",
        failureKind: "file",
      }),
    );

    expect(screen.queryByTestId("retry-indexing")).not.toBeInTheDocument();
  });

  it("delegates Reintentar to retryIndexing()", async () => {
    const user = userEvent.setup();
    wrap(
      candidate({
        status: "failed",
        statusLabel: "Falló el procesamiento",
        failureKind: "system",
      }),
    );

    await user.click(screen.getByTestId("retry-indexing"));

    await waitFor(() => expect(retryIndexing).toHaveBeenCalledTimes(1));
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

  it("delegates Publicar to the draft action interface", async () => {
    const user = userEvent.setup();
    wrap(
      candidate({
        status: "ready",
        statusLabel: "Listo para publicar",
        canPublish: true,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Publicar" }));

    expect(publish).toHaveBeenCalledOnce();
  });

  it("toasts when publish fails", async () => {
    const user = userEvent.setup();
    publish.mockResolvedValue("publish_failed");
    wrap(
      candidate({
        status: "ready",
        statusLabel: "Listo para publicar",
        canPublish: true,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Publicar" }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("No se pudo publicar"),
    );
  });

  it.each(["processing", "ready", "failed"] as const)(
    "offers Descartar in the %s state when canDiscard",
    (status) => {
      wrap(
        candidate({ status, canDiscard: true, canPublish: status === "ready" }),
      );

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

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("No se pudo descartar"),
    );
  });
});
