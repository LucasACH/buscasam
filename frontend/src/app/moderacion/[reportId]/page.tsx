"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useUser } from "@/lib/useUser";
import { useInspect, type ActionError, type InspectMetadata } from "./useInspect";

export default function InspectPage() {
  const { user, isInvitado, isLoading } = useUser();
  const router = useRouter();
  const params = useParams<{ reportId: string }>();
  const reportId = Number(params.reportId);
  const isDocente = user?.role === "docente";
  const { metadata, isLoading: inspectLoading, isError, hide, unhide, dismiss } =
    useInspect(reportId, isDocente && !Number.isNaN(reportId));

  useEffect(() => {
    if (isInvitado) {
      router.replace(`/login?next=/moderacion/${reportId}`);
    } else if (user && user.role !== "docente") {
      router.replace("/");
    }
  }, [isInvitado, user, router, reportId]);

  if (isLoading || isInvitado) return null;
  if (!user || user.role !== "docente") return null;
  if (inspectLoading) return null;
  if (isError || !metadata) return <NotFound />;

  return (
    <InspectView
      reportId={reportId}
      metadata={metadata}
      hide={hide}
      unhide={unhide}
      dismiss={dismiss}
    />
  );
}

type Action = (reason: string) => Promise<ActionError | undefined>;

function InspectView({
  reportId,
  metadata,
  hide,
  unhide,
  dismiss,
}: {
  reportId: number;
  metadata: InspectMetadata;
  hide: Action;
  unhide: Action;
  dismiss: Action;
}) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  async function run(action: Action) {
    setPending(true);
    // finally re-enables the buttons (their disabled state doubles as the
    // double-click guard) so a thrown action never leaves the user stuck.
    try {
      const error = await action(reason);
      if (error) {
        toast.error("No se pudo aplicar la acción");
        return;
      }
      router.push("/moderacion");
    } catch {
      toast.error("No se pudo aplicar la acción");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        {metadata.titulo}
      </h1>

      <dl className="mt-8 space-y-4 text-sm">
        <Meta label="Tipo">{metadata.tipo}</Meta>
        <Meta label="Área">{metadata.area_path}</Meta>
        <Meta label="Autores">
          {metadata.autores.map((a) => a.display_name).join(", ")}
        </Meta>
        <Meta label="Palabras clave">
          {metadata.palabras_clave.join(", ")}
        </Meta>
        <Meta label="Resumen">{metadata.abstract}</Meta>
      </dl>

      <a
        href={`/api/moderation/reports/${reportId}/download`}
        className="mt-6 inline-block text-sm underline"
      >
        Descargar archivo
      </a>

      <div className="mt-8 space-y-3 border-t pt-8">
        <label htmlFor="motivo" className="text-sm font-medium">
          Motivo
        </label>
        <textarea
          id="motivo"
          className="w-full rounded-md border px-3 py-2 text-sm"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <div className="flex gap-2">
          <Button
            variant="destructive"
            disabled={pending || reason.trim() === ""}
            onClick={() => run(hide)}
          >
            Ocultar
          </Button>
          <Button variant="outline" disabled={pending} onClick={() => run(unhide)}>
            Mostrar
          </Button>
          <Button variant="ghost" disabled={pending} onClick={() => run(dismiss)}>
            Descartar
          </Button>
        </div>
      </div>
    </main>
  );
}

function NotFound() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <p className="text-muted-foreground text-sm">
        No se pudo cargar el reporte
      </p>
    </main>
  );
}

function Meta({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
