import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const addAttachment = vi.fn();
const removeAttachment = vi.fn();

const { toastError } = vi.hoisted(() => ({ toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { AttachmentsPanel } from "./AttachmentsPanel";

type Attachment = {
  id: number;
  original_filename: string;
  size_bytes: number;
  mime: string;
};

function att(id: number, name: string): Attachment {
  return { id, original_filename: name, size_bytes: 2048, mime: "text/csv" };
}

function wrap(attachments: Attachment[], canManage = true) {
  return render(
    <AttachmentsPanel
      attachments={attachments}
      actions={{ add: addAttachment, remove: removeAttachment }}
      canManage={canManage}
    />,
  );
}

describe("AttachmentsPanel", () => {
  beforeEach(() => {
    addAttachment.mockReset();
    addAttachment.mockResolvedValue(undefined);
    removeAttachment.mockReset();
    removeAttachment.mockResolvedValue(undefined);
    toastError.mockReset();
  });
  afterEach(() => cleanup());

  it("renders existing attachment rows with a Quitar button", () => {
    wrap([att(1, "data.csv")]);

    expect(screen.getByText(/data\.csv/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Quitar data\.csv/i }),
    ).toBeInTheDocument();
  });

  it("delegates removal to draft management", async () => {
    const user = userEvent.setup();
    const attachment = att(1, "data.csv");
    wrap([attachment]);

    await user.click(screen.getByRole("button", { name: /Quitar data\.csv/i }));

    expect(removeAttachment).toHaveBeenCalledWith(attachment);
  });

  it("disables the add affordance with the 5-cap copy at 5 attachments", () => {
    wrap([1, 2, 3, 4, 5].map((i) => att(i, `f${i}.csv`)));

    expect(screen.getByLabelText(/agregar adjunto/i)).toBeDisabled();
    expect(
      screen.getByText("Llegaste al máximo de 5 adjuntos"),
    ).toBeInTheDocument();
  });

  it("delegates selected files to draft management", async () => {
    const user = userEvent.setup();
    wrap([]);

    const file = new File(["a,b\n"], "new.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(/agregar adjunto/i), file);

    expect(addAttachment).toHaveBeenCalledWith(file);
  });

  it("surfaces the 20 MB message on a rejected large attachment", async () => {
    const user = userEvent.setup();
    addAttachment.mockResolvedValue("too_large");
    wrap([]);

    const file = new File(["x"], "big.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText(/agregar adjunto/i), file);

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        "Este adjunto pasa los 20 MB. Probá uno más chico.",
      ),
    );
  });

  it("hides add/remove affordances when canManage is false", () => {
    wrap([att(1, "data.csv")], false);

    expect(screen.getByText(/data\.csv/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Quitar/i })).toBeNull();
    expect(screen.queryByLabelText(/agregar adjunto/i)).toBeNull();
  });
});
