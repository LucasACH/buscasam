"use client";

import { useState } from "react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { useUser } from "@/lib/useUser";

import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type Reason = components["schemas"]["ReportBody"]["reason"];

const REASONS: { value: Reason; label: string }[] = [
  { value: "spam", label: "Spam" },
  { value: "contenido_inadecuado", label: "Contenido inadecuado" },
  { value: "plagio", label: "Plagio" },
  { value: "error", label: "Error en el contenido" },
];

// "Reportar" affordance on the document detail page (module map §frontend).
// Rendered only for authenticated readers — an invitado sees nothing; the
// server is the real gate (POST /reports is require_authenticated). The
// duplicate no-op is silent: a second report shows the same confirmation.
export function ReportDialog({ docId }: { docId: number }) {
  const { user } = useUser();
  const [reason, setReason] = useState<Reason | null>(null);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  async function submit() {
    if (!reason) return;
    setBusy(true);
    setFailed(false);
    const { error } = await api.POST("/api/moderation/reports", {
      body: { doc_id: docId, reason },
    });
    setBusy(false);
    if (error) {
      setFailed(true);
      return;
    }
    setDone(true);
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="text-muted-foreground text-sm underline-offset-4 hover:underline"
        >
          Reportar
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-4">
        {done ? (
          <p className="text-sm">Recibimos tu reporte. Gracias.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium">¿Por qué reportás este documento?</p>
            <fieldset className="space-y-2">
              {REASONS.map((r) => (
                <label key={r.value} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="report-reason"
                    value={r.value}
                    checked={reason === r.value}
                    onChange={() => setReason(r.value)}
                  />
                  {r.label}
                </label>
              ))}
            </fieldset>
            {failed && (
              <p role="alert" className="text-destructive text-xs">
                No se pudo enviar el reporte. Reintentá.
              </p>
            )}
            <button
              type="button"
              disabled={!reason || busy}
              onClick={submit}
              className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Enviar
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
