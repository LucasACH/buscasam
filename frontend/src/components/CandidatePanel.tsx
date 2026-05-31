"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ProcessingSteps } from "@/components/ProcessingSteps";
import { TONE_CLASSES, type BadgeTone } from "@/components/StatusBadge";
import type {
  Candidate,
  DraftWorkspaceActions,
  ReplaceMutationError,
} from "@/app/mis-trabajos/useDraftState";

const ACCEPT = ".pdf,.docx,.odt";
const HELPER =
  "La versión previa permanece pública hasta que publiques la nueva.";

const REPLACE_ERROR_COPY: Record<ReplaceMutationError, string> = {
  too_large: "Este archivo supera los 50 MB",
  unsupported_type: "Formato no soportado o PDF cifrado",
  no_published_version: "El documento aún no tiene una versión publicada",
  replace_failed: "No se pudo reemplazar el archivo",
};

export function CandidatePanel({
  candidate,
  actions,
}: {
  candidate: Candidate | null;
  actions: Pick<DraftWorkspaceActions, "publish" | "replace" | "discard">;
}) {
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);

  async function onDiscard() {
    setDiscarding(true);
    try {
      const err = await actions.discard();
      if (err) toast.error("No se pudo descartar");
    } finally {
      setDiscarding(false);
    }
  }

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset so re-picking the same file fires onChange again.
    event.target.value = "";
    if (!file) return;
    setError(null);
    const err = await actions.replace(file);
    if (err) setError(REPLACE_ERROR_COPY[err]);
  }

  async function onPublish() {
    setPublishing(true);
    try {
      const result = await actions.publish();
      if (result === "publish_failed") {
        toast.error("No se pudo publicar");
      }
    } catch {
      toast.error("No se pudo publicar");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-3 px-[18px] py-4">
        <h2 className="text-[19px] font-semibold tracking-tight">
          Archivo principal
        </h2>
      </div>
      <div className="px-[18px] pb-[18px]">
        {error && (
          <p
            data-testid="replace-error"
            className="text-destructive mb-3 flex items-center gap-1.5 text-[13px]"
          >
            {error}
          </p>
        )}

        {candidate === null && (
          <div className="space-y-3">
            <p className="text-muted-foreground text-sm leading-relaxed">
              {HELPER}
            </p>
            <ReplaceButton
              label="Reemplazar archivo principal"
              onPick={onPick}
            />
          </div>
        )}

        {candidate?.status === "processing" && (
          <div className="space-y-4">
            <ProcessingSteps stage={candidate.stage} />
            <div className="flex flex-wrap gap-2">
              <ReplaceButton label="Reemplazar" onPick={onPick} />
              {candidate.canDiscard && (
                <DiscardButton onClick={onDiscard} disabled={discarding} />
              )}
            </div>
          </div>
        )}

        {candidate?.status === "ready" && (
          <div className="space-y-3.5">
            <StatusPill tone="green">{candidate.statusLabel}</StatusPill>
            <div className="rounded-lg border border-border bg-neutral-50 p-3.5">
              <div className="text-muted-foreground mb-2.5 text-[11px] font-semibold tracking-[0.05em] uppercase">
                Metadatos detectados
              </div>
              <dl className="grid grid-cols-[110px_1fr] gap-x-4 gap-y-2.5 text-sm">
                <Staged label="Resumen">
                  {candidate.stagedAbstract || "—"}
                </Staged>
                <Staged label="Palabras clave">
                  {candidate.stagedKeywords.join(", ") || "—"}
                </Staged>
                <Staged label="Fecha">{candidate.stagedFecha || "—"}</Staged>
              </dl>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={!candidate.canPublish || publishing}
                onClick={onPublish}
              >
                Publicar
              </Button>
              {candidate.canDiscard && (
                <DiscardButton onClick={onDiscard} disabled={discarding} />
              )}
            </div>
          </div>
        )}

        {candidate?.status === "failed" && (
          <div className="space-y-3">
            <StatusPill tone="red">{candidate.statusLabel}</StatusPill>
            {candidate.error && (
              <p
                data-testid="candidate-error"
                className="text-destructive text-sm"
              >
                {candidate.error}
              </p>
            )}
            {candidate.canDiscard && (
              <DiscardButton onClick={onDiscard} disabled={discarding} />
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function DiscardButton({
  onClick,
  disabled,
}: {
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={disabled}>
      Descartar
    </Button>
  );
}

function ReplaceButton({
  label,
  onPick,
}: {
  label: string;
  onPick: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <Button asChild variant="outline" size="sm">
      <label className="cursor-pointer">
        {label}
        <input
          type="file"
          accept={ACCEPT}
          aria-label={label}
          onChange={onPick}
          className="sr-only"
        />
      </label>
    </Button>
  );
}

function StatusPill({
  tone,
  children,
}: {
  tone: BadgeTone;
  children: React.ReactNode;
}) {
  return (
    <span
      data-testid="candidate-status-pill"
      className={`inline-flex h-[22px] items-center gap-1 rounded-full px-[9px] text-xs font-medium whitespace-nowrap ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

function Staged({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-neutral-700">{children}</dd>
    </>
  );
}
