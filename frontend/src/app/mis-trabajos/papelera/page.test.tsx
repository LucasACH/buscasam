import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { useUserMock } = vi.hoisted(() => ({
  useUserMock: vi.fn(() => ({
    user: { user_id: 1, role: "estudiante" } as { user_id: number; role: string } | null,
    isInvitado: false,
    isLoading: false,
    isError: false,
  })),
}));
vi.mock("@/lib/useUser", () => ({ useUser: () => useUserMock() }));

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { useDeletedDocumentsMock, restore } = vi.hoisted(() => ({
  useDeletedDocumentsMock: vi.fn(),
  restore: vi.fn(),
}));
vi.mock("./useDeletedDocuments", () => ({
  useDeletedDocuments: () => useDeletedDocumentsMock(),
}));

import PapeleraPage from "./page";

function returns(documents: unknown[], isLoading = false) {
  useDeletedDocumentsMock.mockReturnValue({ documents, isLoading, restore });
}

describe("/mis-trabajos/papelera page", () => {
  beforeEach(() => {
    replace.mockReset();
    restore.mockReset();
    restore.mockResolvedValue(undefined);
    useUserMock.mockReturnValue({
      user: { user_id: 1, role: "estudiante" },
      isInvitado: false,
      isLoading: false,
      isError: false,
    });
    useDeletedDocumentsMock.mockReset();
  });
  afterEach(() => cleanup());

  it("lists each deleted doc with a days-remaining label", () => {
    returns([
      { id: 5, title: "Tesis borrada", publicationStatus: "published", daysRemaining: 2 },
    ]);

    render(<PapeleraPage />);

    expect(screen.getByText("Tesis borrada")).toBeInTheDocument();
    expect(screen.getByText(/Se elimina en 2 días/)).toBeInTheDocument();
  });

  it("Restaurar calls restore with the doc id", async () => {
    returns([
      { id: 5, title: "Tesis borrada", publicationStatus: "published", daysRemaining: 2 },
    ]);

    render(<PapeleraPage />);
    await userEvent.click(screen.getByRole("button", { name: "Restaurar" }));

    expect(restore).toHaveBeenCalledWith(5);
  });

  it("redirects an invitado to login", () => {
    useUserMock.mockReturnValue({
      user: null,
      isInvitado: true,
      isLoading: false,
      isError: false,
    });
    returns([]);

    render(<PapeleraPage />);

    expect(replace).toHaveBeenCalledWith("/login?next=/mis-trabajos/papelera");
  });

  it("shows empty-state copy when the papelera is empty", async () => {
    returns([]);

    render(<PapeleraPage />);

    await waitFor(() =>
      expect(screen.getByText(/La papelera está vacía/)).toBeInTheDocument(),
    );
  });
});
