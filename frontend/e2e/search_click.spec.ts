import { expect, test } from "@playwright/test";

import { getRecorded, setMockRoute } from "./mock-helpers";

// Unique ids so this spec is isolated on the shared mock-backend (no reset →
// parallel-safe): nothing else POSTs to /api/search/click with this search_id.
const DOC_ID = 9777;
const SEARCH_ID = "e2e-search-click-9777";
const TITULO = "Documento clickeable de prueba";

const RESULT = {
  doc_id: DOC_ID,
  titulo: TITULO,
  fecha: "2024-01-01",
  area_path: "escuela_ciencia",
  tipo: "paper",
  abstract: null,
  snippet: "Fragmento de prueba.",
  snippet_is_html: false,
  visibility: "publico",
};

const DETAIL = {
  view: "detail",
  doc_id: DOC_ID,
  titulo: TITULO,
  autores: [],
  area_path: "escuela_ciencia",
  tipo: "paper",
  fecha: "2024-01-01",
  visibility: "publico",
  abstract: "Resumen del trabajo.",
  palabras_clave: [],
  archivo_principal: {
    original_filename: "trabajo.pdf",
    size_bytes: 2048,
    mime: "application/pdf",
  },
  adjuntos: [],
  manageable: false,
};

function json(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test("search result click records a server-side click with Origin", async ({
  page,
  baseURL,
}) => {
  // SSR routes the Next server fetches from the mock backend.
  await setMockRoute({ path: "/api/areas", status: 200, body: [] });
  await setMockRoute({
    path: `/api/docs/${DOC_ID}`,
    status: 200,
    body: DETAIL,
  });

  // Browser-side calls.
  await page.route("**/api/me", (r) => r.fulfill({ status: 401, body: "" }));
  await page.route("**/api/notifications**", (r) =>
    r.fulfill(json({ items: [] })),
  );
  await page.route(`**/api/docs/${DOC_ID}/related`, (r) => r.fulfill(json([])));
  await page.route("**/api/search**", (r) =>
    r.fulfill(
      json({
        results: [RESULT],
        total: 1,
        saturated: false,
        unfiltered_total: null,
        lexical_fallback: false,
        fuzzy_fallback: false,
        search_id: SEARCH_ID,
      }),
    ),
  );

  await page.goto("/buscar?q=prueba");

  // R001 wiring: the result link carries the originating search + global rank.
  const link = page.getByRole("link", { name: TITULO });
  const href = `/docs/${DOC_ID}?s=${SEARCH_ID}&r=1`;
  await expect(link).toHaveAttribute("href", href);

  // Visiting that link renders the doc page; the click is attributed
  // server-side via after() (no JS beacon).
  await page.goto(href);
  await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();

  // after() runs post-response: poll the mock for the recorded click POST.
  const clickPath = "/api/search/click";
  const ours = async () =>
    (await getRecorded()).filter(
      (e) =>
        e.method === "POST" &&
        e.path === clickPath &&
        e.body.includes(SEARCH_ID),
    );
  await expect.poll(async () => (await ours()).length).toBeGreaterThan(0);

  const click = (await ours())[0];
  expect(JSON.parse(click.body)).toEqual({
    search_id: SEARCH_ID,
    doc_id: DOC_ID,
    rank: 1,
  });
  // R005 regression guard: the SSR POST must carry Origin = the site origin, or
  // the backend CSRF Origin-check 403s it for any visitor with a sid cookie.
  expect(click.headers.origin).toBe(baseURL);
});

// Distinct doc id so the negative assertion is scoped to this test on the
// shared recorder (other specs' clicks must not make it flake).
const DOC_ID_NO_SEARCH = 9778;

test("browsing a doc without ?s= records no click", async ({ page }) => {
  await setMockRoute({ path: "/api/areas", status: 200, body: [] });
  await setMockRoute({
    path: `/api/docs/${DOC_ID_NO_SEARCH}`,
    status: 200,
    body: { ...DETAIL, doc_id: DOC_ID_NO_SEARCH },
  });
  await page.route("**/api/me", (r) => r.fulfill({ status: 401, body: "" }));
  await page.route("**/api/notifications**", (r) =>
    r.fulfill(json({ items: [] })),
  );
  await page.route(`**/api/docs/${DOC_ID_NO_SEARCH}/related`, (r) =>
    r.fulfill(json([])),
  );

  await page.goto(`/docs/${DOC_ID_NO_SEARCH}`);
  await expect(page.getByRole("heading", { name: TITULO })).toBeVisible();

  // No originating search → page.tsx schedules no after(), so no click POST
  // for this doc is ever recorded.
  const clicks = (await getRecorded()).filter(
    (e) =>
      e.method === "POST" &&
      e.path === "/api/search/click" &&
      JSON.parse(e.body).doc_id === DOC_ID_NO_SEARCH,
  );
  expect(clicks).toHaveLength(0);
});
