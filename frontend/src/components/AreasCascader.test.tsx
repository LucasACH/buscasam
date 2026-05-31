import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

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

describe("AreasCascader", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiGet.mockResolvedValue({ data: AREAS });
  });
  afterEach(() => {
    cleanup();
  });

  it("fetches /api/areas and lists the escuelas", async () => {
    wrap(<AreasCascader onChange={() => {}} />);

    expect(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Elegí una Escuela")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Escuela de Humanidades/ }),
    ).toBeInTheDocument();
  });

  it("drills Escuela → Carrera → Materia and emits the leaf path", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<AreasCascader onChange={onChange} />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Ing\. Informática/ }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Bases de Datos/ }),
    );

    expect(onChange).toHaveBeenCalledWith(
      "escuela_ciencia.carrera_informatica.materia_bd",
    );
  });

  it("does not emit until a leaf is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<AreasCascader onChange={onChange} />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Ing\. Informática/ }),
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  it("selects an escuela that is itself a leaf", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<AreasCascader onChange={onChange} />);

    await user.click(
      await screen.findByRole("button", { name: /Escuela de Humanidades/ }),
    );
    expect(onChange).toHaveBeenCalledWith("escuela_humanidades");
  });

  it("back button returns to the parent level", async () => {
    const user = userEvent.setup();
    wrap(<AreasCascader onChange={() => {}} />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    expect(await screen.findByRole("button", { name: /Ing\. Informática/ }))
      .toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Volver/ }));
    expect(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    ).toBeInTheDocument();
  });

  it("opens at the parent of the selected value and clears via Quitar área", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(
      <AreasCascader
        value="escuela_ciencia.carrera_informatica.materia_bd"
        onChange={onChange}
      />,
    );

    // Opens drilled into the carrera, showing the selected materia.
    expect(await screen.findByRole("button", { name: /Bases de Datos/ }))
      .toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Quitar área/ }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
