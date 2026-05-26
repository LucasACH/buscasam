import { expect, test } from "@playwright/test";

type Visibility = "publico" | "interno" | "privado";

function result(doc_id: number, titulo: string, visibility: Visibility) {
  return {
    doc_id,
    titulo,
    fecha: "2024-01-01",
    area_path: "escuela_ciencia",
    tipo: "paper",
    abstract: null,
    snippet: "Fragmento de prueba.",
    snippet_is_html: false,
    visibility,
  };
}

function searchResponse(results: ReturnType<typeof result>[]) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      results,
      total: results.length,
      saturated: false,
      unfiltered_total: null,
      lexical_fallback: false,
    }),
  };
}

test("invitado: results carry no visibility chips", async ({ page }) => {
  await page.route("**/api/me", (route) =>
    route.fulfill({ status: 401, body: "" }),
  );
  await page.route("**/api/search**", (route) =>
    route.fulfill(searchResponse([result(1, "Documento público", "publico")])),
  );

  await page.goto("/buscar?q=redes");

  await expect(page.getByText("Documento público")).toBeVisible();
  await expect(page.getByText("Interno")).toHaveCount(0);
  await expect(page.getByText("Privado")).toHaveCount(0);
});

test("authenticated: Interno/Privado chips render on non-publico results", async ({
  page,
}) => {
  await page.route("**/api/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: 7,
        role: "estudiante",
        name: "Ada Lovelace",
        picture_url: null,
        hd: "estudiantes.unsam.edu.ar",
      }),
    }),
  );
  await page.route("**/api/search**", (route) =>
    route.fulfill(
      searchResponse([
        result(1, "Documento público", "publico"),
        result(2, "Documento interno", "interno"),
        result(3, "Documento privado", "privado"),
      ]),
    ),
  );

  await page.goto("/buscar?q=redes");

  const publicoCard = page
    .locator("article")
    .filter({ hasText: "Documento público" });
  const internoCard = page
    .locator("article")
    .filter({ hasText: "Documento interno" });
  const privadoCard = page
    .locator("article")
    .filter({ hasText: "Documento privado" });

  await expect(internoCard.getByText("Interno", { exact: true })).toBeVisible();
  await expect(privadoCard.getByText("Privado", { exact: true })).toBeVisible();
  await expect(publicoCard.getByText("Interno", { exact: true })).toHaveCount(0);
  await expect(publicoCard.getByText("Privado", { exact: true })).toHaveCount(0);
});
