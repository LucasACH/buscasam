"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ChevronLeft,
  Download,
  Eye,
  EyeOff,
  FileText,
  FileX,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAreaLabel } from "@/components/AreaField";
import { useUser } from "@/lib/useUser";
import { useInspect, type ActionError, type InspectMetadata } from "./useInspect";

// Reporter-chosen categories (document_reports.reason), shown so the moderator
// sees why the document was reported. Distinct from the moderator's free-text
// "Motivo" note below.
const REASON_LABELS: Record<string, string> = {
  spam: "Spam",
  contenido_inadecuado: "Contenido inadecuado",
  plagio: "Plagio",
  error: "Error en el contenido",
};

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
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <Button
        asChild
        variant="ghost"
        size="sm"
        className="text-muted-foreground -ml-2 mb-4"
      >
        <Link href="/moderacion">
          <ChevronLeft size={15} /> Volver a Moderación
        </Link>
      </Button>

      <h1 className="text-[28px] font-semibold tracking-tight">
        {metadata.titulo}
      </h1>

      <div className="border-border bg-card mt-6 rounded-lg border p-5">
        <dl className="space-y-3 text-sm">
          <Meta label="Tipo">{metadata.tipo}</Meta>
          <Meta label="Área">
            <AreaLabel areaPath={metadata.area_path} />
          </Meta>
          <Meta label="Autores">
            {metadata.autores.map((a) => a.display_name).join(", ")}
          </Meta>
          <Meta label="Palabras clave">
            {metadata.palabras_clave.join(", ")}
          </Meta>
          <Meta label="Reportado por">
            {(metadata.report_reasons ?? [])
              .map((r) => REASON_LABELS[r] ?? r)
              .join(", ")}
          </Meta>
        </dl>
      </div>

      <h2 className="mt-7 mb-2.5 text-[19px] font-semibold tracking-tight">
        Resumen
      </h2>
      <p className="text-neutral-700 text-[15px] leading-relaxed">
        {metadata.abstract}
      </p>

      <a
        href={`/api/moderation/reports/${reportId}/download`}
        className="border-border bg-card hover:bg-neutral-50 mt-5 flex max-w-[360px] items-center gap-3 rounded-lg border p-3 transition-colors"
      >
        <span className="bg-muted text-muted-foreground grid size-9 shrink-0 place-items-center rounded-lg">
          <FileText size={18} strokeWidth={1.8} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">Descargar archivo</span>
          <span className="text-muted-foreground mt-0.5 block text-xs">
            PDF
          </span>
        </span>
        <Download size={16} className="text-muted-foreground shrink-0" />
      </a>

      <hr className="border-border my-8" />

      <div className="border-border bg-neutral-50 rounded-lg border p-5">
        <h2 className="text-[19px] font-semibold tracking-tight">
          Resolver reporte
        </h2>
        <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
          Se le notificará al autor con el motivo que escribas a continuación.
        </p>

        <div className="mt-4 space-y-2">
          <label htmlFor="motivo" className="text-sm font-medium">
            Motivo
          </label>
          <textarea
            id="motivo"
            className="border-border bg-background w-full rounded-lg border px-3 py-2 text-sm"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Explicá brevemente la decisión (visible para el autor)…"
          />
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            variant="destructive"
            disabled={pending}
            onClick={() => run(hide)}
            className="bg-destructive border-transparent text-white hover:bg-[#b91c1c]"
          >
            <EyeOff size={14} strokeWidth={1.9} /> Ocultar
          </Button>
          <Button variant="outline" disabled={pending} onClick={() => run(unhide)}>
            <Eye size={14} strokeWidth={1.9} /> Mostrar
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
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="border-border bg-card rounded-lg border px-6 py-16">
        <div className="mx-auto flex max-w-[340px] flex-col items-center text-center">
          <div className="border-border bg-neutral-100 text-muted-foreground/70 grid size-12 place-items-center rounded-lg border">
            <FileX size={22} strokeWidth={1.8} />
          </div>
          <p className="mt-4 text-base font-semibold">
            No se pudo cargar el reporte
          </p>
          <p className="text-muted-foreground mt-1 text-sm">
            El reporte puede haber sido resuelto por otro moderador o ya no está
            disponible.
          </p>
        </div>
      </div>
    </main>
  );
}

function AreaLabel({ areaPath }: { areaPath: string }) {
  return <>{useAreaLabel(areaPath)}</>;
}

function Meta({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <dt className="text-muted-foreground w-[110px] shrink-0">{label}</dt>
      <dd className="text-foreground min-w-0 flex-1">{children}</dd>
    </div>
  );
}
