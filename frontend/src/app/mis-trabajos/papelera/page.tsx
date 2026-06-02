"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { ChevronLeft, Clock, RotateCcw, Trash2 } from "lucide-react";

import posthog from "posthog-js";

import { useUser } from "@/lib/useUser";
import { Button } from "@/components/ui/button";
import { useDeletedDocuments, type DeletedDoc } from "./useDeletedDocuments";

export default function PapeleraPage() {
  const { user, isInvitado, isLoading } = useUser();
  const router = useRouter();
  const { documents, isLoading: docsLoading, restore } = useDeletedDocuments();

  useEffect(() => {
    if (isInvitado) {
      router.replace("/login?next=/mis-trabajos/papelera");
    }
  }, [isInvitado, router]);

  if (isLoading || isInvitado) return null;
  if (!user) return null;

  async function onRestore(id: number) {
    const error = await restore(id);
    if (error) {
      toast.error("No se pudo restaurar");
      return;
    }
    posthog.capture("document_restored", { doc_id: id });
    toast.success("Trabajo restaurado");
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <Link
        href="/mis-trabajos"
        className="text-muted-foreground hover:text-foreground mb-4 -ml-1 inline-flex items-center gap-1 text-[13px]"
      >
        <ChevronLeft className="size-4" />
        Volver a Mis trabajos
      </Link>

      <div className="mb-6">
        <h1 className="text-[28px] font-semibold tracking-tight">Papelera</h1>
        <p className="text-muted-foreground mt-1.5 text-sm">
          Los trabajos eliminados se conservan 180 días antes de borrarse de
          forma permanente.
        </p>
      </div>

      {docsLoading ? (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <div className="divide-border divide-y">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3.5 px-4 py-3.5">
                <div className="flex-1">
                  <div className="bg-muted h-3.5 w-3/5 animate-pulse rounded-sm" />
                  <div className="bg-muted mt-2 h-2.5 w-2/5 animate-pulse rounded-sm" />
                </div>
                <div className="bg-muted h-7 w-24 animate-pulse rounded-md" />
              </div>
            ))}
          </div>
        </div>
      ) : documents.length === 0 ? (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <div className="border-border text-muted-foreground/70 grid size-12 place-items-center rounded-lg border bg-neutral-100">
              <Trash2 className="size-5" />
            </div>
            <p className="text-base font-semibold">La papelera está vacía</p>
            <p className="text-muted-foreground max-w-[340px] text-sm">
              Cuando elimines un trabajo, vas a poder restaurarlo desde acá
              durante 180 días.
            </p>
            <Button asChild className="mt-1">
              <Link href="/mis-trabajos">Volver a Mis trabajos</Link>
            </Button>
          </div>
        </div>
      ) : (
        <div className="border-border bg-card overflow-hidden rounded-lg border">
          <ul className="divide-border divide-y">
            {documents.map((d) => (
              <Row key={d.id} doc={d} onRestore={onRestore} />
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}

function Row({
  doc,
  onRestore,
}: {
  doc: DeletedDoc;
  onRestore: (id: number) => void;
}) {
  const near = doc.daysRemaining <= 7;
  return (
    <li className="flex items-center gap-3.5 px-4 py-3.5">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{doc.title}</div>
        <div
          className={`mt-0.5 flex items-center gap-1.5 text-[13px] ${
            near ? "text-status-amber-fg" : "text-muted-foreground"
          }`}
        >
          <Clock className="size-3.5" />
          <span>
            Se elimina en {doc.daysRemaining}{" "}
            {doc.daysRemaining === 1 ? "día" : "días"}
          </span>
        </div>
      </div>
      <button
        type="button"
        onClick={() => onRestore(doc.id)}
        className="text-primary hover:text-primary-hover inline-flex items-center gap-1 text-[11px] hover:underline"
      >
        <RotateCcw className="size-3" />
        Restaurar
      </button>
    </li>
  );
}
