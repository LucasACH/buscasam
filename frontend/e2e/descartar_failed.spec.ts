import { expect, test } from "@playwright/test";

// Issue #59 tracer: an author whose replacement candidate failed processing
// clicks Descartar. The panel returns to the no-candidate state and the
// Reemplazar affordance is re-enabled. Driven through page.route — DELETE
// /candidate advances a small state machine the next draft poll reflects.

const DOC_ID = 88;
const USER = {
  user_id: 7,
  role: "estudiante",
  name: "Ada Lovelace",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

type Phase = "failed" | "discarded";

test("descartar a failed candidate returns the panel to the no-candidate state", async ({
  page,
}) => {
  let phase: Phase = "failed";

  const failedCandidate = {
    status: "failed",
    staged_abstract: "Resumen publicado",
    staged_keywords: ["bd", "sql"],
    staged_fecha: "2024-03-01",
    can_publish: false,
    can_discard: true,
    indexed_at: null,
    error: "No se pudo extraer el texto",
  };

  function draftBody() {
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
      versions: [
        {
          n: 1,
          original_filename: "original.pdf",
          mime: "application/pdf",
          size_bytes: 2048,
          indexed_at: "2024-03-01T00:00:00Z",
          is_current: true,
        },
      ],
      candidate: phase === "failed" ? failedCandidate : null,
    };
  }

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );
  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) =>
    route.fulfill(json(draftBody())),
  );
  await page.route(`**/api/documents/${DOC_ID}/candidate`, (route) => {
    phase = "discarded";
    return route.fulfill({ status: 204, body: "" });
  });

  // 1. Land on the editar page; the candidate is in the failed state.
  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  const panel = page.locator("section").filter({ hasText: "Archivo principal" });
  await expect(panel.getByTestId("candidate-status-pill")).toHaveText(
    "Falló el procesamiento",
  );
  await expect(panel.getByTestId("candidate-error")).toHaveText(
    "No se pudo extraer el texto",
  );

  // 2. Descartar.
  await panel.getByRole("button", { name: "Descartar" }).click();

  // 3. Panel returns to the no-candidate state: Reemplazar enabled + helper line.
  const reemplazar = panel.getByLabel("Reemplazar archivo principal");
  await expect(reemplazar).toBeAttached({ timeout: 15_000 });
  await expect(reemplazar).toBeEnabled();
  await expect(
    panel.getByText(
      "La versión previa permanece pública hasta que publiques la nueva.",
    ),
  ).toBeVisible();
  // The failed candidate's pill is gone.
  await expect(panel.getByTestId("candidate-status-pill")).toHaveCount(0);
});
