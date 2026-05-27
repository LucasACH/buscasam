import { expect, test } from "@playwright/test";

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  {
    area_path: "escuela_ciencia.carrera_informatica",
    display_name: "Ing. Informática",
  },
];

const DOC_ID = 42;
const TITULO = "Búsqueda híbrida en repositorios académicos";

const PUBLICO_DETAIL = {
  doc_id: DOC_ID,
  titulo: TITULO,
  autores: [{ display_name: "Ada Lovelace", user_id: 7 }],
  area_path: "escuela_ciencia.carrera_informatica",
  tipo: "tesis",
  fecha: "2024-03-15",
  visibility: "publico",
  abstract: "Resumen del trabajo.",
  palabras_clave: ["bd"],
  archivo_principal: {
    original_filename: "tesis.pdf",
    size_bytes: 2048,
    mime: "application/pdf",
  },
  adjuntos: [],
  manageable: false,
};

const NEIGHBOUR_DETAIL = {
  ...PUBLICO_DETAIL,
  doc_id: 100,
  titulo: "Vecino A",
};

const RELATED_FIVE = [
  {
    doc_id: 100,
    titulo: "Vecino A",
    autores: [{ display_name: "Ada", user_id: 1 }],
    area_path: "escuela_ciencia.carrera_informatica",
    tipo: "paper",
    fecha: "2024-02-01",
    similarity: 0.95,
  },
  {
    doc_id: 101,
    titulo: "Vecino B",
    autores: [{ display_name: "Bob", user_id: 2 }],
    area_path: "escuela_ciencia.carrera_informatica",
    tipo: "paper",
    fecha: "2024-01-15",
    similarity: 0.91,
  },
  {
    doc_id: 102,
    titulo: "Vecino C",
    autores: [{ display_name: "Cleo", user_id: 3 }],
    area_path: "escuela_ciencia",
    tipo: "tesis",
    fecha: "2023-12-10",
    similarity: 0.88,
  },
  {
    doc_id: 103,
    titulo: "Vecino D",
    autores: [{ display_name: "Dan", user_id: 4 }],
    area_path: "escuela_ciencia",
    tipo: "monografia",
    fecha: "2023-10-01",
    similarity: 0.84,
  },
  {
    doc_id: 104,
    titulo: "Vecino E",
    autores: [{ display_name: "Eli", user_id: 5 }],
    area_path: "escuela_ciencia",
    tipo: "paper",
    fecha: "2023-08-20",
    similarity: 0.81,
  },
];

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/docs/[id] trabajos relacionados rail", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({ status: 401, body: "" }),
    );
    await page.route("**/api/areas", (route) => route.fulfill(json(AREAS)));
    await page.route("**/api/notifications**", (route) =>
      route.fulfill(json({ items: [] })),
    );
  });

  test("invitado on publico with neighbours: rail shows up to 5 cards and links navigate", async ({
    page,
  }) => {
    await page.route(`**/api/docs/${DOC_ID}/related`, (route) =>
      route.fulfill(json(RELATED_FIVE)),
    );
    await page.route(`**/api/docs/${DOC_ID}`, (route) =>
      route.fulfill(json(PUBLICO_DETAIL)),
    );
    await page.route("**/api/docs/100/related", (route) =>
      route.fulfill(json([])),
    );
    await page.route("**/api/docs/100", (route) =>
      route.fulfill(json(NEIGHBOUR_DETAIL)),
    );

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByText("Trabajos relacionados")).toBeVisible();
    for (const titulo of [
      "Vecino A",
      "Vecino B",
      "Vecino C",
      "Vecino D",
      "Vecino E",
    ]) {
      await expect(page.getByRole("link", { name: titulo })).toBeVisible();
    }

    // Click navigates to the card's /docs/{id}.
    await page.getByRole("link", { name: "Vecino A" }).click();
    await expect(page).toHaveURL("/docs/100");
    await expect(page.getByRole("heading", { name: "Vecino A" })).toBeVisible();
  });

  test("invitado on publico with no neighbours: rail header is not rendered", async ({
    page,
  }) => {
    await page.route(`**/api/docs/${DOC_ID}/related`, (route) =>
      route.fulfill(json([])),
    );
    await page.route(`**/api/docs/${DOC_ID}`, (route) =>
      route.fulfill(json(PUBLICO_DETAIL)),
    );

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
    await expect(page.getByText(/trabajos relacionados/i)).toHaveCount(0);
  });
});
