import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ProcessingSteps } from "./ProcessingSteps";

afterEach(cleanup);

describe("ProcessingSteps", () => {
  it("shows the stage label when a checkpoint is set", () => {
    render(<ProcessingSteps stage="summarizing" />);
    expect(screen.getByText("Generando resumen y palabras clave")).toBeTruthy();
  });

  it("shows 'En cola' only while genuinely queued", () => {
    render(<ProcessingSteps stage={null} queued />);
    expect(screen.getByText("En cola")).toBeTruthy();
  });

  it("shows 'Procesando…' when processing without a stage yet", () => {
    render(<ProcessingSteps stage={null} />);
    expect(screen.getByText("Procesando…")).toBeTruthy();
    expect(screen.queryByText("En cola")).toBeNull();
  });
});
