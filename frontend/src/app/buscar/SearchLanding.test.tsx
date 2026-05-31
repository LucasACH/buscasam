import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const { useUser } = vi.hoisted(() => ({ useUser: vi.fn() }));
const { useMostRead } = vi.hoisted(() => ({ useMostRead: vi.fn() }));
const { useAreaLabel } = vi.hoisted(() => ({ useAreaLabel: vi.fn() }));
vi.mock("@/lib/useUser", () => ({ useUser }));
vi.mock("./useMostRead", () => ({ useMostRead }));
vi.mock("@/lib/useAreas", () => ({
  useAreaLabel,
  useAreas: vi.fn(() => ({ isLoading: false })),
}));

const POPULAR = [
  {
    doc_id: 7,
    titulo: "Redes neuronales profundas",
    area_path: "ecyt.lic_datos",
    tipo: "tesis",
    fecha: "2023-05-01",
    reads: 42,
  },
  {
    doc_id: 9,
    titulo: "Microplásticos en el Río Reconquista",
    area_path: "ecyt.lic_ambiental",
    tipo: "paper",
    fecha: "2021-11-02",
    reads: 8,
  },
];

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
  useAreaLabel.mockImplementation((path: string | null) =>
    path ? "Escuela de Ciencia y Tecnología" : null,
  );
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

describe("SearchLanding más leídos", () => {
  function withResults() {
    useMostRead.mockReturnValue({
      results: POPULAR,
      publicTotal: 100,
      isLoading: false,
      isError: false,
    });
  }

  it("renders ranked rows with label, tipo, year and read count", () => {
    withResults();
    render(<SearchLanding onApply={vi.fn()} />);
    const row = screen
      .getByText("Redes neuronales profundas")
      .closest("a")!;
    expect(row).toHaveTextContent("1");
    expect(row).toHaveTextContent("Escuela de Ciencia y Tecnología");
    expect(row).toHaveTextContent("Tesis");
    expect(row).toHaveTextContent("2023");
    expect(row).toHaveTextContent("42 lecturas");
  });

  it("links each row to the document detail page", () => {
    withResults();
    render(<SearchLanding onApply={vi.fn()} />);
    expect(
      screen.getByRole("link", { name: /Redes neuronales profundas/ }),
    ).toHaveAttribute("href", "/docs/7");
  });

  it("omits the section when the ranking is empty", () => {
    render(<SearchLanding onApply={vi.fn()} />);
    expect(screen.queryByText(/Más leídos/i)).not.toBeInTheDocument();
  });

  it("shows the heading without rows while fetching", () => {
    useMostRead.mockReturnValue({
      results: [],
      publicTotal: 0,
      isLoading: true,
      isError: false,
    });
    render(<SearchLanding onApply={vi.fn()} />);
    expect(screen.getByText(/Más leídos/i)).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
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
