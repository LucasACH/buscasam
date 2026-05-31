import { expect, test } from "@playwright/test";

test("invitado: AuthNav renders the login link with encoded next", async ({
  page,
}) => {
  await page.route("**/api/me", (route) =>
    route.fulfill({ status: 401, body: "" }),
  );
  await page.route("**/api/search**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: [],
        total: 0,
        saturated: false,
        unfiltered_total: null,
        lexical_fallback: false,
      }),
    }),
  );

  await page.goto("/buscar");

  const link = page.getByRole("link", { name: /Iniciar sesión con UNSAM/i });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute(
    "href",
    "/login?next=" + encodeURIComponent("/buscar"),
  );
});

test("authenticated: avatar + role label + logout returns to invitado", async ({
  page,
}) => {
  const user = {
    user_id: 7,
    role: "docente",
    name: "Ada Lovelace",
    email: "ada@unsam.edu.ar",
    picture_url: "https://example.test/a.png",
    hd: "unsam.edu.ar",
  };
  let logoutCalled = false;

  await page.route("**/api/me", (route) => {
    if (logoutCalled) return route.fulfill({ status: 401, body: "" });
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(user),
    });
  });
  await page.route("**/api/auth/logout", (route) => {
    logoutCalled = true;
    return route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/search**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: [],
        total: 0,
        saturated: false,
        unfiltered_total: null,
        lexical_fallback: false,
      }),
    }),
  );

  await page.goto("/buscar");

  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  await expect(page.getByText("Docente")).toBeVisible();

  const misTrabajos = page.getByRole("link", { name: /Mis trabajos/i });
  await expect(misTrabajos).toBeVisible();
  await expect(misTrabajos).toHaveAttribute("href", "/mis-trabajos");

  await page.getByRole("button", { name: /Ada Lovelace/i }).click();
  const logoutBtn = page.getByRole("button", { name: /Cerrar sesión/i });
  await expect(logoutBtn).toBeVisible();
  await logoutBtn.click();

  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("link", { name: /Iniciar sesión con UNSAM/i }),
  ).toBeVisible();
});
