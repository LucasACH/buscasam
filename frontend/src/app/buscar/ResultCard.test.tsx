import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it } from "vitest";

import { ResultCard, type ResultCardData } from "./ResultCard";

function renderCard(result: ResultCardData) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ResultCard result={result} />
    </QueryClientProvider>,
  );
}

describe("ResultCard", () => {
  afterEach(() => cleanup());

  it("renders document markup as text while preserving lexical highlights", () => {
    const { container } = renderCard({
      doc_id: 1,
      titulo: "Documento",
      fecha: "2026-05-27",
      area_path: "ingenieria",
      tipo: "tesis",
      abstract: null,
      snippet: '<img src="x" onerror="alert(1)"> Redes <mark>neuronales</mark>',
      snippet_is_html: true,
      visibility: "publico",
    });

    expect(container.querySelector("img")).toBeNull();
    expect(
      screen.getByText(/<img src="x" onerror="alert\(1\)">/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("neuronales", { selector: "mark" }),
    ).toBeInTheDocument();
  });

  it("falls back to abstract when the snippet has no highlight (no exact match)", () => {
    const { container } = renderCard({
      doc_id: 3,
      titulo: "Multa",
      fecha: "2026-01-01",
      area_path: "ingenieria",
      tipo: "tesis",
      abstract: "Francisco presenta un descargo ante un acta de comprobación.",
      snippet: "Francisco presenta un descargo ante un acta de comprobación.",
      snippet_is_html: true,
      visibility: "publico",
    });

    expect(container.querySelectorAll("p").length).toBe(1);
    expect(
      screen.getByText(
        "Francisco presenta un descargo ante un acta de comprobación.",
      ),
    ).toBeInTheDocument();
  });

  it("omits snippet block when snippet is undefined (related rail shape)", () => {
    const { container } = renderCard({
      doc_id: 7,
      titulo: "Sibling",
      fecha: "2024-01-15",
      area_path: "escuela_ciencia",
      tipo: "paper",
      autores: [{ display_name: "Ada", user_id: 1 }],
    });

    expect(container.querySelector("mark")).toBeNull();
    // No paragraph for snippet or abstract should render.
    expect(container.querySelectorAll("p").length).toBe(0);
    expect(screen.getByText("Ada")).toBeInTheDocument();
  });

  it("links the title to the doc detail page", () => {
    renderCard({
      doc_id: 42,
      titulo: "Linked",
      fecha: "2024-01-15",
      area_path: "x",
      tipo: "paper",
    });
    const link = screen.getByRole("link", { name: "Linked" });
    expect(link).toHaveAttribute("href", "/docs/42");
  });
});
