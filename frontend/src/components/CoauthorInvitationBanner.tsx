"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import {
  useCoauthorInvitation,
  type InvitationMutationError,
} from "@/lib/useCoauthorInvitation";

type Props = {
  docId: number;
  titulo: string;
  inviter: string;
  variant: "minimal" | "banner";
};

// The único visual contract for "you are pending on this document" (module map
// §components/CoauthorInvitationBanner). `variant` controls layout only:
// "minimal" is the whole page body for a privado doc the invitee cannot read;
// "banner" is a strip above the metadata of a doc they can already read.
export function CoauthorInvitationBanner({
  docId,
  titulo,
  inviter,
  variant,
}: Props) {
  const router = useRouter();
  const { accept, decline } = useCoauthorInvitation();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function run(action: (id: number) => Promise<InvitationMutationError | undefined>) {
    setBusy(true);
    setFailed(false);
    const err = await action(docId);
    setBusy(false);
    // Success or a 404 (already transitioned / revoked) both mean the server
    // truth moved: re-run the SSR fetch (accept widens to the reader view,
    // decline drops to the 404 empty state). Only a network error stays put.
    if (!err || err.kind === "gone") {
      router.refresh();
      return;
    }
    setFailed(true);
  }

  return (
    <section
      className={
        variant === "minimal"
          ? "border-border mx-auto max-w-md rounded-lg border p-5"
          : "border-border bg-muted/40 mb-6 rounded-lg border p-4"
      }
    >
      <p className="text-sm leading-relaxed">
        <span className="font-medium">{inviter}</span> te invitó como coautor en{" "}
        <span className="font-medium">«{titulo}»</span>. ¿Aceptar o rechazar?
      </p>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => run(accept)}
          className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          Aceptar
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => run(decline)}
          className="text-muted-foreground text-sm underline-offset-4 hover:underline disabled:opacity-50"
        >
          Rechazar
        </button>
      </div>
      {failed && (
        <p role="alert" className="text-destructive mt-2 text-xs">
          No se pudo completar la acción. Reintentá.
        </p>
      )}
    </section>
  );
}
