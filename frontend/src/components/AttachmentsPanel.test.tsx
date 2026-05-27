import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiDelete, apiGet } = vi.hoisted(() => ({ apiDelete: vi.fn(), apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet, DELETE: apiDelete } }));

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { AttachmentsPanel } from "./AttachmentsPanel";
import { draftQueryKey, type DraftStateDTO } from "@/app/mis-trabajos/useDraftState";

const DOC_ID = 42;

type Attachment = DraftStateDTO["attachments"][number];

function att(id: number, name: string): Attachment {
  return { id, original_filename: name, size_bytes: 2048, mime: "text/csv" };
}

function draft(attachments: Attachment[]): DraftStateDTO {
  return {
    title: "Doc",
    index_status: "indexed",
    staged_abstract: null,
    staged_keywords: [],
    staged_fecha: null,
    index_error: null,
    publish_gate_reason: null,
    is_owner: true,
    attachments,
  };
}

function wrap(attachments: Attachment[], canManage = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(draftQueryKey(DOC_ID), draft(attachments));
  return render(
    <QueryClientProvider client={client}>
      <AttachmentsPanel docId={DOC_ID} canManage={canManage} />
    </QueryClientProvider>,
  );
}

describe("AttachmentsPanel", () => {
  beforeEach(() => {
    apiDelete.mockReset();
    apiDelete.mockResolvedValue({ error: undefined });
    apiGet.mockResolvedValue({ data: draft([]) });
    toastError.mockReset();
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders existing attachment rows with a Quitar button", () => {
    wrap([att(1, "data.csv")]);

    expect(screen.getByText(/data\.csv/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Quitar data\.csv/i })).toBeInTheDocument();
  });

  it("optimistically removes a row and calls DELETE", async () => {
    const user = userEvent.setup();
    wrap([att(1, "data.csv")]);

    await user.click(screen.getByRole("button", { name: /Quitar data\.csv/i }));

    expect(screen.queryByText(/data\.csv/)).toBeNull();
    await waitFor(() => expect(apiDelete).toHaveBeenCalled());
    const call = apiDelete.mock.calls[0]!;
    expect(call[0]).toBe("/api/documents/{doc_id}/attachments/{att_id}");
    expect(call[1]).toMatchObject({ params: { path: { doc_id: DOC_ID, att_id: 1 } } });
  });

  it("disables the add affordance with the 5-cap copy at 5 attachments", () => {
    wrap([1, 2, 3, 4, 5].map((i) => att(i, `f${i}.csv`)));

    expect(screen.getByLabelText(/agregar adjunto/i)).toBeDisabled();
    expect(screen.getByText("Llegaste al máximo de 5 adjuntos")).toBeInTheDocument();
  });

  it("uploads a file and appends the returned row", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 201,
      json: async () => ({ id: 9, original_filename: "new.csv", size_bytes: 10, mime: "text/csv" }),
    });
    wrap([]);

    const file = new File(["a,b\n"], "new.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/agregar adjunto/i), file);

    expect(await screen.findByText(/new\.csv/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      `/api/documents/${DOC_ID}/attachments`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("surfaces the 20 MB message on a 413", async () => {
    const user = userEvent.setup();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 413,
      json: async () => ({ detail: "El adjunto supera los 20 MB" }),
    });
    wrap([]);

    const file = new File(["x"], "big.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText(/agregar adjunto/i), file);

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Este adjunto pasa los 20 MB. Probá uno más chico."),
    );
  });

  it("hides add/remove affordances when canManage is false", () => {
    wrap([att(1, "data.csv")], false);

    expect(screen.getByText(/data\.csv/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Quitar/i })).toBeNull();
    expect(screen.queryByLabelText(/agregar adjunto/i)).toBeNull();
  });
});
