"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FileText, Plus, Trash2 } from "lucide-react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { useUser } from "@/lib/useUser";
import { Button } from "@/components/ui/button";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";

type OwnDoc = components["schemas"]["OwnDocDTO"];

async function fetchOwnDocs(): Promise<OwnDoc[]> {
  const { data, error } = await api.GET("/api/me/documents");
  if (error) throw error;
  return data ?? [];
}

export default function MisTrabajosPage() {
  const { user, isInvitado, isLoading } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (isInvitado) {
      router.replace("/login?next=/mis-trabajos");
    }
  }, [isInvitado, router]);

  const { data: docs, isPending: docsPending } = useQuery({
    queryKey: ["me", "documents"],
    queryFn: fetchOwnDocs,
    enabled: !isInvitado && !isLoading,
  });

  if (isLoading || isInvitado) return null;
  if (!user) return null;

  const borradores = (docs ?? []).filter((d) => d.publication_status === "draft");
  const publicados = (docs ?? []).filter((d) => d.publication_status === "published");

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[28px] font-semibold tracking-tight">Mis trabajos</h1>
        <div className="flex items-center gap-2.5">
          <Button variant="outline" asChild>
            <Link href="/mis-trabajos/papelera">
              <Trash2 />
              Papelera
            </Link>
          </Button>
          <Button asChild>
            <Link href="/mis-trabajos/nuevo">
              <Plus />
              Nuevo trabajo
            </Link>
          </Button>
        </div>
      </div>

      <Section title="Borradores" docs={borradores} pending={docsPending} />
      <Section title="Publicados" docs={publicados} pending={docsPending} />
    </main>
  );
}

function Section({
  title,
  docs,
  pending,
}: {
  title: string;
  docs: OwnDoc[];
  pending: boolean;
}) {
  return (
    <section className="mt-9">
      <h2 className="mb-3 text-lg font-semibold tracking-tight">{title}</h2>
      {pending ? (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="divide-y divide-border">
            {[0, 1].map((i) => (
              <div key={i} className="flex items-center gap-3.5 px-4 py-3.5">
                <div className="flex-1">
                  <div className="h-3.5 w-1/2 animate-pulse rounded-sm bg-muted" />
                  <div className="mt-2 h-2.5 w-1/4 animate-pulse rounded-sm bg-muted" />
                </div>
                <div className="h-[22px] w-20 animate-pulse rounded-full bg-muted" />
              </div>
            ))}
          </div>
        </div>
      ) : docs.length === 0 ? (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <div className="grid size-12 place-items-center rounded-lg border border-border bg-neutral-100 text-muted-foreground/70">
              <FileText className="size-5" />
            </div>
            <p className="text-base font-semibold">Todavía no hay nada acá</p>
            <p className="max-w-[340px] text-sm text-muted-foreground">
              Aún no subiste ningún trabajo — empezá con Nuevo trabajo
            </p>
          </div>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <ul className="divide-y divide-border">
            {docs.map((d) => (
              <li key={d.id}>
                <DocRow doc={d} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function DocRow({ doc }: { doc: OwnDoc }) {
  const tone: BadgeTone = doc.moderation_hidden
    ? "red"
    : doc.publication_status === "published"
      ? "green"
      : "neutral";
  const label = doc.moderation_hidden
    ? "Oculto por moderación"
    : doc.publication_status === "published"
      ? "Publicado"
      : "Borrador";

  return (
    <Link
      href={`/mis-trabajos/${doc.id}/editar`}
      className="flex items-center gap-3.5 px-4 py-3.5 transition-colors hover:bg-neutral-50"
    >
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{doc.title}</div>
        {doc.published_at && (
          <div className="mt-0.5 text-[13px] text-muted-foreground">
            Publicado el {new Date(doc.published_at).toLocaleDateString("es-AR")}
          </div>
        )}
      </div>
      <StatusBadge tone={tone}>{label}</StatusBadge>
    </Link>
  );
}
