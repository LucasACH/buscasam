import { expect, test } from "@playwright/test";

const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  { area_path: "escuela_ciencia.carrera_informatica", display_name: "Ing. Informática" },
  {
    area_path: "escuela_ciencia.carrera_informatica.materia_bd",
    display_name: "Bases de Datos",
  },
];

const DOC_ID = 42;
const TITLE = "Mi tesis BD";

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

// Full round trip: a signed-in Estudiante uploads → sees Procesando → suggestions
// populate → edits the abstract → Publicar enables → click publishes and lands on
// /mis-trabajos → an invitado in a second context finds the doc in /buscar.
test("publish happy path: upload → edit → publish → visible to invitado in /buscar", async ({
  page,
  browser,
}) => {
  let draftPolls = 0;
  let ownDocs: Array<Record<string, unknown>> = [];

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/me/documents", (route) => route.fulfill(json(ownDocs)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await page.route("**/api/areas", (route) => route.fulfill(json(AREAS)));
  await page.route("**/api/users/search**", (route) => route.fulfill(json([])));

  await page.route("**/api/documents", async (route) => {
    if (route.request().method() === "POST") {
      ownDocs = [
        { id: DOC_ID, title: TITLE, publication_status: "draft", visibility: "publico", published_at: null },
      ];
      await route.fulfill(json({ id: DOC_ID }, 201));
      return;
    }
    await route.fulfill({ status: 404, body: "" });
  });
  await page.route(`**/api/documents/${DOC_ID}/upload`, (route) =>
    route.fulfill({ status: 202, body: "" }),
  );
  // First poll: processing. Subsequent polls: indexed, publishable, owner.
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) => {
    draftPolls += 1;
    if (draftPolls === 1) {
      return route.fulfill(
        json({
          title: TITLE,
          index_status: "processing",
          staged_abstract: null,
          staged_keywords: [],
          staged_fecha: null,
          index_error: null,
          publish_gate_reason: "processing",
          is_owner: true,
        }),
      );
    }
    return route.fulfill(
      json({
        title: TITLE,
        index_status: "indexed",
        staged_abstract: "Resumen extraído por el worker",
        staged_keywords: ["bd", "sql"],
        staged_fecha: "2024-03-01",
        index_error: null,
        publish_gate_reason: null,
        is_owner: true,
      }),
    );
  });
  await page.route(`**/api/documents/${DOC_ID}`, (route) => {
    if (route.request().method() === "PATCH") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ status: 404, body: "" });
  });
  await page.route(`**/api/documents/${DOC_ID}/publish`, (route) => {
    ownDocs = [
      {
        id: DOC_ID,
        title: TITLE,
        publication_status: "published",
        visibility: "publico",
        published_at: "2024-03-01T12:00:00Z",
      },
    ];
    return route.fulfill({ status: 204, body: "" });
  });

  // 1. Upload from /nuevo.
  await page.goto("/mis-trabajos/nuevo");
  await page.getByLabel(/Título/i).fill(TITLE);
  await page.getByRole("button", { name: /Escuela de Ciencia y Tecnología/ }).click();
  await page.getByRole("button", { name: /Ing\. Informática/ }).click();
  await page.getByRole("button", { name: /Bases de Datos/ }).click();
  await page.getByLabel(/Tipo/i).selectOption("tesis");
  await page.getByLabel(/Público/i).check();
  await page.getByLabel(/Archivo principal/i).setInputFiles({
    name: "sample.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fake"),
  });
  await page.getByRole("button", { name: /Subir trabajo/i }).click();

  // 2. Land on editar with Procesando, then watch it flip to publishable.
  await expect(page).toHaveURL(new RegExp(`/mis-trabajos/${DOC_ID}/editar$`));
  await expect(page.getByTestId("status-pill")).toHaveText(/Procesando…/);
  await expect(page.getByTestId("status-pill")).toHaveText(/Listo para publicar/, {
    timeout: 10_000,
  });

  // 3. Edit the abstract; Publicar is enabled for the owner once publishable.
  const publishBtn = page.getByRole("button", { name: /Publicar/i });
  await expect(publishBtn).toBeEnabled();
  const abstract = page.getByLabel(/Resumen/i);
  await abstract.fill("Resumen editado por la autora");
  await abstract.blur();

  // 4. Publish → progress overlay holds ~2s + confetti ~1.6s before redirecting
  //    to /mis-trabajos, doc now under Publicados.
  await publishBtn.click();
  await expect(page).toHaveURL(/\/mis-trabajos$/, { timeout: 10_000 });
  await expect(page.getByRole("link", { name: new RegExp(TITLE) })).toBeVisible();

  // 5. An invitado in a second context finds the published doc in /buscar.
  const invitadoCtx = await browser.newContext();
  const invitado = await invitadoCtx.newPage();
  await invitado.route("**/api/me", (route) => route.fulfill({ status: 401, body: "" }));
  await invitado.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await invitado.route("**/api/search**", (route) =>
    route.fulfill(
      json({
        results: [
          {
            doc_id: DOC_ID,
            titulo: TITLE,
            fecha: "2024-03-01",
            area_path: "escuela_ciencia",
            tipo: "tesis",
            abstract: "Resumen editado por la autora",
            snippet: "Fragmento.",
            snippet_is_html: false,
            visibility: "publico",
          },
        ],
        total: 1,
        saturated: false,
        unfiltered_total: null,
        lexical_fallback: false,
      }),
    ),
  );

  await invitado.goto("/buscar?q=tesis");
  await expect(invitado.getByRole("heading", { name: TITLE })).toBeVisible();

  await invitadoCtx.close();
});
