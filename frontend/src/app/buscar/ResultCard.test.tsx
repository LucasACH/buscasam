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

  it("omits snippet block when snippet is undefined (related rail shape)", () => {
    const { container } = render(
      <ResultCard
        result={{
          doc_id: 7,
          titulo: "Sibling",
          fecha: "2024-01-15",
          area_path: "escuela_ciencia",
          tipo: "paper",
          autores: [{ display_name: "Ada", user_id: 1 }],
        }}
      />,
    );

    expect(container.querySelector("mark")).toBeNull();
    // No paragraph for snippet or abstract should render.
    expect(container.querySelectorAll("p").length).toBe(0);
    expect(screen.getByText("Ada")).toBeInTheDocument();
  });

  it("links the title to the doc detail page", () => {
    render(
      <ResultCard
        result={{
          doc_id: 42,
          titulo: "Linked",
          fecha: "2024-01-15",
          area_path: "x",
          tipo: "paper",
        }}
      />,
    );
    const link = screen.getByRole("link", { name: "Linked" });
    expect(link).toHaveAttribute("href", "/docs/42");
  });
});
