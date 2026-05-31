"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

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
// duplicate no-op is silent: a second report shows the same toast.
export function ReportDialog({ docId }: { docId: number }) {
  const { user } = useUser();
  const [reason, setReason] = useState<Reason | null>(null);
  const [open, setOpen] = useState(false);
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
    setOpen(false);
    setReason(null);
    toast.success("Recibimos tu reporte. Gracias.");
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 self-start text-sm transition-colors"
        >
          <AlertTriangle size={14} />
          Reportar
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-72 rounded-[14px] p-4 shadow-[0_8px_30px_-8px_rgba(23,23,23,0.18)]"
      >
        <div className="space-y-3">
          <p className="text-sm font-medium">¿Por qué reportás este documento?</p>
          <fieldset className="space-y-2.5">
            {REASONS.map((r) => (
              <label
                key={r.value}
                className="flex items-center gap-2.5 text-sm"
              >
                <input
                  type="radio"
                  name="report-reason"
                  value={r.value}
                  checked={reason === r.value}
                  onChange={() => setReason(r.value)}
                  className="accent-primary size-4"
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
            className="bg-primary text-primary-foreground hover:bg-primary-hover h-9 w-full rounded-lg px-3 text-sm font-medium transition-colors disabled:opacity-50"
          >
            Enviar
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
