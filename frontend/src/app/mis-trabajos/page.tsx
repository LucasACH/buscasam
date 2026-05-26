"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { useUser } from "@/lib/useUser";

export default function MisTrabajosPage() {
  const { user, isInvitado, isLoading } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (isInvitado) {
      router.replace("/login?next=/mis-trabajos");
    }
  }, [isInvitado, router]);

  if (isLoading || isInvitado) return null;
  if (!user) return null;

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

      <Section title="Borradores" />
      <Section title="Publicados" />
    </main>
  );
}

function Section({ title }: { title: string }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-medium">{title}</h2>
      <p className="text-muted-foreground mt-4 text-sm">
        Aún no subiste ningún trabajo — empezá con Nuevo trabajo
      </p>
    </section>
  );
}
