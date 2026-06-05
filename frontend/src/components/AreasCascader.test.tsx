import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { GET: apiGet } }));

import { useState } from "react";

import { AreasCascader } from "./AreasCascader";
import type { AreasCascaderProps } from "./AreasCascader";

// Holds the selected value like a real form would, so value-dependent UI
// (header check, "Elegir … (opcional)" divider) renders after selecting.
function Controlled(props: AreasCascaderProps) {
  const [value, setValue] = useState<string | null>(null);
  return (
    <AreasCascader
      {...props}
      value={value}
      onChange={(v) => {
        setValue(v);
        props.onChange(v);
      }}
    />
  );
}

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const AREAS = [
  {
    area_path: "escuela_ciencia",
    display_name: "Escuela de Ciencia y Tecnología",
  },
  {
    area_path: "escuela_ciencia.carrera_informatica",
    display_name: "Ing. Informática",
  },
  {
    area_path: "escuela_ciencia.carrera_informatica.materia_bd",
    display_name: "Bases de Datos",
  },
  {
    area_path: "escuela_ciencia.carrera_matematica",
    display_name: "Matemática",
  },
  {
    area_path: "escuela_ciencia.carrera_matematica.materia_algebra",
    display_name: "Álgebra",
  },
  // No Materia → pruned from the cascader.
  {
    area_path: "escuela_ciencia.carrera_vacia",
    display_name: "Carrera Vacía",
  },
  { area_path: "escuela_humanidades", display_name: "Escuela de Humanidades" },
  {
    area_path: "escuela_humanidades.carrera_historia",
    display_name: "Historia",
  },
  {
    area_path: "escuela_humanidades.carrera_historia.materia_antigua",
    display_name: "Historia Antigua",
  },
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

  it("prunes branches that lead to no Materia", async () => {
    const user = userEvent.setup();
    wrap(<AreasCascader onChange={() => {}} />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    // Carreras with a Materia survive; the materia-less one is gone.
    expect(
      await screen.findByRole("button", { name: /Ing\. Informática/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Carrera Vacía/ }),
    ).not.toBeInTheDocument();
  });

  it("back button returns to the parent level", async () => {
    const user = userEvent.setup();
    wrap(<AreasCascader onChange={() => {}} />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    expect(
      await screen.findByRole("button", { name: /Ing\. Informática/ }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Volver/ }));
    expect(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    ).toBeInTheDocument();
  });

  it("filters the current level by the search query, ignoring accents", async () => {
    const user = userEvent.setup();
    wrap(<AreasCascader onChange={() => {}} />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    // Both carreras are listed before searching.
    await screen.findByRole("button", { name: /Ing\. Informática/ });
    expect(
      screen.getByRole("button", { name: /Matemática/ }),
    ).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Buscar área…"), "matematica");

    expect(
      screen.getByRole("button", { name: /Matemática/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Ing\. Informática/ }),
    ).not.toBeInTheDocument();
  });

  it("scopes search to the current level, not the whole tree", async () => {
    const user = userEvent.setup();
    wrap(<AreasCascader onChange={() => {}} />);

    // "Informática" lives one level down; from the escuela list it must not match.
    await user.type(
      await screen.findByPlaceholderText("Buscar escuela…"),
      "informatica",
    );

    expect(
      screen.queryByRole("button", { name: /Ing\. Informática/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Sin resultados")).toBeInTheDocument();
  });

  it("clears the search query when drilling into a level", async () => {
    const user = userEvent.setup();
    wrap(<AreasCascader onChange={() => {}} />);

    await user.type(
      await screen.findByPlaceholderText("Buscar escuela…"),
      "ciencia",
    );
    await user.click(
      screen.getByRole("button", { name: /Escuela de Ciencia y Tecnología/ }),
    );

    // Inside the escuela the placeholder names the next level down.
    expect(screen.getByPlaceholderText("Buscar área…")).toHaveValue("");
    // Full child list is shown again, not filtered by "ciencia".
    expect(
      screen.getByRole("button", { name: /Matemática/ }),
    ).toBeInTheDocument();
  });

  it('minLevel="carrera" keeps materia-less carreras and selects them on click', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<AreasCascader onChange={onChange} minLevel="carrera" />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    // No longer pruned: a carrera is itself selectable, and as a leaf it
    // selects on click.
    await user.click(
      await screen.findByRole("button", { name: /Carrera Vacía/ }),
    );

    expect(onChange).toHaveBeenCalledWith("escuela_ciencia.carrera_vacia");
  });

  it('minLevel="carrera" selects a carrera on click and drills in to optionally refine', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<Controlled onChange={onChange} minLevel="carrera" />);

    // Escuelas are above the minimum: clicking only drills, no selection.
    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    expect(onChange).not.toHaveBeenCalled();

    // Clicking the carrera selects it AND drills in: the materias are offered
    // as optional refinement, not as a required next step.
    await user.click(
      await screen.findByRole("button", { name: /Ing\. Informática/ }),
    );
    expect(onChange).toHaveBeenCalledWith(
      "escuela_ciencia.carrera_informatica",
    );
    expect(
      await screen.findByText(/Elegir una? .+ \(opcional\)/),
    ).toBeInTheDocument();

    // Refining replaces the selection with the materia.
    await user.click(
      await screen.findByRole("button", { name: /Bases de Datos/ }),
    );
    expect(onChange).toHaveBeenLastCalledWith(
      "escuela_ciencia.carrera_informatica.materia_bd",
    );
  });

  it('minLevel="escuela" selects the escuela itself on click', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    wrap(<Controlled onChange={onChange} minLevel="escuela" />);

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );

    expect(onChange).toHaveBeenCalledWith("escuela_ciencia");
    expect(
      await screen.findByText(/Elegir una? .+ \(opcional\)/),
    ).toBeInTheDocument();
  });

  it("fires onComplete when a leaf (materia) is picked", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    wrap(<Controlled onChange={() => {}} onComplete={onComplete} />);

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

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("does not fire onComplete when a non-leaf node is picked", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    wrap(
      <Controlled
        onChange={() => {}}
        onComplete={onComplete}
        minLevel="carrera"
      />,
    );

    await user.click(
      await screen.findByRole("button", {
        name: /Escuela de Ciencia y Tecnología/,
      }),
    );
    // A carrera (selectable at minLevel) with materias under it is non-leaf.
    await user.click(
      await screen.findByRole("button", { name: /Ing\. Informática/ }),
    );

    expect(onComplete).not.toHaveBeenCalled();
  });

  it("opens at the parent of the selected value", async () => {
    wrap(
      <AreasCascader
        value="escuela_ciencia.carrera_informatica.materia_bd"
        onChange={() => {}}
      />,
    );

    // Opens drilled into the carrera, showing the selected materia.
    expect(
      await screen.findByRole("button", { name: /Bases de Datos/ }),
    ).toBeInTheDocument();
  });
});
