import { expect, test } from "@playwright/test";

import { setMockRoute } from "./mock-helpers";

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  {
    area_path: "escuela_ciencia.carrera_informatica",
    display_name: "Ing. Informática",
  },
];

// This file owns DOC_ID 43 + neighbour 200 in the shared mock-backend registry.
const DOC_ID = 43;
const NEIGHBOUR_ID = 200;
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
  doc_id: NEIGHBOUR_ID,
  titulo: "Vecino A",
};

const RELATED_FIVE = [
  {
    doc_id: NEIGHBOUR_ID,
    titulo: "Vecino A",
    autores: [{ display_name: "Ada", user_id: 1 }],
    area_path: "escuela_ciencia.carrera_informatica",
    tipo: "paper",
    fecha: "2024-02-01",
    similarity: 0.95,
  },
  {
    doc_id: 201,
    titulo: "Vecino B",
    autores: [{ display_name: "Bob", user_id: 2 }],
    area_path: "escuela_ciencia.carrera_informatica",
    tipo: "paper",
    fecha: "2024-01-15",
    similarity: 0.91,
  },
  {
    doc_id: 202,
    titulo: "Vecino C",
    autores: [{ display_name: "Cleo", user_id: 3 }],
    area_path: "escuela_ciencia",
    tipo: "tesis",
    fecha: "2023-12-10",
    similarity: 0.88,
  },
  {
    doc_id: 203,
    titulo: "Vecino D",
    autores: [{ display_name: "Dan", user_id: 4 }],
    area_path: "escuela_ciencia",
    tipo: "monografia",
    fecha: "2023-10-01",
    similarity: 0.84,
  },
  {
    doc_id: 204,
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

// Serial: later tests overwrite the registry slot for /api/docs/43.
test.describe.configure({ mode: "serial" });

test.describe("/docs/[id] trabajos relacionados rail", () => {
  test.beforeEach(async ({ page }) => {
    await setMockRoute({ path: "/api/areas", status: 200, body: AREAS });
    await page.route("**/api/me", (route) =>
      route.fulfill({ status: 401, body: "" }),
    );
    await page.route("**/api/notifications**", (route) =>
      route.fulfill(json({ items: [] })),
    );
  });

  test("invitado on publico with neighbours: rail shows up to 5 cards and links navigate", async ({
    page,
  }) => {
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: PUBLICO_DETAIL,
    });
    await setMockRoute({
      path: `/api/docs/${NEIGHBOUR_ID}`,
      status: 200,
      body: NEIGHBOUR_DETAIL,
    });
    await page.route(`**/api/docs/${DOC_ID}/related`, (route) =>
      route.fulfill(json(RELATED_FIVE)),
    );
    await page.route(`**/api/docs/${NEIGHBOUR_ID}/related`, (route) =>
      route.fulfill(json([])),
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
    await expect(page).toHaveURL(`/docs/${NEIGHBOUR_ID}`);
    await expect(page.getByRole("heading", { name: "Vecino A" })).toBeVisible();
  });

  test("invitado on publico with no neighbours: rail header is not rendered", async ({
    page,
  }) => {
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: PUBLICO_DETAIL,
    });
    await page.route(`**/api/docs/${DOC_ID}/related`, (route) =>
      route.fulfill(json([])),
    );

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
    await expect(page.getByText(/trabajos relacionados/i)).toHaveCount(0);
  });
});
