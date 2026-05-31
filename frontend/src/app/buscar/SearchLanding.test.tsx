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
    render(<SearchLanding onApply={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
      "Ada",
    );
  });

  it("shows no name for an invitado", () => {
    setUser(null);
    render(<SearchLanding onApply={vi.fn()} />);
    const title = screen.getByRole("heading", { level: 1 }).textContent ?? "";
    expect(title).not.toContain(",");
  });
});

describe("SearchLanding composer", () => {
  it("submits the trimmed query", () => {
    const onApply = vi.fn();
    render(<SearchLanding onApply={onApply} />);
    const input = screen.getByLabelText("Buscar trabajos");
    fireEvent.change(input, { target: { value: "  redes neuronales  " } });
    fireEvent.submit(input.closest("form")!);
    expect(onApply).toHaveBeenCalledWith({ q: "redes neuronales" });
  });

  it("submits on Enter without Shift", () => {
    const onApply = vi.fn();
    render(<SearchLanding onApply={onApply} />);
    const input = screen.getByLabelText("Buscar trabajos");
    fireEvent.change(input, { target: { value: "microplásticos" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onApply).toHaveBeenCalledWith({ q: "microplásticos" });
  });
});

describe("SearchLanding quick filters", () => {
  it("applies a tipo filter via a type chip", () => {
    const onApply = vi.fn();
    render(<SearchLanding onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "Tesis" }));
    expect(onApply).toHaveBeenCalledWith({ tipos: ["tesis"] });
  });

  it("switches to recientes via the chip", () => {
    const onApply = vi.fn();
    render(<SearchLanding onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver más recientes" }));
    expect(onApply).toHaveBeenCalledWith({ orden: "recientes" });
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
    render(<SearchLanding onApply={vi.fn()} />);
    expect(screen.getByText(/12\.480/)).toBeInTheDocument();
  });
});
