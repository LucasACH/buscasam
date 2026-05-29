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

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

// Upload → lands on /editar/{id} blocked behind the indexing loader (Procesando
// pill); unblocks to the edit form once the mocked /draft response advances to
// indexed and the pill flips to "Listo para publicar".
test("upload happy path: nuevo → editar pill flips from Procesando to Listo", async ({
  page,
}) => {
  const DOC_ID = 42;
  // The "test-mode synchronous worker" is just a poll counter on the mocked
  // /draft endpoint: first call returns processing, subsequent calls return
  // indexed. Mirrors what the production worker would do.
  let draftPolls = 0;
  let ownDocs: Array<{
    id: number;
    title: string;
    publication_status: string;
    visibility: string;
  }> = [];

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
        { id: DOC_ID, title: "Mi tesis BD", publication_status: "draft", visibility: "publico" },
      ];
      await route.fulfill(json({ id: DOC_ID }, 201));
      return;
    }
    await route.fulfill({ status: 404, body: "" });
  });
  await page.route(`**/api/documents/${DOC_ID}/upload`, (route) =>
    route.fulfill({ status: 202, body: "" }),
  );
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) => {
    draftPolls += 1;
    if (draftPolls === 1) {
      return route.fulfill(
        json({
          title: "Mi tesis BD",
          index_status: "processing",
          staged_abstract: null,
          staged_keywords: [],
          staged_fecha: null,
          index_error: null,
          publish_gate_reason: "processing",
          is_owner: true,
          visibility: "publico",
          attachments: [],
          coauthors: [],
          versions: [],
          candidate: null,
        }),
      );
    }
    return route.fulfill(
      json({
        title: "Mi tesis BD",
        index_status: "indexed",
        staged_abstract: "Resumen extraído por el worker",
        staged_keywords: ["bd", "sql"],
        staged_fecha: "2024-03-01",
        index_error: null,
        publish_gate_reason: null,
        is_owner: true,
        visibility: "publico",
        attachments: [],
        coauthors: [],
        versions: [],
        candidate: null,
      }),
    );
  });

  // 1. Land on /mis-trabajos/nuevo as signed-in user.
  await page.goto("/mis-trabajos/nuevo");
  await expect(page.getByRole("heading", { name: /Nuevo trabajo/ })).toBeVisible();

  // 2. Fill the form.
  await page.getByLabel(/Título/i).fill("Mi tesis BD");

  await expect(page.getByRole("combobox", { name: /Escuela/i })).toContainText(
    /Ciencia/,
  );
  await page
    .getByRole("combobox", { name: /Escuela/i })
    .selectOption("escuela_ciencia");
  await page
    .getByRole("combobox", { name: /Carrera/i })
    .selectOption("escuela_ciencia.carrera_informatica");
  await page
    .getByRole("combobox", { name: /Materia/i })
    .selectOption("escuela_ciencia.carrera_informatica.materia_bd");

  await page.getByLabel(/Tipo/i).selectOption("tesis");
  await page.getByLabel(/Público/i).check();

  await page.getByLabel(/Archivo principal/i).setInputFiles({
    name: "tesis.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fake"),
  });

  // 3. Submit and land on the editar page.
  await page.getByRole("button", { name: /Subir trabajo/i }).click();
  await expect(page).toHaveURL(new RegExp(`/mis-trabajos/${DOC_ID}/editar$`));

  // 4. First /draft poll → page is blocked behind the full-page indexing loader
  // (initial-publication path), with the Procesando… pill.
  await expect(page.getByTestId("status-pill")).toHaveText(/Procesando…/);
  await expect(page.getByTestId("indexing-block")).toBeVisible();

  // 5. After the mocked worker advances, the page unblocks: the pill flips to
  // Listo and the suggestions populate.
  await expect(page.getByTestId("status-pill")).toHaveText(/Listo para publicar/, {
    timeout: 10_000,
  });
  await expect(page.getByTestId("suggestion-abstract")).toContainText(
    /Resumen extraído por el worker/,
  );
});
