import { expect, test } from "@playwright/test";

// Issue #76 tracer: a Docente reaches the moderation queue from the nav and sees
// one entry per reported document with its reason(s) and reporter count. The page
// is a client component (useUser + typed-client fetch), so page.route intercepts
// both /api/me and /api/moderation/queue.

const DOCENTE = {
  user_id: 3,
  role: "docente",
  name: "Docente",
  picture_url: null,
  hd: "unsam.edu.ar",
};

const ENTRY = {
  doc_id: 42,
  title: "Trabajo reportado",
  reasons: ["plagio", "spam"],
  first_reported_at: "2026-01-01T00:00:00Z",
  last_reported_at: "2026-01-05T00:00:00Z",
  report_count: 3,
};

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

test("docente reaches the queue from the nav and sees a reported document", async ({
  page,
}) => {
  await page.route("**/api/me", (route) => route.fulfill(json(DOCENTE)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await page.route("**/api/moderation/queue", (route) =>
    route.fulfill(json({ items: [ENTRY] })),
  );

  await page.goto("/buscar");
  await page.getByRole("link", { name: "Moderación" }).click();
  await page.waitForURL("**/moderacion");

  await expect(page.getByText("Trabajo reportado")).toBeVisible();
  await expect(page.getByText(/plagio, spam/)).toBeVisible();
  await expect(page.getByText(/3 reportes/)).toBeVisible();
});
