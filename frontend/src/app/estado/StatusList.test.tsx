import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { OverallBanner, StatusList, type ServiceHealth } from "./StatusList";

afterEach(cleanup);

const services: ServiceHealth[] = [
  {
    key: "database",
    name: "Base de datos",
    status: "ok",
    detail: "latencia 3 ms",
  },
  {
    key: "workers",
    name: "Procesamiento",
    status: "degraded",
    detail: "0 activo(s) · 0 en cola",
  },
  {
    key: "metadata_llm",
    name: "Metadata LLM",
    status: "disabled",
    detail: "desactivado",
  },
];

describe("StatusList", () => {
  it("renders each service with its localized status label and detail", () => {
    render(<StatusList services={services} />);
    expect(screen.getByText("Base de datos")).toBeInTheDocument();
    expect(screen.getByText("Operativo")).toBeInTheDocument();
    expect(screen.getByText("Degradado")).toBeInTheDocument();
    expect(screen.getByText("Desactivado")).toBeInTheDocument();
    expect(screen.getByText("latencia 3 ms")).toBeInTheDocument();
  });
});

describe("OverallBanner", () => {
  it("shows the localized overall status", () => {
    render(<OverallBanner status="ok" />);
    expect(screen.getByText("Operativo")).toBeInTheDocument();
  });

  it("reports an unreachable service when status is null", () => {
    render(<OverallBanner status={null} />);
    expect(
      screen.getByText("No se pudo contactar al servicio"),
    ).toBeInTheDocument();
  });
});
