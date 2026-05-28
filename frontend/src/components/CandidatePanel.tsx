"use client";

import { useState } from "react";
import { toast } from "sonner";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  useDraftState,
  type ReplaceMutationError,
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
  docId,
  canPublish,
}: {
  docId: number;
  canPublish: boolean;
}) {
  const { state, replace, refresh } = useDraftState(docId);
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);

  if (!state) return null;
  const candidate = state.candidate;

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset so re-picking the same file fires onChange again.
    event.target.value = "";
    if (!file) return;
    setError(null);
    const err = await replace(file);
    if (err) setError(REPLACE_ERROR_COPY[err]);
  }

  async function onPublish() {
    setPublishing(true);
    try {
      const { error: pubErr, response } = await api.POST(
        "/api/documents/{doc_id}/publish",
        { params: { path: { doc_id: docId } } },
      );
      if (pubErr) {
        // 409 is a publish-gate race: refetch so the next poll re-renders the
        // gate (server is source of truth). Same path as the editar form.
        if (response?.status === 409) {
          await refresh();
          return;
        }
        toast.error("No se pudo publicar");
        return;
      }
      await refresh();
    } catch {
      toast.error("No se pudo publicar");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <section className="rounded-lg border p-4">
      <h2 className="text-muted-foreground text-sm font-medium">
        Archivo principal
      </h2>
      {error && (
        <p data-testid="replace-error" className="text-destructive mt-2 text-sm">
          {error}
        </p>
      )}

      {candidate === null && (
        <div className="mt-3 space-y-2">
          <ReplaceButton label="Reemplazar archivo principal" onPick={onPick} />
          <p className="text-muted-foreground text-sm">{HELPER}</p>
        </div>
      )}

      {candidate?.status === "processing" && (
        <div className="mt-3 space-y-2">
          <StatusPill>{candidate.statusLabel}</StatusPill>
          <ReplaceButton label="Reemplazar" onPick={onPick} />
        </div>
      )}

      {candidate?.status === "ready" && (
        <div className="mt-3 space-y-3">
          <StatusPill>{candidate.statusLabel}</StatusPill>
          <dl className="space-y-2 text-sm">
            <Staged label="Resumen">{candidate.stagedAbstract || "—"}</Staged>
            <Staged label="Palabras clave">
              {candidate.stagedKeywords.join(", ") || "—"}
            </Staged>
            <Staged label="Fecha">{candidate.stagedFecha || "—"}</Staged>
          </dl>
          <Button
            disabled={!(canPublish && candidate.canPublish) || publishing}
            onClick={onPublish}
          >
            Publicar
          </Button>
        </div>
      )}

      {candidate?.status === "failed" && (
        <div className="mt-3 space-y-2">
          <StatusPill>{candidate.statusLabel}</StatusPill>
          {candidate.error && (
            <p
              data-testid="candidate-error"
              className="text-destructive text-sm"
            >
              {candidate.error}
            </p>
          )}
        </div>
      )}
    </section>
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

function StatusPill({ children }: { children: React.ReactNode }) {
  return (
    <span
      data-testid="candidate-status-pill"
      className="bg-muted inline-block rounded-full px-3 py-1 text-sm"
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
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
