"use client";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type {
  AttachmentMutationError,
  DraftAttachment,
  DraftWorkspaceActions,
} from "@/app/mis-trabajos/useDraftState";
import { formatBytes } from "@/lib/utils";

const ACCEPT = ".csv,.json,.txt,.py,.ipynb,.png,.jpg,.jpeg,.gif,.zip";
const MAX_ATTACHMENTS = 5;

export function AttachmentsPanel({
  canManage,
  attachments,
  actions,
}: {
  canManage: boolean;
  attachments: DraftAttachment[];
  actions: DraftWorkspaceActions["attachments"];
}) {
  const atCapacity = attachments.length >= MAX_ATTACHMENTS;

  async function onAdd(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset so picking the same file again re-fires onChange.
    event.target.value = "";
    if (!file) return;

    const error = await actions.add(file);
    if (error === "too_large") {
      toast.error("Este adjunto pasa los 20 MB. Probá uno más chico.");
      return;
    }
    if (error === "unsupported_type") {
      toast.error("Ese tipo de archivo no se permite como adjunto.");
      return;
    }
    if (error === "upload_failed") {
      toast.error("No se pudo subir el adjunto");
    }
  }

  async function onRemove(attachment: DraftAttachment) {
    const error: AttachmentMutationError | undefined =
      await actions.remove(attachment);
    if (error === "remove_failed") {
      toast.error("No se pudo quitar el adjunto");
    }
  }

  return (
    <section className="rounded-lg border p-4">
      <h2 className="text-muted-foreground text-sm font-medium">Adjuntos</h2>
      <ul className="mt-3 space-y-2 text-sm">
        {attachments.map((a) => (
          <li key={a.id} className="flex items-center justify-between gap-2">
            <span>
              {a.original_filename} · {formatBytes(a.size_bytes)}
            </span>
            {canManage && (
              <button
                type="button"
                aria-label={`Quitar ${a.original_filename}`}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => onRemove(a)}
              >
                Quitar
              </button>
            )}
          </li>
        ))}
        {attachments.length === 0 && (
          <li className="text-muted-foreground">Sin adjuntos</li>
        )}
      </ul>

      {canManage && (
        <div className="mt-3">
          <Button asChild variant="outline" size="sm" disabled={atCapacity}>
            <label
              className={
                atCapacity ? "pointer-events-none opacity-50" : "cursor-pointer"
              }
            >
              Agregar adjunto
              <input
                type="file"
                accept={ACCEPT}
                aria-label="Agregar adjunto"
                disabled={atCapacity}
                onChange={onAdd}
                className="sr-only"
              />
            </label>
          </Button>
          {atCapacity && (
            <p className="text-muted-foreground mt-2 text-sm">
              Llegaste al máximo de 5 adjuntos
            </p>
          )}
        </div>
      )}
    </section>
  );
}
