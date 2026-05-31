import { expect, test } from "@playwright/test";

// AC10: an invitee opens the bandeja, sees the coauthor-invite item with an
// inline Aceptar, clicks it, and the item transitions to its read state.
//
// The publish-time fan-out that produces the notification row is covered by the
// backend integration tests (test_jobs_fan_out_coauthor_invites,
// test_documents_publish); here every API call is route-mocked, so this spec
// isolates the new invitee-side UI: CoauthorInviteItem buttons +
// useCoauthorInvitation invalidation.
//
// Opening the bell no longer auto-marks notifications read (that would hide the
// unread-gated invite actions before the user can act); reads happen only via
// the explicit "Marcar como leída" / bulk controls.

const INVITEE = {
  user_id: 11,
  role: "estudiante",
  name: "Bob Invitee",
  picture_url: null,
  hd: "estudiantes.unsam.edu.ar",
};

const DOC_ID = 42;
const TITLE = "Redes neuronales";

function json(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

function inviteItem(read: boolean) {
  return {
    id: 1,
    kind: "coauthor_invite",
    payload: { doc_title: TITLE, inviter: "Ada Lovelace", doc_id: DOC_ID },
    read_at: read ? "2026-05-27T00:00:00Z" : null,
    created_at: "2026-05-27T00:00:00Z",
  };
}

test("invitee accepts a coauthor invite from the bandeja", async ({ page }) => {
  let accepted = false;

  await page.route("**/api/me", (route) => route.fulfill(json(INVITEE)));
  await page.route("**/api/search**", (route) =>
    route.fulfill(
      json({
        results: [],
        total: 0,
        saturated: false,
        unfiltered_total: null,
        lexical_fallback: false,
      }),
    ),
  );
  await page.route("**/api/notifications**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/unread_count"))
      return route.fulfill(json({ count: 0 }));
    if (path.endsWith("/mark_all_read"))
      return route.fulfill(json({ count: 0 }));
    return route.fulfill(json({ items: [inviteItem(accepted)] }));
  });
  await page.route(`**/api/coauthor_invitations/${DOC_ID}/accept`, (route) => {
    accepted = true;
    return route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/buscar");

  // Open the bandeja and confirm the invite renders with inline actions.
  await page.getByRole("button", { name: /Notificaciones/i }).click();
  await expect(page.getByText(TITLE)).toBeVisible();
  const aceptar = page.getByRole("button", { name: /Aceptar/i });
  await expect(aceptar).toBeVisible();
  await expect(page.getByRole("link", { name: /Ver/i })).toHaveAttribute(
    "href",
    `/docs/${DOC_ID}`,
  );

  // Accept → POST fires, the bandeja query invalidates, and the refetched item
  // comes back read, so the inline actions disappear.
  const acceptCall = page.waitForRequest(
    `**/api/coauthor_invitations/${DOC_ID}/accept`,
  );
  await aceptar.click();
  await acceptCall;

  await expect(page.getByRole("button", { name: /Aceptar/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Rechazar/i })).toHaveCount(0);
});
