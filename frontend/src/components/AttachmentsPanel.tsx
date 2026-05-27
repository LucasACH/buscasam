"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  draftQueryKey,
  useDraftState,
  type DraftStateDTO,
} from "@/app/mis-trabajos/useDraftState";

type Attachment = DraftStateDTO["attachments"][number];

const MAX_ATTACHMENTS = 5;
const ACCEPT = ".csv,.json,.txt,.py,.ipynb,.png,.jpg,.jpeg,.gif,.zip";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`;
}

export function AttachmentsPanel({
  docId,
  canManage,
}: {
  docId: number;
  canManage: boolean;
}) {
  const { state } = useDraftState(docId);
  const queryClient = useQueryClient();
  const attachments = state?.attachments ?? [];

  function setAttachments(next: Attachment[]) {
    queryClient.setQueryData<DraftStateDTO>(draftQueryKey(docId), (old) =>
      old ? { ...old, attachments: next } : old,
    );
  }

  async function onAdd(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset so picking the same file again re-fires onChange.
    event.target.value = "";
    if (!file) return;

    // Raw fetch + FormData: the generated body type is a binary placeholder
    // (`{ file: string }`), not assignable from a runtime File — same reason
    // the /nuevo upload bypasses the typed client.
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`/api/documents/${docId}/attachments`, {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    if (resp.status === 413) {
      toast.error("Este adjunto pasa los 20 MB. Probá uno más chico.");
      return;
    }
    if (resp.status === 415) {
      toast.error("Ese tipo de archivo no se permite como adjunto.");
      return;
    }
    if (resp.status !== 201) {
      toast.error("No se pudo subir el adjunto");
      return;
    }
    const created = (await resp.json()) as Attachment;
    setAttachments([...attachments, created]);
  }

  async function onRemove(att: Attachment) {
    const previous = attachments;
    setAttachments(attachments.filter((a) => a.id !== att.id));
    const { error } = await api.DELETE(
      "/api/documents/{doc_id}/attachments/{att_id}",
      { params: { path: { doc_id: docId, att_id: att.id } } },
    );
    if (error) {
      setAttachments(previous);
      toast.error("No se pudo quitar el adjunto");
    }
  }

  const atCap = attachments.length >= MAX_ATTACHMENTS;

  return (
    <section className="rounded-lg border p-4">
      <h2 className="text-sm font-medium text-muted-foreground">Adjuntos</h2>
      <ul className="mt-3 space-y-2 text-sm">
        {attachments.map((a) => (
          <li key={a.id} className="flex items-center justify-between gap-2">
            <span>
              {a.original_filename} · {formatSize(a.size_bytes)}
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
          <Button asChild variant="outline" size="sm" disabled={atCap}>
            <label className={atCap ? "pointer-events-none opacity-50" : "cursor-pointer"}>
              Agregar adjunto
              <input
                type="file"
                accept={ACCEPT}
                aria-label="Agregar adjunto"
                disabled={atCap}
                onChange={onAdd}
                className="sr-only"
              />
            </label>
          </Button>
          {atCap && (
            <p className="mt-2 text-sm text-muted-foreground">
              Llegaste al máximo de 5 adjuntos
            </p>
          )}
        </div>
      )}
    </section>
  );
}
