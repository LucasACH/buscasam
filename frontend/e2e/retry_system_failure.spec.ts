import { expect, test } from "@playwright/test";

// An initial upload terminally fails on our side (kind='system'). The failed
// block shows the our-fault copy and a Reintentar button that counts down the
// server cooldown, then re-enqueues processing on click. Driven through
// page.route — POST /retry-indexing advances a small state machine the next
// draft poll reflects, and the processing phase auto-advances to indexed so
// the page unblocks into the form.

const DOC_ID = 91;
const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

type Phase = "failed" | "processing" | "indexed";

function draftBody(phase: Phase, retryAvailableAt: string | null) {
  const base = {
    title: "Mi tesis",
    index_stage: phase === "processing" ? "reading" : null,
    staged_abstract: phase === "indexed" ? "Resumen extraído" : null,
    staged_keywords: phase === "indexed" ? ["redes"] : [],
    staged_fecha: null,
    generated_abstract: null,
    generated_keywords: [],
    generated_fecha: null,
    is_owner: true,
    visibility: "publico",
    area_path: "escuela_ciencia",
    published_at: null,
    attachments: [],
    coauthors: [
      {
        user_id: 7,
        display_name: "Ada Lovelace",
        email_local: "ada",
        email: null,
        status: "owner",
      },
    ],
    versions: [],
    candidate: null,
  };
  if (phase === "failed")
    return {
      ...base,
      index_status: "failed",
      index_error: "exhausted retries: EmbedUnavailable",
      index_failure_kind: "system",
      retry_available_at: retryAvailableAt,
      retry_remaining: 3,
      publish_gate_reason: "processing_failed",
    };
  if (phase === "processing")
    return {
      ...base,
      index_status: "processing",
      index_error: null,
      index_failure_kind: null,
      retry_available_at: null,
      retry_remaining: 2,
      publish_gate_reason: "processing",
    };
  return {
    ...base,
    index_status: "indexed",
    index_error: null,
    index_failure_kind: null,
    retry_available_at: null,
    retry_remaining: 2,
    publish_gate_reason: null,
  };
}

test("retrying a system failure counts down, re-enqueues and unblocks the page", async ({
  page,
}) => {
  let phase: Phase = "failed";
  let processingPolls = 0;
  // Cooldown ends shortly after the page lands, so the spec exercises both
  // the disabled-countdown state and the enabled click.
  const retryAvailableAt = new Date(Date.now() + 4_000).toISOString();

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) => {
    // The worker is fake: after a couple of processing polls, flip to indexed.
    if (phase === "processing" && ++processingPolls >= 2) phase = "indexed";
    return route.fulfill(json(draftBody(phase, retryAvailableAt)));
  });
  await page.route(`**/api/documents/${DOC_ID}/retry-indexing`, (route) => {
    phase = "processing";
    return route.fulfill({ status: 204, body: "" });
  });

  // 1. Land on the failed page: our-fault copy + Reintentar counting down.
  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  const failedBlock = page.getByTestId("failed-block");
  await expect(failedBlock).toContainText("Hubo un problema de nuestro lado");
  const retry = page.getByTestId("retry-indexing");
  await expect(retry).toBeDisabled();
  await expect(retry).toHaveText(/Reintentar en 0:0\d/);

  // 2. The countdown reaches the server's retry_available_at and enables.
  await expect(retry).toBeEnabled({ timeout: 10_000 });
  await expect(retry).toHaveText("Reintentar");

  // 3. Click → POST /retry-indexing → the page flips back to processing.
  await retry.click();
  await expect(page.getByTestId("indexing-block")).toBeVisible({
    timeout: 15_000,
  });

  // 4. Processing completes; the page unblocks into the editar form.
  await expect(page.getByLabel("Título")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Título")).toHaveValue("Mi tesis");
});

test("a system failure past the retry limit offers no Reintentar", async ({
  page,
}) => {
  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) =>
    route.fulfill(
      json({
        ...draftBody("failed", null),
        retry_remaining: 0,
      }),
    ),
  );

  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  const failedBlock = page.getByTestId("failed-block");
  await expect(failedBlock).toContainText(
    "se alcanzó el límite de reintentos",
  );
  await expect(page.getByTestId("retry-indexing")).toHaveCount(0);
  // Eliminar remains the way out.
  await expect(
    failedBlock.getByRole("button", { name: "Eliminar" }),
  ).toBeVisible();
});
