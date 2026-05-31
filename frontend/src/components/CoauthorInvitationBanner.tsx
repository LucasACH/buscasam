"use client";

import { UserPlus } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
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

  if (variant === "minimal") {
    return (
      <section className="border-primary-tint-2 bg-card w-full max-w-md rounded-[14px] border p-7 text-center shadow-[0_8px_30px_-8px_rgba(23,23,23,0.18)]">
        <div className="bg-primary-tint text-primary mx-auto grid size-12 place-items-center rounded-lg">
          <UserPlus size={22} />
        </div>
        <div className="text-muted-foreground mt-4 text-[11px] font-semibold tracking-[0.06em] uppercase">
          Invitación a coautoría
        </div>
        <p className="mt-2 text-[15px] leading-relaxed">
          <span className="font-semibold">{inviter}</span> te invitó como
          coautor en <span className="font-semibold">«{titulo}»</span>. ¿Aceptar
          o rechazar?
        </p>
        <p className="text-muted-foreground mx-auto mt-2 max-w-[340px] text-sm leading-relaxed">
          Si aceptás, vas a poder ver y editar este trabajo privado.
        </p>
        <div className="mt-5 flex items-center justify-center gap-2">
          <Button
            type="button"
            disabled={busy}
            onClick={() => run(accept)}
            className="min-w-[118px]"
          >
            Aceptar
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            onClick={() => run(decline)}
          >
            Rechazar
          </Button>
        </div>
        {failed && (
          <p role="alert" className="text-destructive mt-3 text-xs">
            No se pudo completar la acción. Reintentá.
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="border-primary-tint-2 bg-primary-tint mb-6 flex flex-wrap items-center gap-4 rounded-lg border px-[18px] py-3.5">
      <span className="border-primary-tint-2 bg-card text-primary grid size-9 flex-none place-items-center rounded-md border">
        <UserPlus size={18} />
      </span>
      <div className="min-w-[220px] flex-1">
        <p className="text-neutral-700 text-sm leading-relaxed">
          <span className="text-foreground font-semibold">{inviter}</span> te
          invitó como coautor en{" "}
          <span className="text-foreground font-semibold">«{titulo}»</span>.
        </p>
        <p className="text-primary-hover mt-0.5 text-[11px] font-medium">
          ¿Aceptar o rechazar?
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={busy}
          onClick={() => run(accept)}
        >
          Aceptar
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => run(decline)}
        >
          Rechazar
        </Button>
      </div>
      {failed && (
        <p role="alert" className="text-destructive w-full text-xs">
          No se pudo completar la acción. Reintentá.
        </p>
      )}
    </section>
  );
}
