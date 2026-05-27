import { expect, test } from "@playwright/test";

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

// Editing título on /editar/{id} triggers a `Reindexando título…` gate; the
// badge clears once the (mocked) headline reindex completes.
test("editar título: reindexing_headline gate appears, then clears", async ({ page }) => {
  const DOC_ID = 42;

  // The mocked /draft response is a simple state machine driven by PATCH:
  // - before PATCH: indexed (publish_gate_reason=null)
  // - immediately after PATCH: reindexing_headline (and stays for one poll)
  // - subsequent polls: indexed again (worker "finished" the reindex)
  let phase: "idle" | "reindexing" | "done" = "idle";
  let reindexPolls = 0;

  await page.route("**/api/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/notifications**", (route) =>
    route.fulfill(json({ items: [] })),
  );

  await page.route(`**/api/documents/${DOC_ID}/draft`, (route) => {
    if (phase === "reindexing") {
      reindexPolls += 1;
      if (reindexPolls >= 2) phase = "done";
      return route.fulfill(
        json({
          title: "Mi tesis BD (editada)",
          index_status: "indexed",
          staged_abstract: "Resumen extraído",
          staged_keywords: ["bd"],
          staged_fecha: "2024-03-01",
          index_error: null,
          publish_gate_reason: "reindexing_headline",
        }),
      );
    }
    return route.fulfill(
      json({
        title: phase === "done" ? "Mi tesis BD (editada)" : "Mi tesis BD",
        index_status: "indexed",
        staged_abstract: "Resumen extraído",
        staged_keywords: ["bd"],
        staged_fecha: "2024-03-01",
        index_error: null,
        publish_gate_reason: null,
      }),
    );
  });

  await page.route(`**/api/documents/${DOC_ID}`, async (route) => {
    if (route.request().method() === "PATCH") {
      phase = "reindexing";
      reindexPolls = 0;
      return route.fulfill({ status: 204, body: "" });
    }
    await route.fulfill({ status: 404, body: "" });
  });

  // 1. Land on /editar with indexed state — no gate reason, no badge.
  await page.goto(`/mis-trabajos/${DOC_ID}/editar`);
  await expect(page.getByTestId("status-pill")).toHaveText(/Listo para publicar/);
  await expect(page.getByTestId("gate-reason")).toHaveCount(0);

  // 2. Edit título and blur.
  const titulo = page.getByLabel("Título");
  await titulo.fill("Mi tesis BD (editada)");
  await titulo.blur();

  // 3. Reindexando título… gate appears.
  await expect(page.getByTestId("gate-reason")).toHaveText(/Reindexando título…/, {
    timeout: 10_000,
  });

  // 4. Once the (mocked) reindex finishes, the gate clears.
  await expect(page.getByTestId("gate-reason")).toHaveCount(0, { timeout: 15_000 });
});
