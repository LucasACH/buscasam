import { FileText } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CoauthorInvitationBanner } from "@/components/CoauthorInvitationBanner";
import { ReportDialog } from "@/components/ReportDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { VersionsPanel } from "@/components/VersionsPanel";
import { Button } from "@/components/ui/button";
import { TIPO_LABEL, VISIBILITY_LABEL } from "@/lib/labels";

import { fetchAreas, fetchDocDetail } from "./fetchDetail";
import { RelatedRail } from "./RelatedRail";
import type { DetailDoc, DetailWithInvitationDoc, MinimalInviteDoc } from "./types";

type PageProps = { params: Promise<{ id: string }> };

function parseDocId(raw: string): number | null {
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export async function generateMetadata({ params }: PageProps) {
  const docId = parseDocId((await params).id);
  if (docId === null) return {};
  const detail = await fetchDocDetail(docId);
  if (!detail) return {};
  return { title: detail.titulo };
}

export default async function DocDetailPage({ params }: PageProps) {
  const docId = parseDocId((await params).id);
  if (docId === null) notFound();
  const [detail, areas] = await Promise.all([
    fetchDocDetail(docId),
    fetchAreas(),
  ]);
  if (!detail) notFound();
  // Pending invitee on a doc they cannot read: minimal disclosure only — no
  // metadata, abstract, archivo, adjuntos, related rail, or versions panel
  // (ADR-0010 §6).
  if (detail.view === "minimal") {
    return <MinimalInviteView detail={detail} docId={docId} />;
  }
  const areaName =
    areas.find((a) => a.area_path === detail.area_path)?.display_name ??
    detail.area_path;
  return <DetailView detail={detail} docId={docId} areaName={areaName} />;
}

function MinimalInviteView({
  detail,
  docId,
}: {
  detail: MinimalInviteDoc;
  docId: number;
}) {
  return (
    <main className="mx-auto grid min-h-[calc(100dvh-60px)] w-full place-items-center px-6 py-8">
      <CoauthorInvitationBanner
        docId={docId}
        titulo={detail.titulo}
        inviter={detail.inviter_display_name}
        variant="minimal"
      />
    </main>
  );
}

function DetailView({
  detail,
  docId,
  areaName,
}: {
  detail: DetailDoc | DetailWithInvitationDoc;
  docId: number;
  areaName: string;
}) {
  const tipo = TIPO_LABEL[detail.tipo] ?? detail.tipo;
  const visibilityBadge =
    detail.visibility !== "publico" ? VISIBILITY_LABEL[detail.visibility] : null;
  const autores = detail.autores.map((a) => a.display_name).join(", ");

  return (
    <main className="mx-auto w-full max-w-[1120px] px-6 py-8">
      {detail.view === "detail_with_invitation" && (
        <CoauthorInvitationBanner
          docId={docId}
          titulo={detail.titulo}
          inviter={detail.invitation.inviter_display_name}
          variant="banner"
        />
      )}
      <article className="grid items-start gap-10 lg:grid-cols-[1fr_300px]">
        <header className="min-w-0">
          <h1 className="text-[28px] leading-[1.18] font-semibold tracking-tight">
            {detail.titulo}
          </h1>
          <div className="text-muted-foreground mt-2.5 text-sm">{autores}</div>

          <dl className="mt-6 grid grid-cols-[110px_1fr] gap-x-5 gap-y-2.5 text-sm">
            <dt className="text-muted-foreground">Área</dt>
            <dd className="text-foreground">{areaName}</dd>
            <dt className="text-muted-foreground">Tipo</dt>
            <dd className="text-foreground">{tipo}</dd>
            {detail.fecha && (
              <>
                <dt className="text-muted-foreground">Fecha</dt>
                <dd className="text-foreground">{detail.fecha}</dd>
              </>
            )}
            {visibilityBadge && (
              <>
                <dt className="text-muted-foreground">Visibilidad</dt>
                <dd>
                  <StatusBadge tone="blue">{visibilityBadge}</StatusBadge>
                </dd>
              </>
            )}
          </dl>

          {detail.abstract && (
            <section className="mt-6 border-t border-border pt-6">
              <h2 className="text-[19px] font-semibold tracking-tight">
                Resumen
              </h2>
              <p className="text-neutral-700 mt-3 text-[15px] leading-relaxed">
                {detail.abstract}
              </p>
            </section>
          )}

          {detail.palabras_clave.length > 0 && (
            <section className="mt-7">
              <h2 className="text-[19px] font-semibold tracking-tight">
                Palabras clave
              </h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                {detail.palabras_clave.map((kw) => (
                  <li key={kw}>
                    <StatusBadge tone="neutral">{kw}</StatusBadge>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <RelatedRail docId={docId} />
        </header>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-[84px]">
          {detail.manageable && (
            <Button asChild className="w-full">
              <Link href={`/mis-trabajos/${docId}/editar`}>
                <FileText />
                Editar
              </Link>
            </Button>
          )}

          <section className="border-border bg-card overflow-hidden rounded-lg border">
            <div className="border-border flex items-center justify-between gap-3 border-b px-5 py-3.5">
              <h2 className="text-sm font-semibold whitespace-nowrap">
                Archivo principal
              </h2>
            </div>
            <div className="p-3">
              <div className="hover:bg-neutral-50 hover:border-border-strong flex items-center gap-3 rounded-md border border-border bg-card p-3 transition-colors">
                <div className="bg-primary-tint text-primary grid size-9 flex-none place-items-center rounded-md">
                  <FileText size={18} />
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  {detail.archivo_principal.original_filename}
                </span>
                <Button asChild size="sm">
                  <a
                    href={`/api/docs/${docId}/download`}
                    download
                    aria-label="Descargar archivo principal"
                  >
                    Descargar
                  </a>
                </Button>
              </div>
            </div>
          </section>

          {detail.adjuntos.length > 0 && (
            <section className="border-border bg-card overflow-hidden rounded-lg border">
              <div className="border-border flex items-center justify-between gap-3 border-b px-5 py-3.5">
                <h2 className="text-sm font-semibold whitespace-nowrap">
                  Adjuntos
                </h2>
              </div>
              <ul className="flex flex-col gap-2 p-3">
                {detail.adjuntos.map((att) => (
                  <li
                    key={att.id}
                    className="hover:bg-neutral-50 hover:border-border-strong flex items-center gap-3 rounded-md border border-border bg-card p-3 transition-colors"
                  >
                    <div className="bg-primary-tint text-primary grid size-9 flex-none place-items-center rounded-md">
                      <FileText size={18} />
                    </div>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {att.original_filename}
                    </span>
                    <Button asChild size="sm" variant="outline">
                      <a
                        href={`/api/docs/${docId}/attachments/${att.id}`}
                        download
                        aria-label={`Descargar ${att.original_filename}`}
                      >
                        Descargar
                      </a>
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <VersionsPanel
            docId={docId}
            versions={detail.versions}
            canManage={detail.manageable}
          />

          <ReportDialog docId={docId} />
        </aside>
      </article>
    </main>
  );
}
