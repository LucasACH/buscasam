import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AreasCascader } from "./AreasCascader";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  { area_path: "escuela_ciencia.carrera_informatica", display_name: "Ing. Informática" },
  { area_path: "escuela_ciencia.carrera_informatica.materia_bd", display_name: "Bases de Datos" },
  { area_path: "escuela_humanidades", display_name: "Escuela de Humanidades" },
];

function mockAreas(body = AREAS) {
  return vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("AreasCascader", () => {
  beforeEach(() => {
    vi.spyOn(global, "fetch").mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("fetches /api/areas and renders Escuela options", async () => {
    mockAreas();

    wrap(<AreasCascader onChange={() => {}} />);

    await waitFor(() => {
      const escuela = screen.getByRole("combobox", { name: /escuela/i });
      expect(escuela).toHaveTextContent(/Escuela de Ciencia y Tecnología/);
    });
    const escuela = screen.getByRole("combobox", { name: /escuela/i });
    expect(escuela).toHaveTextContent(/Escuela de Humanidades/);
  });

  it("reveals Carrera options scoped to the selected Escuela", async () => {
    mockAreas();
    const user = userEvent.setup();

    wrap(<AreasCascader onChange={() => {}} />);

    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /escuela/i }),
      ).toHaveTextContent(/Ciencia/),
    );

    expect(screen.queryByRole("combobox", { name: /carrera/i })).toBeNull();

    await user.selectOptions(
      screen.getByRole("combobox", { name: /escuela/i }),
      "escuela_ciencia",
    );

    const carrera = await screen.findByRole("combobox", { name: /carrera/i });
    expect(carrera).toHaveTextContent(/Ing\. Informática/);
  });

  it("reveals Materia options scoped to the selected Carrera", async () => {
    mockAreas();
    const user = userEvent.setup();

    wrap(<AreasCascader onChange={() => {}} />);

    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /escuela/i }),
      ).toHaveTextContent(/Ciencia/),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: /escuela/i }),
      "escuela_ciencia",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: /carrera/i }),
      "escuela_ciencia.carrera_informatica",
    );

    const materia = await screen.findByRole("combobox", { name: /materia/i });
    expect(materia).toHaveTextContent(/Bases de Datos/);
  });

  it("requireLeaf: emits onChange only once Materia is selected and shows error on partial", async () => {
    mockAreas();
    const user = userEvent.setup();
    const onChange = vi.fn();

    wrap(<AreasCascader requireLeaf onChange={onChange} />);

    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /escuela/i }),
      ).toHaveTextContent(/Ciencia/),
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: /escuela/i }),
      "escuela_ciencia",
    );

    // Partial selection: no leaf yet → inline error and no leaf-path emission.
    expect(await screen.findByText(/Elegí una Materia/)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalledWith(expect.stringContaining("materia_"));

    await user.selectOptions(
      await screen.findByRole("combobox", { name: /carrera/i }),
      "escuela_ciencia.carrera_informatica",
    );
    expect(screen.getByText(/Elegí una Materia/)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalledWith(expect.stringContaining("materia_"));

    await user.selectOptions(
      await screen.findByRole("combobox", { name: /materia/i }),
      "escuela_ciencia.carrera_informatica.materia_bd",
    );

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        "escuela_ciencia.carrera_informatica.materia_bd",
      );
    });
    expect(screen.queryByText(/Elegí una Materia/)).toBeNull();
  });

  it("requireLeaf=false: emits the deepest selected path and never shows the leaf error", async () => {
    mockAreas();
    const user = userEvent.setup();
    const onChange = vi.fn();

    wrap(<AreasCascader onChange={onChange} />);

    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /escuela/i }),
      ).toHaveTextContent(/Ciencia/),
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: /escuela/i }),
      "escuela_ciencia",
    );

    await waitFor(() => expect(onChange).toHaveBeenCalledWith("escuela_ciencia"));
    expect(screen.queryByText(/Elegí una Materia/)).toBeNull();
  });
});
