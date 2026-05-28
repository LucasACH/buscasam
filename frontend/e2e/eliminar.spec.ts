import { expect, test } from "@playwright/test";

import { resetMocks, setMockRoute } from "./mock-helpers";

// Issue #65 tracer: an owner on the editar page of a document clicks Eliminar,
// is routed back to /mis-trabajos, the document is gone from the list, and its
// detalle page 404s. The editar + Mis trabajos surfaces are client components
// (driven through page.route); the detalle page is server-rendered against the
// mock backend, so its post-deletion 404 is configured via setMockRoute.

const DOC_ID = 88;
const TITULO = "Trabajo a eliminar";
const USER = {
  user_id: 9,
  role: "estudiante",
  name: "Owner",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

test("owner deletes from editar → routed away, gone from Mis trabajos, detalle 404s", async ({
  page,
}) => {
  let deleted = false;

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );

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

  // The Eliminar mutation. Only DELETE is owned here; anything else falls
  // through so the /draft GET above keeps its own handler.
  await page.route(`**/api/documents/${DOC_ID}`, (route) => {
    if (route.request().method() === "DELETE") {
      deleted = true;
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fallback();
  });

  // Mis trabajos list — the doc drops out once deleted (manageable_where).
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
                published_at: "2024-03-01T00:00:00Z",
              },
            ],
      ),
    ),
  );

  // Detalle is SSR → served by the mock backend, not page.route. Post-deletion
  // the reader gets a 404.
  await resetMocks();
  await setMockRoute({ path: `/api/docs/${DOC_ID}`, status: 404 });

  // 1. Land on the editar page; the owner sees Eliminar.
  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  const eliminar = page.getByRole("button", { name: "Eliminar" });
  await expect(eliminar).toBeVisible();

  // 2. Delete and get routed back to Mis trabajos.
  await eliminar.click();
  await page.waitForURL("**/mis-trabajos");
  expect(deleted).toBe(true);

  // 3. The document is absent from the list.
  await expect(page.getByText(TITULO)).toHaveCount(0);

  // 4. Its detalle page 404s.
  const response = await page.goto(`/docs/${DOC_ID}`);
  expect(response?.status()).toBe(404);
  await expect(page.getByText("No encontramos este documento")).toBeVisible();
});
