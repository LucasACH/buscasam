import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { useUserMock, apiPost, toastSuccess } = vi.hoisted(() => ({
  useUserMock: vi.fn(),
  apiPost: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("@/lib/useUser", () => ({ useUser: () => useUserMock() }));
vi.mock("@/api/client", () => ({ api: { POST: apiPost } }));
vi.mock("sonner", () => ({ toast: { success: toastSuccess } }));

import { ReportDialog } from "./ReportDialog";

function asInvitado() {
  useUserMock.mockReturnValue({ user: null, isInvitado: true, isLoading: false });
}

function asAuthenticated() {
  useUserMock.mockReturnValue({
    user: { user_id: 1, role: "estudiante" },
    isInvitado: false,
    isLoading: false,
  });
}

describe("ReportDialog", () => {
  beforeEach(() => {
    useUserMock.mockReset();
    apiPost.mockReset().mockResolvedValue({ response: { status: 204 } });
    toastSuccess.mockReset();
  });
  afterEach(() => cleanup());

  it("renders nothing for an invitado", () => {
    asInvitado();
    const { container } = render(<ReportDialog docId={7} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the Reportar affordance for an authenticated reader", () => {
    asAuthenticated();
    render(<ReportDialog docId={7} />);
    expect(
      screen.getByRole("button", { name: /Reportar/i }),
    ).toBeInTheDocument();
  });

  it("offers the four reasons once opened", async () => {
    asAuthenticated();
    render(<ReportDialog docId={7} />);
    await userEvent.click(screen.getByRole("button", { name: /Reportar/i }));
    expect(screen.getByRole("radio", { name: /Spam/i })).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Contenido inadecuado/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Plagio/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Error/i })).toBeInTheDocument();
  });

  it("posts the chosen reason and confirms on success", async () => {
    asAuthenticated();
    render(<ReportDialog docId={7} />);
    await userEvent.click(screen.getByRole("button", { name: /Reportar/i }));
    await userEvent.click(screen.getByRole("radio", { name: /Plagio/i }));
    await userEvent.click(screen.getByRole("button", { name: /Enviar/i }));

    expect(apiPost).toHaveBeenCalledWith("/api/moderation/reports", {
      body: { doc_id: 7, reason: "plagio" },
    });
    await vi.waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        "Recibimos tu reporte. Gracias.",
      ),
    );
  });

  it("shows an alert and no confirmation when the request fails", async () => {
    asAuthenticated();
    apiPost.mockResolvedValue({ error: { detail: "not_found" } });
    render(<ReportDialog docId={7} />);
    await userEvent.click(screen.getByRole("button", { name: /Reportar/i }));
    await userEvent.click(screen.getByRole("radio", { name: /Spam/i }));
    await userEvent.click(screen.getByRole("button", { name: /Enviar/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("confirms silently on the duplicate no-op (204) with no error", async () => {
    asAuthenticated();
    apiPost.mockResolvedValue({ response: { status: 204 } });
    render(<ReportDialog docId={7} />);
    await userEvent.click(screen.getByRole("button", { name: /Reportar/i }));
    await userEvent.click(screen.getByRole("radio", { name: /Spam/i }));
    await userEvent.click(screen.getByRole("button", { name: /Enviar/i }));

    await vi.waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        "Recibimos tu reporte. Gracias.",
      ),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
