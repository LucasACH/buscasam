"use client";

import { toast } from "sonner";

import {
  useCoauthors,
  type CoauthorRow,
} from "@/app/mis-trabajos/[id]/editar/useCoauthors";
import { CoauthorPicker } from "./CoauthorPicker";

const STATUS_PILL: Record<string, string> = {
  pending: "Pendiente",
  accepted: "Aceptado",
  declined: "Rechazado",
};

const MUTATION_ERROR_COPY: Record<string, string> = {
  already_listed: "Ese coautor ya está en la lista",
  forbidden: "Solo el dueño puede gestionar coautores",
  network: "No se pudo completar la acción",
};

export function CoauthorsPanel({ docId }: { docId: number }) {
  const { isOwner, coauthors, invite, revoke } = useCoauthors(docId);

  if (!isOwner) return null;

  const rows = coauthors ?? [];
  // Filter already-listed users (any status) out of picker selections before
  // round-tripping. A 409 from a tab race is the inline-error fallback.
  const listedUserIds = new Set(
    rows.map((r) => r.user_id).filter((id): id is number => id !== null),
  );

  async function onPick(ids: number[]) {
    for (const id of ids) {
      if (listedUserIds.has(id)) continue;
      const err = await invite(id);
      if (err) toast.error(MUTATION_ERROR_COPY[err.kind]);
    }
  }

  async function onRevoke(row: CoauthorRow) {
    if (row.user_id === null) return;
    const err = await revoke(row.user_id);
    if (err) toast.error(MUTATION_ERROR_COPY[err.kind]);
  }

  return (
    <section className="rounded-lg border p-4">
      <h2 className="text-muted-foreground text-sm font-medium">Coautores</h2>
      <ul className="mt-3 space-y-2 text-sm">
        {rows.map((row) => (
          <li
            key={`${row.user_id ?? "ext"}-${row.display_name}`}
            className="flex items-center justify-between gap-2"
          >
            <span>
              {row.display_name}
              {row.email_local && ` · ${row.email_local}`}
              {row.status === "owner" && (
                <span className="text-muted-foreground ml-2 text-xs">Vos</span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {row.status !== "owner" && row.status !== "external" && (
                <span
                  className="bg-muted rounded-full px-2 py-0.5 text-xs"
                  data-testid={`status-${row.user_id}`}
                >
                  {STATUS_PILL[row.status] ?? row.status}
                </span>
              )}
              {row.status === "pending" && (
                <button
                  type="button"
                  aria-label={`Quitar ${row.display_name}`}
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => onRevoke(row)}
                >
                  Quitar
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-3">
        <CoauthorPicker value={[]} onChange={onPick} />
      </div>
    </section>
  );
}
