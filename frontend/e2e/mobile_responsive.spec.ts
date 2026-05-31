import { expect, test } from "@playwright/test";

// Throwaway visual check: drive key views at a phone viewport and screenshot
// them, asserting no horizontal overflow. Run with:
//   pnpm exec playwright test e2e/_mobile-check.spec.ts
test.use({ viewport: { width: 360, height: 800 } });

const SEARCH_EMPTY = {
  results: [],
  total: 0,
  saturated: false,
  unfiltered_total: null,
  lexical_fallback: false,
};

const RESULTS = {
  results: Array.from({ length: 3 }).map((_, i) => ({
    doc_id: i + 1,
    titulo: "Un título de trabajo académico bastante largo para probar el wrap",
    fecha: "2023-05-01",
    area_path: "ciencia/fisica",
    tipo: "tesis",
    abstract: "Resumen de ejemplo ".repeat(8),
    autores: [{ display_name: "Ada Lovelace", user_id: 7 }],
  })),
  total: 3,
  saturated: false,
  unfiltered_total: null,
  lexical_fallback: false,
};

const USER = {
  user_id: 7,
  role: "docente",
  name: "Ada Lovelace",
  email: "ada@unsam.edu.ar",
  picture_url: null,
  hd: "unsam.edu.ar",
};

async function noHScroll(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow (px)").toBeLessThanOrEqual(0);
}

test("guest home", async ({ page }) => {
  await page.route("**/api/me", (r) => r.fulfill({ status: 401, body: "" }));
  await page.goto("/buscar");
  await expect(
    page.getByRole("link", { name: /Iniciar sesión/i }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/m-guest-home.png",
    fullPage: true,
  });
  await noHScroll(page);
});

test("guest results", async ({ page }) => {
  await page.route("**/api/me", (r) => r.fulfill({ status: 401, body: "" }));
  await page.route("**/api/search**", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(RESULTS),
    }),
  );
  await page.goto("/buscar?q=fisica");
  await expect(page.getByText(/resultado/).first()).toBeVisible();
  await page.screenshot({
    path: "test-results/m-guest-results.png",
    fullPage: true,
  });
  await noHScroll(page);
});

test("authed header", async ({ page }) => {
  await page.route("**/api/me", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(USER),
    }),
  );
  await page.route("**/api/notifications**", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], count: 0 }),
    }),
  );
  await page.route("**/api/search**", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SEARCH_EMPTY),
    }),
  );
  await page.goto("/buscar");
  await page.screenshot({ path: "test-results/m-authed-collapsed.png" });
  await noHScroll(page);
  // the avatar trigger is named via the avatar (alt/aria-label) on mobile
  await page.getByRole("button", { name: /Ada Lovelace/i }).click();
  await page.screenshot({ path: "test-results/m-authed-menu.png" });
  await expect(page.getByRole("link", { name: /Mis trabajos/i })).toBeVisible();
});
