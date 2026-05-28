"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";

import { useUser } from "@/lib/useUser";
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
    toast.success("Trabajo restaurado");
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Papelera</h1>
        <Link href="/mis-trabajos" className="text-sm text-muted-foreground hover:underline">
          Volver a Mis trabajos
        </Link>
      </div>

      {docsLoading ? null : documents.length === 0 ? (
        <p className="text-muted-foreground mt-8 text-sm">La papelera está vacía</p>
      ) : (
        <ul className="mt-8 divide-y rounded-md border">
          {documents.map((d) => (
            <Row key={d.id} doc={d} onRestore={onRestore} />
          ))}
        </ul>
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
  return (
    <li className="flex items-center justify-between px-4 py-3 text-sm">
      <div>
        <span>{doc.title}</span>
        <span className="text-muted-foreground ml-2 text-xs">
          Se elimina en {doc.daysRemaining} {doc.daysRemaining === 1 ? "día" : "días"}
        </span>
      </div>
      <button
        type="button"
        onClick={() => onRestore(doc.id)}
        className="rounded-md border px-3 py-1 text-sm font-medium hover:bg-muted"
      >
        Restaurar
      </button>
    </li>
  );
}
