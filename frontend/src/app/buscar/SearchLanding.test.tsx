import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const { useUser } = vi.hoisted(() => ({ useUser: vi.fn() }));
const { useMostRead } = vi.hoisted(() => ({ useMostRead: vi.fn() }));
vi.mock("@/lib/useUser", () => ({ useUser }));
vi.mock("./useMostRead", () => ({ useMostRead }));

import { SearchLanding } from "./SearchLanding";

function setUser(user: { name: string } | null) {
  useUser.mockReturnValue({
    user,
    isInvitado: user === null,
    isLoading: false,
    isError: false,
  });
}

beforeEach(() => {
  setUser(null);
  useMostRead.mockReturnValue({
    results: [],
    publicTotal: 0,
    isLoading: false,
    isError: false,
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SearchLanding greeting", () => {
  it("shows the first name for an authenticated user", () => {
    setUser({ name: "Ada Lovelace" });
    render(<SearchLanding onSearch={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
      "Ada",
    );
  });

  it("shows no name for an invitado", () => {
    setUser(null);
    render(<SearchLanding onSearch={vi.fn()} />);
    const title = screen.getByRole("heading", { level: 1 }).textContent ?? "";
    expect(title).not.toContain(",");
  });
});

describe("SearchLanding composer", () => {
  it("submits the trimmed query via onSearch", () => {
    const onSearch = vi.fn();
    render(<SearchLanding onSearch={onSearch} />);
    const input = screen.getByLabelText("Buscar trabajos");
    fireEvent.change(input, { target: { value: "  redes neuronales  " } });
    fireEvent.submit(input.closest("form")!);
    expect(onSearch).toHaveBeenCalledWith("redes neuronales");
  });

  it("submits on Enter without Shift", () => {
    const onSearch = vi.fn();
    render(<SearchLanding onSearch={onSearch} />);
    const input = screen.getByLabelText("Buscar trabajos");
    fireEvent.change(input, { target: { value: "microplásticos" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSearch).toHaveBeenCalledWith("microplásticos");
  });

  it("navigates via a suggested-query chip", () => {
    const onSearch = vi.fn();
    render(<SearchLanding onSearch={onSearch} />);
    fireEvent.click(
      screen.getByRole("button", { name: "modelos de lenguaje" }),
    );
    expect(onSearch).toHaveBeenCalledWith("modelos de lenguaje");
  });
});

describe("SearchLanding footnote", () => {
  it("shows the formatted public_total", () => {
    useMostRead.mockReturnValue({
      results: [],
      publicTotal: 12480,
      isLoading: false,
      isError: false,
    });
    render(<SearchLanding onSearch={vi.fn()} />);
    expect(screen.getByText(/12\.480/)).toBeInTheDocument();
  });
});
