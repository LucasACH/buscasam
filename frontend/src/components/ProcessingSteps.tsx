"use client";

import { Loader2 } from "lucide-react";

// Honest checkpoints emitted by the indexing worker (core/jobs). Conditional
// stages (`ocr`, `summarizing`) only ever arrive when that branch actually
// runs, so showing the *current* label — rather than a fixed pipeline — never
// advertises a step that won't happen. `step`/TOTAL_STEPS drive the bar fill;
// `ready` is the implicit final step.
const STAGE_STEPS: Record<string, { label: string; step: number }> = {
  reading: { label: "Leyendo el documento", step: 1 },
  ocr: { label: "Reconociendo texto (puede tardar varios minutos)", step: 1 },
  summarizing: { label: "Generando resumen y palabras clave", step: 2 },
  analyzing: { label: "Analizando contenido", step: 2 },
  indexing: { label: "Preparando la búsqueda", step: 3 },
};
const TOTAL_STEPS = 4;

export function ProcessingSteps({ stage }: { stage: string | null }) {
  const current = stage ? STAGE_STEPS[stage] : undefined;
  // Before the worker claims the row (pending/queued) there is no stage yet;
  // show the first step so the bar never starts empty.
  const step = current?.step ?? 1;
  const label = current?.label ?? "En cola";
  const pct = Math.round((step / TOTAL_STEPS) * 100);

  return (
    <div data-testid="processing-steps" className="w-full max-w-md space-y-2">
      <div className="flex items-center gap-2">
        <Loader2 className="text-muted-foreground h-4 w-4 shrink-0 animate-spin" />
        <span className="text-sm">{label}</span>
      </div>
      <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
        <div
          className="bg-primary h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
