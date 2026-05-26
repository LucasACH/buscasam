import { expect, test } from "@playwright/test";

test("login?error=not_unsam shows retry copy and re-initiates the flow", async ({
  page,
}) => {
  await page.route("**/api/auth/login*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: "stub: login initiator",
    });
  });

  await page.goto("/login?error=not_unsam");

  await expect(
    page.getByText(/Solo cuentas @unsam\.edu\.ar/i),
  ).toBeVisible();

  const cta = page.getByRole("link", { name: /Probar otra cuenta/i });
  await expect(cta).toBeVisible();

  const requestPromise = page.waitForRequest("**/api/auth/login*");
  await cta.click();
  const req = await requestPromise;

  const url = new URL(req.url());
  expect(url.pathname).toBe("/api/auth/login");
  expect(url.searchParams.get("next")).toBe("/buscar");
});
