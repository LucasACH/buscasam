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

function json(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  email: "ada@estudiantes.unsam.edu.ar",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

// The four test-seeded kinds — the contract producers (PRDs #3/#5/#8) satisfy.
const SEEDED = [
  {
    id: 1,
    kind: "coauthor_invite",
    payload: { doc_id: 11, doc_title: "Redes neuronales", inviter: "Bob" },
    read_at: null,
    created_at: "2026-01-04T00:00:00Z",
  },
  {
    id: 2,
    kind: "document_hidden",
    payload: { doc_id: 12, doc_title: "Grafos", reason: "contenido duplicado" },
    read_at: null,
    created_at: "2026-01-03T00:00:00Z",
  },
  {
    id: 3,
    kind: "document_unhidden",
    payload: { doc_id: 13, doc_title: "Compiladores", note: "revisado y restaurado" },
    read_at: null,
    created_at: "2026-01-02T00:00:00Z",
  },
  {
    id: 4,
    kind: "processing_failed",
    payload: { doc_id: 14, doc_title: "Álgebra lineal" },
    read_at: null,
    created_at: "2026-01-01T00:00:00Z",
  },
];

test("happy path: invitado → login → chip + bandeja loop → logout", async ({
  page,
}) => {
  let loggedIn = false;
  let marked = false;

  await page.route("**/api/me", (route) =>
    loggedIn ? route.fulfill(json(USER)) : route.fulfill({ status: 401, body: "" }),
  );
  // Mocked OIDC: the login initiator stands in for the whole Google round-trip,
  // flipping the session on and landing back on the validated `next`.
  await page.route("**/api/auth/login*", (route) => {
    loggedIn = true;
    return route.fulfill({
      status: 302,
      headers: { location: "/buscar?q=redes" },
      body: "",
    });
  });
  await page.route("**/api/auth/logout", (route) => {
    loggedIn = false;
    return route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/search**", (route) =>
    route.fulfill(
      json({
        results: loggedIn
          ? [
              result(1, "Documento público", "publico"),
              result(2, "Documento interno", "interno"),
            ]
          : [result(1, "Documento público", "publico")],
        total: loggedIn ? 2 : 1,
        saturated: false,
        unfiltered_total: null,
        lexical_fallback: false,
      }),
    ),
  );
  await page.route("**/api/notifications/unread_count", (route) =>
    route.fulfill(json({ count: loggedIn && !marked ? SEEDED.length : 0 })),
  );
  await page.route("**/api/notifications/mark_all_read", (route) => {
    marked = true;
    return route.fulfill(json({ count: SEEDED.length }));
  });
  await page.route("**/api/notifications", (route) =>
    route.fulfill(
      json({
        items: SEEDED.map((n) => ({
          ...n,
          read_at: marked ? "2026-01-05T00:00:00Z" : n.read_at,
        })),
      }),
    ),
  );

  // 1. Invitado: results render with no visibility chips.
  await page.goto("/buscar?q=redes");
  await expect(page.getByText("Documento público")).toBeVisible();
  await expect(page.getByText("Interno", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Privado", { exact: true })).toHaveCount(0);

  // 2. Log in through the (mocked) UNSAM flow. The header link lands on /login;
  // the page CTA initiates the (mocked) OIDC round-trip back to /buscar.
  await page.getByRole("link", { name: /Iniciar sesión con UNSAM/i }).click();
  await expect(page).toHaveURL(/\/login/);
  await page
    .locator("main")
    .getByRole("link", { name: /Iniciar sesión con UNSAM/i })
    .click();
  await expect(page).toHaveURL(/\/buscar/);

  // 3. Post-login: the Interno chip surfaces on the same query.
  await expect(page.getByText("Ada Lovelace")).toBeVisible();
  const internoCard = page
    .locator("article")
    .filter({ hasText: "Documento interno" });
  await expect(internoCard.getByText("Interno", { exact: true })).toBeVisible();

  // 4. The bell badge shows the seeded unread count.
  const bell = page.getByRole("button", { name: /Notificaciones/i });
  await expect(bell).toContainText(String(SEEDED.length));

  // 5. Opening the popover renders all four per-kind renderers and clears the badge.
  await bell.click();
  await expect(page.getByText(/Redes neuronales/)).toBeVisible();
  await expect(page.getByText(/Bob/)).toBeVisible();
  await expect(page.getByText(/Grafos/)).toBeVisible();
  await expect(page.getByText(/contenido duplicado/)).toBeVisible();
  await expect(page.getByText(/Compiladores/)).toBeVisible();
  await expect(page.getByText(/revisado y restaurado/)).toBeVisible();
  await expect(page.getByText(/Álgebra lineal/)).toBeVisible();
  await expect(bell).not.toContainText(String(SEEDED.length));

  // 6. Logout (inside the user menu) returns to the invitado view.
  await page.getByRole("button", { name: /Ada Lovelace/i }).click();
  await page.getByRole("button", { name: /Cerrar sesión/i }).click();
  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("link", { name: /Iniciar sesión con UNSAM/i }),
  ).toBeVisible();
});
