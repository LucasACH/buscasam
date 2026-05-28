import { expect, test } from "@playwright/test";

import { resetMocks, setMockRoute } from "./mock-helpers";

// Issue #66 tracer: an owner deletes a published document, it leaves Mis
// trabajos and appears in the Papelera with a "Se elimina en N días" countdown,
// and Restaurar returns it to Mis trabajos and to its detalle page. The list
// surfaces are client components (page.route); detalle is SSR against the mock
// backend (setMockRoute). This file owns DOC_ID 91; serial mode keeps its
// /api/docs/91 registry slot from racing other specs.
test.describe.configure({ mode: "serial" });

const DOC_ID = 91;
const TITULO = "Trabajo restaurable";
const PURGE_AT = new Date(Date.now() + 90 * 24 * 3600 * 1000).toISOString();

const USER = {
  user_id: 9,
  role: "estudiante",
  name: "Owner",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

const DETAIL = {
  view: "detail",
  doc_id: DOC_ID,
  titulo: TITULO,
  autores: [{ display_name: "Owner", user_id: 9 }],
  area_path: "escuela_ciencia",
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

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

test("delete → Papelera countdown → Restaurar returns to Mis trabajos + detalle", async ({
  page,
}) => {
  let deleted = false;

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );

  // Editar page draft channel — owner sees Eliminar.
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) =>
    route.fulfill(
      json({
        title: TITULO,
        index_status: "indexed",
        staged_abstract: "Resumen",
        staged_keywords: [],
        staged_fecha: null,
        index_error: null,
        publish_gate_reason: null,
        is_owner: true,
        attachments: [],
        coauthors: [
          { user_id: 9, display_name: "Owner", email_local: "owner", status: "owner" },
        ],
        versions: [
          {
            n: 1,
            original_filename: "v1.pdf",
            mime: "application/pdf",
            size_bytes: 2048,
            indexed_at: "2024-03-01T00:00:00Z",
            is_current: true,
          },
        ],
        candidate: null,
      }),
    ),
  );

  // Soft-delete (DELETE) and restore (POST) flip the shared `deleted` flag.
  await page.route(`**/api/documents/${DOC_ID}/restore`, (route) => {
    if (route.request().method() === "POST") {
      deleted = false;
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fallback();
  });
  await page.route(`**/api/documents/${DOC_ID}`, (route) => {
    if (route.request().method() === "DELETE") {
      deleted = true;
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fallback();
  });

  // Mis trabajos drops the doc once deleted (manageable_where excludes it).
  await page.route("**/api/me/documents", (route) =>
    route.fulfill(
      json(
        deleted
          ? []
          : [
              {
                id: DOC_ID,
                title: TITULO,
                publication_status: "published",
                visibility: "publico",
                published_at: "2024-03-01T00:00:00Z",
              },
            ],
      ),
    ),
  );
  // Papelera shows the doc only while deleted (restorable_where selects it).
  await page.route("**/api/me/documents/deleted", (route) =>
    route.fulfill(
      json(
        deleted
          ? [
              {
                id: DOC_ID,
                title: TITULO,
                publication_status: "published",
                purge_at: PURGE_AT,
              },
            ]
          : [],
      ),
    ),
  );

  await setMockRoute({
    path: "/api/areas",
    status: 200,
    body: [
      { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
    ],
  });

  // 1. Owner deletes from the editar page → routed back to Mis trabajos, gone.
  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  await page.getByRole("button", { name: "Eliminar" }).click();
  await page.waitForURL("**/mis-trabajos");
  expect(deleted).toBe(true);
  await expect(page.getByText(TITULO)).toHaveCount(0);

  // 2. It appears in the Papelera with a days-remaining countdown.
  await page.getByRole("link", { name: "Papelera" }).click();
  await page.waitForURL("**/mis-trabajos/papelera");
  await expect(page.getByText(TITULO)).toBeVisible();
  await expect(page.getByText(/Se elimina en \d+ días/)).toBeVisible();

  // While deleted, the detalle page 404s for the reader.
  await setMockRoute({ path: `/api/docs/${DOC_ID}`, status: 404 });
  const gone = await page.goto(`/docs/${DOC_ID}`);
  expect(gone?.status()).toBe(404);

  // 3. Restaurar returns the doc to Mis trabajos and to its detalle page.
  await page.goto("/mis-trabajos/papelera");
  await page.getByRole("button", { name: "Restaurar" }).click();
  await expect(page.getByText(TITULO)).toHaveCount(0); // left the Papelera
  expect(deleted).toBe(false);

  await page.goto("/mis-trabajos");
  await expect(page.getByText(TITULO)).toBeVisible(); // back in Mis trabajos

  await setMockRoute({ path: `/api/docs/${DOC_ID}`, status: 200, body: DETAIL });
  const back = await page.goto(`/docs/${DOC_ID}`);
  expect(back?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
});
