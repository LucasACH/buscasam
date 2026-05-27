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
  adjuntos: [
    { id: 101, original_filename: "datos.csv", size_bytes: 512, mime: "text/csv" },
  ],
  manageable: false,
};

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/docs/[id] reader page", () => {
  test.beforeEach(async ({ page }) => {
    // Invitado: /api/me returns 401.
    await page.route("**/api/me", (route) =>
      route.fulfill({ status: 401, body: "" }),
    );
    await page.route("**/api/areas", (route) => route.fulfill(json(AREAS)));
    await page.route("**/api/notifications**", (route) =>
      route.fulfill(json({ items: [] })),
    );
  });

  test("invitado on publico: metadata + downloads + tab title", async ({
    page,
  }) => {
    await page.route(`**/api/docs/${DOC_ID}`, (route) =>
      route.fulfill(json(PUBLICO_DETAIL)),
    );
    // Both download endpoints reply with a small attachment-style body so the
    // browser triggers a download event.
    await page.route(`**/api/docs/${DOC_ID}/download`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''tesis.pdf",
        },
        body: Buffer.from("%PDF-fake"),
      }),
    );
    await page.route(`**/api/docs/${DOC_ID}/attachments/101`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/csv",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''datos.csv",
        },
        body: "a,b\n1,2\n",
      }),
    );

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
    await expect(page.getByText("Ada Lovelace")).toBeVisible();
    await expect(page.getByText("Ing. Informática")).toBeVisible();
    await expect(page.getByText("Tesis", { exact: true })).toBeVisible();
    await expect(page.getByText("2024-03-15")).toBeVisible();
    await expect(page.getByText("Resumen del trabajo.")).toBeVisible();
    await expect(page.getByText("bd", { exact: true })).toBeVisible();
    await expect(page.getByText("tesis.pdf")).toBeVisible();
    await expect(page.getByText("datos.csv")).toBeVisible();
    await expect(page).toHaveTitle(TITULO);

    const mainDl = page.waitForEvent("download");
    await page.getByRole("link", { name: /descargar archivo principal/i }).click();
    const mainDownload = await mainDl;
    expect(mainDownload.url()).toContain(`/api/docs/${DOC_ID}/download`);

    const attDl = page.waitForEvent("download");
    await page.getByRole("link", { name: /descargar datos\.csv/i }).click();
    const attDownload = await attDl;
    expect(attDownload.url()).toContain(
      `/api/docs/${DOC_ID}/attachments/101`,
    );
  });

  test("invitado on interno: same empty state as non-existent id", async ({
    page,
  }) => {
    await page.route(`**/api/docs/${DOC_ID}`, (route) =>
      route.fulfill({ status: 404, body: "" }),
    );

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByText("No encontramos este documento")).toBeVisible();
    // No metadata leak: no Descargar links rendered.
    await expect(page.getByRole("link", { name: /descargar/i })).toHaveCount(0);
  });
});
