"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { useUser } from "@/lib/useUser";

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
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Mis trabajos</h1>
        <Link
          href="/mis-trabajos/nuevo"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          Nuevo trabajo
        </Link>
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
    <section className="mt-8">
      <h2 className="text-lg font-medium">{title}</h2>
      {pending ? null : docs.length === 0 ? (
        <p className="text-muted-foreground mt-4 text-sm">
          Aún no subiste ningún trabajo — empezá con Nuevo trabajo
        </p>
      ) : (
        <ul className="mt-4 divide-y rounded-md border">
          {docs.map((d) => (
            <li key={d.id}>
              <Link
                href={`/mis-trabajos/${d.id}/editar`}
                className="block px-4 py-3 text-sm hover:bg-muted"
              >
                {d.title}
                {d.published_at && (
                  <span className="text-muted-foreground ml-2 text-xs">
                    Publicado el {new Date(d.published_at).toLocaleDateString("es-AR")}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
