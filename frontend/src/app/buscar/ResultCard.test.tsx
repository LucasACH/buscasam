import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResultCard } from "./ResultCard";

describe("ResultCard", () => {
  it("renders document markup as text while preserving lexical highlights", () => {
    const { container } = render(
      <ResultCard
        result={{
          doc_id: 1,
          titulo: "Documento",
          fecha: "2026-05-27",
          area_path: "ingenieria",
          tipo: "tesis",
          abstract: null,
          snippet:
            '<img src="x" onerror="alert(1)"> Redes <mark>neuronales</mark>',
          snippet_is_html: true,
          visibility: "publico",
        }}
      />,
    );

    expect(container.querySelector("img")).toBeNull();
    expect(
      screen.getByText(/<img src="x" onerror="alert\(1\)">/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("neuronales", { selector: "mark" }),
    ).toBeInTheDocument();
  });
});
