"use client";

import { toast } from "sonner";

import {
  useCoauthors,
  type CoauthorRow,
} from "@/app/mis-trabajos/[id]/editar/useCoauthors";
import { CoauthorPicker } from "./CoauthorPicker";

const STATUS_PILL: Record<
  "pending" | "accepted" | "declined",
  { label: string; classes: string }
> = {
  pending: {
    label: "Pendiente",
    classes: "bg-status-amber-bg text-status-amber-fg",
  },
  accepted: {
    label: "Aceptado",
    classes: "bg-status-green-bg text-status-green-fg",
  },
  declined: {
    label: "Rechazado",
    classes: "bg-status-neutral-bg text-status-neutral-fg",
  },
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

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
    <section className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-3 px-[18px] py-4">
        <h2 className="text-[19px] font-semibold tracking-tight">Coautores</h2>
      </div>
      <div className="px-[18px] pb-[18px]">
        <ul className="mb-4 divide-y divide-border rounded-lg border border-border text-sm">
          {rows.map((row) => (
            <li
              key={`${row.user_id ?? "ext"}-${row.display_name}`}
              className="flex items-center gap-3 px-3.5 py-3"
            >
              <span className="grid size-[30px] flex-none place-items-center rounded-full bg-primary-tint text-xs font-medium text-primary">
                {initials(row.display_name)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-medium">
                  {row.display_name}
                  {row.status === "owner" && (
                    <span className="text-muted-foreground font-normal">
                      {" · "}
                      <span className="text-xs">Vos</span>
                    </span>
                  )}
                </div>
                {row.email_local && (
                  <div className="text-muted-foreground mt-0.5 text-[11px]">
                    @{row.email_local}
                  </div>
                )}
              </div>
              {row.status !== "owner" && row.status !== "external" && (
                <span
                  className={`inline-flex h-[22px] items-center rounded-full px-[9px] text-xs font-medium whitespace-nowrap ${STATUS_PILL[row.status].classes}`}
                  data-testid={`status-${row.user_id}`}
                >
                  {STATUS_PILL[row.status].label}
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
            </li>
          ))}
        </ul>
        <CoauthorPicker value={[]} onChange={onPick} label="Invitar coautor" />
      </div>
    </section>
  );
}
