"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, ShieldCheck } from "lucide-react";

import { useUser } from "@/lib/useUser";
import { useQueue, type QueueEntry } from "./useQueue";

export default function ModeracionPage() {
  const { user, isInvitado, isLoading } = useUser();
  const router = useRouter();
  const isDocente = user?.role === "docente";
  const { entries, isLoading: queueLoading } = useQueue(isDocente);

  useEffect(() => {
    if (isInvitado) {
      router.replace("/login?next=/moderacion");
    } else if (user && user.role !== "docente") {
      router.replace("/");
    }
  }, [isInvitado, user, router]);

  if (isLoading || isInvitado) return null;
  if (!user || user.role !== "docente") return null;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-[28px] font-semibold tracking-tight">Moderación</h1>
        <p className="text-muted-foreground mt-1.5 text-sm leading-relaxed">
          Trabajos reportados por la comunidad. Revisá cada caso antes de
          actuar.
        </p>
      </div>

      {queueLoading ? (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <div className="divide-border divide-y">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-start gap-3.5 px-4 py-3.5">
                <div className="bg-muted size-10 shrink-0 animate-pulse rounded-lg" />
                <div className="flex-1 space-y-2 pt-0.5">
                  <div className="bg-muted h-3 w-4/5 animate-pulse rounded-sm" />
                  <div className="bg-muted h-2.5 w-1/2 animate-pulse rounded-sm" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : entries.length === 0 ? (
        <div className="border-border bg-card rounded-lg border px-6 py-16">
          <div className="mx-auto flex max-w-[340px] flex-col items-center text-center">
            <div className="border-border bg-neutral-100 text-muted-foreground/70 grid size-12 place-items-center rounded-lg border">
              <ShieldCheck size={22} strokeWidth={1.8} />
            </div>
            <p className="mt-4 text-base font-semibold">
              No hay reportes pendientes
            </p>
            <p className="text-muted-foreground mt-1 text-sm">
              Cuando la comunidad reporte un trabajo, vas a verlo acá para
              revisarlo.
            </p>
          </div>
        </div>
      ) : (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <ul className="divide-border divide-y">
            {entries.map((e) => (
              <Row key={e.doc_id} entry={e} />
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}

function Row({ entry }: { entry: QueueEntry }) {
  const high = entry.report_count >= 5;
  return (
    <li>
      <Link
        href={`/moderacion/${entry.report_id}`}
        className="hover:bg-neutral-50 flex items-start gap-3.5 px-4 py-3.5 transition-colors"
      >
        <span
          className={
            "mt-0.5 grid h-10 min-w-10 shrink-0 place-items-center rounded-lg border px-2 " +
            (high
              ? "bg-status-red-bg text-status-red-fg border-[#fca5a5]"
              : "bg-neutral-100 text-muted-foreground border-border")
          }
        >
          <span className="font-mono text-base leading-none font-bold">
            {entry.report_count}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <div className="text-foreground line-clamp-2 text-sm font-semibold tracking-tight">
            {entry.title}
          </div>
          <div className="text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
            {entry.reasons.join(", ")}
            <span className="text-muted-foreground/50">·</span>
            <span
              className={
                high ? "text-status-red-fg font-semibold" : undefined
              }
            >
              {entry.report_count}{" "}
              {entry.report_count === 1 ? "reporte" : "reportes"}
            </span>
            <span className="text-muted-foreground/50">·</span>
            <span>
              Último reporte el{" "}
              {new Date(entry.last_reported_at).toLocaleDateString("es-AR")}
            </span>
          </div>
        </div>

        <ChevronRight
          size={16}
          className="text-muted-foreground/50 mt-2.5 shrink-0"
        />
      </Link>
    </li>
  );
}
