"use client";

import { toast } from "sonner";

import { AlertTriangle, FileText } from "lucide-react";

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
    <section className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-3 px-[18px] py-4">
        <h2 className="text-[19px] font-semibold tracking-tight">Adjuntos</h2>
      </div>
      <div className="px-[18px] pb-[18px]">
        {attachments.length === 0 ? (
          <p className="text-muted-foreground mb-3.5 text-sm">Sin adjuntos</p>
        ) : (
          <ul className="mb-3.5 flex flex-col gap-2 text-sm">
            {attachments.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5 transition hover:bg-neutral-50"
              >
                <div className="grid size-9 place-items-center rounded-md bg-primary-tint text-primary">
                  <FileText className="size-4" strokeWidth={1.8} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">
                    {a.original_filename}
                  </div>
                  <div className="text-muted-foreground text-[11px]">
                    {formatBytes(a.size_bytes)}
                  </div>
                </div>
                {canManage && (
                  <button
                    type="button"
                    aria-label={`Quitar ${a.original_filename}`}
                    className="text-muted-foreground hover:text-foreground text-sm"
                    onClick={() => onRemove(a)}
                  >
                    Quitar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {canManage && (
          <>
            <Button asChild variant="outline" size="sm" disabled={atCapacity}>
              <label
                className={
                  atCapacity
                    ? "pointer-events-none opacity-50"
                    : "cursor-pointer"
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
              <div className="text-muted-foreground mt-2 flex items-center gap-1.5 text-sm">
                <AlertTriangle className="size-3.5" strokeWidth={1.9} />
                Llegaste al máximo de 5 adjuntos
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
