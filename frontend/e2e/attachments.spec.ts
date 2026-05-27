import { expect, test } from "@playwright/test";

const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

const DOC_ID = 42;

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

type Attachment = {
  id: number;
  original_filename: string;
  size_bytes: number;
  mime: string;
};

function draftBody(attachments: Attachment[]) {
  return {
    title: "Mi tesis BD",
    index_status: "indexed",
    staged_abstract: "Resumen",
    staged_keywords: ["bd"],
    staged_fecha: "2024-03-01",
    index_error: null,
    publish_gate_reason: null,
    is_owner: true,
    attachments,
  };
}

async function stubCommon(page: import("@playwright/test").Page, attachments: Attachment[]) {
  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) =>
    route.fulfill(json(draftBody(attachments))),
  );
}

test("author uploads an attachment, sees it listed, and removes it (optimistic)", async ({
  page,
}) => {
  await stubCommon(page, []);

  await page.route(`**/api/documents/${DOC_ID}/attachments`, async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill(
      json(
        { id: 1, original_filename: "sample.csv", size_bytes: 64, mime: "text/csv" },
        201,
      ),
    );
  });
  // Delay the DELETE so the row's disappearance is observably optimistic.
  await page.route(`**/api/documents/${DOC_ID}/attachments/*`, async (route) => {
    expect(route.request().method()).toBe("DELETE");
    await new Promise((r) => setTimeout(r, 400));
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  await expect(page.getByTestId("status-pill")).toHaveText(/Listo para publicar/);

  await page.getByLabel(/Agregar adjunto/i).setInputFiles({
    name: "sample.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("a,b\n1,2\n"),
  });

  await expect(page.getByText(/sample\.csv/)).toBeVisible();

  await page.getByRole("button", { name: /Quitar sample\.csv/i }).click();
  // Optimistic: gone before the (delayed) DELETE resolves.
  await expect(page.getByText(/sample\.csv/)).toHaveCount(0);
});

test("5-attachment cap disables the add affordance with the spec'd copy", async ({
  page,
}) => {
  const full = [1, 2, 3, 4, 5].map((i) => ({
    id: i,
    original_filename: `f${i}.csv`,
    size_bytes: 64,
    mime: "text/csv",
  }));
  await stubCommon(page, full);

  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  await expect(page.getByTestId("status-pill")).toHaveText(/Listo para publicar/);

  await expect(page.getByText("Llegaste al máximo de 5 adjuntos")).toBeVisible();
  await expect(page.getByLabel(/Agregar adjunto/i)).toBeDisabled();
});
