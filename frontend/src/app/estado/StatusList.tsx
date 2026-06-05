export type ServiceHealth = {
  key: string;
  name: string;
  status: string;
  detail: string | null;
};

export type Health = {
  status: string;
  services: ServiceHealth[];
};

const STATUS_META: Record<string, { label: string; dot: string }> = {
  ok: { label: "Operativo", dot: "bg-green-500" },
  degraded: { label: "Degradado", dot: "bg-yellow-500" },
  down: { label: "Caído", dot: "bg-red-500" },
  disabled: { label: "Desactivado", dot: "bg-neutral-400" },
};

const UNKNOWN = { label: "Desconocido", dot: "bg-neutral-400" };

export function statusMeta(status: string | null) {
  return status === null ? UNKNOWN : (STATUS_META[status] ?? UNKNOWN);
}

export function OverallBanner({ status }: { status: string | null }) {
  const meta = statusMeta(status);
  const label =
    status === null ? "No se pudo contactar al servicio" : meta.label;
  return (
    <div className="border-border bg-card flex items-center gap-3 rounded-lg border px-4 py-3.5">
      <span className={`size-2.5 shrink-0 rounded-full ${meta.dot}`} />
      <span className="text-base font-semibold">{label}</span>
    </div>
  );
}

export function StatusList({ services }: { services: ServiceHealth[] }) {
  return (
    <div className="border-border bg-card mt-4 overflow-hidden rounded-lg border">
      <div className="divide-border divide-y">
        {services.map((s) => {
          const meta = statusMeta(s.status);
          return (
            <div key={s.key} className="flex items-center gap-3.5 px-4 py-3.5">
              <span className={`size-2.5 shrink-0 rounded-full ${meta.dot}`} />
              <div className="flex-1">
                <p className="text-sm font-medium">{s.name}</p>
                {s.detail ? (
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    {s.detail}
                  </p>
                ) : null}
              </div>
              <span className="text-muted-foreground text-xs">
                {meta.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
