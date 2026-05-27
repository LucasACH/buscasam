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

const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

const MANAGEABLE_DETAIL = {
  ...PUBLICO_DETAIL,
  visibility: "privado",
  manageable: true,
  versions: [
    {
      n: 1,
      original_filename: "tesis_v1.pdf",
      mime: "application/pdf",
      size_bytes: 1000,
      indexed_at: "2024-01-01T10:00:00+00:00",
      is_current: false,
    },
    {
      n: 2,
      original_filename: "tesis_v2.pdf",
      mime: "application/pdf",
      size_bytes: 2048,
      indexed_at: "2024-02-01T10:00:00+00:00",
      is_current: true,
    },
  ],
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

  test("owner: Editar CTA + Versiones panel + per-version download", async ({
    page,
  }) => {
    await page.route("**/api/me", (route) => route.fulfill(json(USER)));
    await page.route(`**/api/docs/${DOC_ID}`, (route) =>
      route.fulfill(json(MANAGEABLE_DETAIL)),
    );
    // HEAD preflight succeeds; the GET navigation streams an attachment so the
    // browser fires a native download instead of navigating away.
    await page.route(`**/api/docs/${DOC_ID}/versions/1/download`, (route) => {
      if (route.request().method() === "HEAD") {
        return route.fulfill({ status: 200 });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''tesis_v1.pdf",
        },
        body: Buffer.from("%PDF-fake-v1"),
      });
    });

    await page.goto(`/docs/${DOC_ID}`);

    const editar = page.getByRole("link", { name: /editar/i });
    await expect(editar).toBeVisible();
    await expect(editar).toHaveAttribute(
      "href",
      `/mis-trabajos/${DOC_ID}/editar`,
    );

    await expect(page.getByText("Versiones anteriores")).toBeVisible();
    await expect(page.getByText("tesis_v2.pdf")).toBeVisible();
    await expect(page.getByText("tesis_v1.pdf")).toBeVisible();

    const dl = page.waitForEvent("download");
    await page.getByRole("button", { name: /descargar versión 1/i }).click();
    const download = await dl;
    expect(download.url()).toContain(`/api/docs/${DOC_ID}/versions/1/download`);
  });

  test("logged-in non-author: no Editar CTA, no Versiones panel", async ({
    page,
  }) => {
    await page.route("**/api/me", (route) => route.fulfill(json(USER)));
    await page.route(`**/api/docs/${DOC_ID}`, (route) =>
      route.fulfill(json(PUBLICO_DETAIL)),
    );

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
    await expect(page.getByRole("link", { name: /editar/i })).toHaveCount(0);
    await expect(page.getByText("Versiones anteriores")).toHaveCount(0);
  });
});
