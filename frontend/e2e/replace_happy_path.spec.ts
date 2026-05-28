import { expect, test } from "@playwright/test";

// Issue #58 tracer: an owner replaces the main file on a published document,
// watches it process (Procesando… → Listo para publicar), publishes the
// candidate, and the Versiones panel grows to two rows. Throughout the
// pre-publish window a reader hitting /api/docs/{id} and its download endpoint
// keeps seeing the previously published file's bytes; only the Publicar click
// flips them. Driven entirely through page.route — the candidate lifecycle is a
// small state machine the mock advances on /replace, polls, and /publish.

const DOC_ID = 77;
const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

const OLD_BYTES = "PUBLISHED-ORIGINAL-BYTES";
const NEW_BYTES = "REPLACEMENT-CANDIDATE-BYTES";

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

type Phase = "none" | "processing" | "ready" | "published";

test("replace → processing → ready → publish, reader stays on old bytes until commit", async ({
  page,
}) => {
  let phase: Phase = "none";
  let processingPolls = 0;
  // The reader-visible current file. Flips only when /publish commits.
  let publishedFilename = "original.pdf";
  let publishedBytes = OLD_BYTES;

  const stagedCandidate = (status: "processing" | "ready") => ({
    status,
    staged_abstract: "Resumen publicado",
    staged_keywords: ["bd", "sql"],
    staged_fecha: "2024-03-01",
    can_publish: status === "ready",
    can_discard: true,
    indexed_at: status === "ready" ? "2024-04-01T00:00:00Z" : null,
    error: null,
  });

  const versions = () =>
    phase === "published"
      ? [
          row(1, "original.pdf", false),
          row(2, "nueva.pdf", true),
        ]
      : [row(1, "original.pdf", true)];

  function row(n: number, name: string, is_current: boolean) {
    return {
      n,
      original_filename: name,
      mime: "application/pdf",
      size_bytes: 2048,
      indexed_at: "2024-03-01T00:00:00Z",
      is_current,
    };
  }

  function draftBody() {
    let candidate = null;
    if (phase === "processing") candidate = stagedCandidate("processing");
    else if (phase === "ready") candidate = stagedCandidate("ready");
    return {
      title: "Mi trabajo publicado",
      index_status: "indexed",
      staged_abstract: "Resumen publicado",
      staged_keywords: ["bd", "sql"],
      staged_fecha: "2024-03-01",
      index_error: null,
      publish_gate_reason: null,
      is_owner: true,
      attachments: [],
      coauthors: [
        { user_id: 7, display_name: "Ada Lovelace", email_local: "ada", status: "owner" },
      ],
      versions: versions(),
      candidate,
    };
  }

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );

  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) => {
    if (phase === "processing") {
      processingPolls += 1;
      // First poll (the optimistic invalidation right after /replace) keeps it
      // processing; the next poll flips to ready.
      if (processingPolls >= 1) phase = "ready";
      return route.fulfill(json({ ...draftBody(), candidate: stagedCandidate("processing") }));
    }
    return route.fulfill(json(draftBody()));
  });

  await page.route(`**/api/documents/${DOC_ID}/replace`, (route) => {
    phase = "processing";
    processingPolls = 0;
    return route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
  });

  await page.route(`**/api/documents/${DOC_ID}/publish`, (route) => {
    phase = "published";
    publishedFilename = "nueva.pdf";
    publishedBytes = NEW_BYTES;
    return route.fulfill({ status: 204, body: "" });
  });

  // Reader surfaces — current published file, gated on the atomic publish flip.
  await page.route(`**/api/docs/${DOC_ID}`, (route) =>
    route.fulfill(
      json({
        view: "detail",
        doc_id: DOC_ID,
        titulo: "Mi trabajo publicado",
        autores: [{ display_name: "Ada Lovelace", user_id: 7 }],
        area_path: "escuela_ciencia",
        tipo: "paper",
        fecha: "2024-03-01",
        visibility: "publico",
        abstract: "Resumen publicado",
        palabras_clave: ["bd", "sql"],
        archivo_principal: {
          original_filename: publishedFilename,
          size_bytes: 2048,
          mime: "application/pdf",
        },
        adjuntos: [],
        manageable: false,
      }),
    ),
  );
  await page.route(`**/api/docs/${DOC_ID}/download`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/pdf",
      body: publishedBytes,
    }),
  );

  const readerDownload = () =>
    page.evaluate(
      (id) => fetch(`/api/docs/${id}/download`).then((r) => r.text()),
      DOC_ID,
    );
  const readerFilename = () =>
    page.evaluate(
      (id) => fetch(`/api/docs/${id}`).then((r) => r.json()).then((d) => d.archivo_principal.original_filename),
      DOC_ID,
    );

  // 1. Land on the editar page of a published doc with no candidate.
  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  const panel = page.locator("section").filter({ hasText: "Archivo principal" });
  await expect(
    panel.getByLabel("Reemplazar archivo principal"),
  ).toBeAttached();
  await expect(
    page.getByText(
      "La versión previa permanece pública hasta que publiques la nueva.",
    ),
  ).toBeVisible();

  // Reader sees the original published file before any replacement.
  expect(await readerDownload()).toBe(OLD_BYTES);
  expect(await readerFilename()).toBe("original.pdf");

  // 2. Replace the main file with a fixture.
  await panel.getByLabel("Reemplazar archivo principal").setInputFiles({
    name: "nueva.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 nueva"),
  });

  // 3. Procesando… → Listo para publicar.
  await expect(panel.getByTestId("candidate-status-pill")).toHaveText(
    "Procesando…",
    { timeout: 10_000 },
  );
  await expect(panel.getByTestId("candidate-status-pill")).toHaveText(
    "Listo para publicar",
    { timeout: 15_000 },
  );

  // Reader STILL sees the previously published bytes while the candidate is ready
  // but unpublished.
  expect(await readerDownload()).toBe(OLD_BYTES);
  expect(await readerFilename()).toBe("original.pdf");

  // 4. Owner publishes the candidate.
  await panel.getByRole("button", { name: "Publicar" }).click();

  // 5. Panel resets to the no-candidate state.
  await expect(
    panel.getByLabel("Reemplazar archivo principal"),
  ).toBeAttached({ timeout: 15_000 });

  // 6. Versiones anteriores now lists two rows, the new one marked (actual).
  const versionsPanel = page
    .locator("section")
    .filter({ hasText: "Versiones anteriores" });
  await expect(versionsPanel.getByText(/nueva\.pdf/)).toBeVisible();
  await expect(versionsPanel.getByText(/\(actual\)/)).toBeVisible();
  await expect(versionsPanel.getByText(/v1 ·/)).toBeVisible();

  // 7. Only now does the reader see the new file's bytes.
  expect(await readerDownload()).toBe(NEW_BYTES);
  expect(await readerFilename()).toBe("nueva.pdf");
});
