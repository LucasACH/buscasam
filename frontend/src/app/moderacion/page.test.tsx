import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const { useUserMock } = vi.hoisted(() => ({
  useUserMock: vi.fn(),
}));
vi.mock("@/lib/useUser", () => ({ useUser: () => useUserMock() }));

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const { useQueueMock } = vi.hoisted(() => ({ useQueueMock: vi.fn() }));
vi.mock("./useQueue", () => ({ useQueue: () => useQueueMock() }));

import ModeracionPage from "./page";

function docente() {
  useUserMock.mockReturnValue({
    user: { user_id: 1, role: "docente" },
    isInvitado: false,
    isLoading: false,
    isError: false,
  });
}

function returns(entries: unknown[], isLoading = false) {
  useQueueMock.mockReturnValue({ entries, isLoading });
}

const ENTRY = {
  doc_id: 7,
  report_id: 42,
  title: "Trabajo reportado",
  reasons: ["plagio", "spam"],
  first_reported_at: "2026-01-01T00:00:00Z",
  last_reported_at: "2026-01-05T00:00:00Z",
  report_count: 3,
};

describe("/moderacion queue page", () => {
  beforeEach(() => {
    replace.mockReset();
    useUserMock.mockReset();
    useQueueMock.mockReset();
    docente();
    returns([]);
  });
  afterEach(() => cleanup());

  it("lists each entry with title, reason(s) and reporter count", () => {
    returns([ENTRY]);

    render(<ModeracionPage />);

    expect(screen.getByText("Trabajo reportado")).toBeInTheDocument();
    expect(screen.getByText(/plagio, spam/)).toBeInTheDocument();
    expect(screen.getByText(/3 reportes/)).toBeInTheDocument();
  });

  it("links each row to its report-scoped inspect view", () => {
    returns([ENTRY]);

    render(<ModeracionPage />);

    expect(
      screen.getByRole("link", { name: /Trabajo reportado/ }),
    ).toHaveAttribute("href", "/moderacion/42");
  });

  it("redirects an invitado to login", () => {
    useUserMock.mockReturnValue({
      user: null,
      isInvitado: true,
      isLoading: false,
      isError: false,
    });

    render(<ModeracionPage />);

    expect(replace).toHaveBeenCalledWith("/login?next=/moderacion");
  });

  it("redirects a non-Docente to home", () => {
    useUserMock.mockReturnValue({
      user: { user_id: 2, role: "estudiante" },
      isInvitado: false,
      isLoading: false,
      isError: false,
    });

    render(<ModeracionPage />);

    expect(replace).toHaveBeenCalledWith("/");
  });

  it("shows empty-state copy when the queue is empty", async () => {
    returns([]);

    render(<ModeracionPage />);

    await waitFor(() =>
      expect(screen.getByText(/No hay reportes pendientes/)).toBeInTheDocument(),
    );
  });
});
