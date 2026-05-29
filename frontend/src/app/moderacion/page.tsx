"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

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
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Moderación</h1>

      {queueLoading ? null : entries.length === 0 ? (
        <p className="text-muted-foreground mt-8 text-sm">
          No hay reportes pendientes
        </p>
      ) : (
        <ul className="mt-8 divide-y rounded-md border">
          {entries.map((e) => (
            <Row key={e.doc_id} entry={e} />
          ))}
        </ul>
      )}
    </main>
  );
}

function Row({ entry }: { entry: QueueEntry }) {
  return (
    <li>
      <Link
        href={`/moderacion/${entry.report_id}`}
        className="hover:bg-muted/50 block px-4 py-3 text-sm"
      >
        <div className="font-medium">{entry.title}</div>
        <div className="text-muted-foreground mt-1 text-xs">
          {entry.reasons.join(", ")} · {entry.report_count}{" "}
          {entry.report_count === 1 ? "reporte" : "reportes"} · Último reporte el{" "}
          {new Date(entry.last_reported_at).toLocaleDateString("es-AR")}
        </div>
      </Link>
    </li>
  );
}
