import { expect, test } from "@playwright/test";

import { setMockRoute } from "./mock-helpers";

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
  view: "detail",
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

const PENDING_MINIMAL = {
  view: "minimal",
  doc_id: DOC_ID,
  titulo: TITULO,
  inviter_display_name: "Ada Lovelace",
};

const DETAIL_WITH_INVITATION = {
  ...PUBLICO_DETAIL,
  view: "detail_with_invitation",
  invitation: { inviter_display_name: "Ada Lovelace" },
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
  view: "detail",
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

// The mock-backend is shared across all specs; this file owns DOC_ID 42 and
// serial mode lets later tests overwrite the registry slot for /api/docs/42.
test.describe.configure({ mode: "serial" });

test.describe("/docs/[id] reader page (SSR)", () => {
  test.beforeEach(async ({ page }) => {
    // Always-present SSR route: áreas tree resolves display names. Idempotent.
    await setMockRoute({ path: "/api/areas", status: 200, body: AREAS });

    // Browser-side AuthNav requests stay mocked at the Playwright layer.
    await page.route("**/api/me", (route) =>
      route.fulfill({ status: 401, body: "" }),
    );
    await page.route("**/api/notifications**", (route) =>
      route.fulfill(json({ items: [] })),
    );
  });

  test("invitado on publico: metadata + downloads + tab title", async ({
    page,
  }) => {
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: PUBLICO_DETAIL,
    });
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

  test("invitado on interno: same empty state as non-existent id, 404 status", async ({
    page,
  }) => {
    // Mock-backend returns 404, fetchDetail returns null, page calls notFound()
    // → not-found.tsx renders and the response carries HTTP 404.
    await setMockRoute({ path: `/api/docs/${DOC_ID}`, status: 404 });

    const response = await page.goto(`/docs/${DOC_ID}`);

    expect(response?.status()).toBe(404);
    await expect(page.getByText("No encontramos este documento")).toBeVisible();
    await expect(page.getByRole("link", { name: /descargar/i })).toHaveCount(0);
  });

  test("owner: Editar CTA + Versiones panel + per-version download", async ({
    page,
  }) => {
    await page.unroute("**/api/me");
    await page.route("**/api/me", (route) => route.fulfill(json(USER)));
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: MANAGEABLE_DETAIL,
    });
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
    await page.unroute("**/api/me");
    await page.route("**/api/me", (route) => route.fulfill(json(USER)));
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: PUBLICO_DETAIL,
    });

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
    await expect(page.getByRole("link", { name: /editar/i })).toHaveCount(0);
    await expect(page.getByText("Versiones anteriores")).toHaveCount(0);
  });

  test("pending invitee on privado: minimal disclosure block only", async ({
    page,
  }) => {
    await page.unroute("**/api/me");
    await page.route("**/api/me", (route) => route.fulfill(json(USER)));
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: PENDING_MINIMAL,
    });

    await page.goto(`/docs/${DOC_ID}`);

    // The invitation banner is the whole page body.
    await expect(page.getByText(/te invitó como coautor/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Aceptar/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Rechazar/i })).toBeVisible();
    // No metadata, abstract, downloads, Editar CTA, or Versiones panel leak.
    await expect(page.getByRole("heading", { name: TITULO })).toHaveCount(0);
    await expect(page.getByText("Resumen del trabajo.")).toHaveCount(0);
    await expect(page.getByRole("link", { name: /descargar/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /editar/i })).toHaveCount(0);
    await expect(page.getByText("Versiones anteriores")).toHaveCount(0);
  });

  test("pending invitee on readable doc: banner above the full detail", async ({
    page,
  }) => {
    await page.unroute("**/api/me");
    await page.route("**/api/me", (route) => route.fulfill(json(USER)));
    await setMockRoute({
      path: `/api/docs/${DOC_ID}`,
      status: 200,
      body: DETAIL_WITH_INVITATION,
    });

    await page.goto(`/docs/${DOC_ID}`);

    await expect(page.getByText(/te invitó como coautor/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Aceptar/i })).toBeVisible();
    // The full reader view is still present below the banner.
    await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();
    await expect(page.getByText("Resumen del trabajo.")).toBeVisible();
    await expect(page.getByText("tesis.pdf")).toBeVisible();
  });
});
