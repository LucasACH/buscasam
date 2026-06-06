import type { Metadata } from "next";
import { after } from "next/server";
import { FileText, Mail } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BackButton } from "@/components/BackButton";
import { CoauthorInvitationBanner } from "@/components/CoauthorInvitationBanner";
import { CopyEmailButton } from "@/components/CopyEmailButton";
import { ReportDialog } from "@/components/ReportDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { VersionsPanel } from "@/components/VersionsPanel";
import { AreaBreadcrumb } from "@/components/AreaBreadcrumb";
import { Button } from "@/components/ui/button";
import { TIPO_LABEL, VISIBILITY_LABEL } from "@/lib/labels";

import {
  fetchAreas,
  fetchDocDetail,
  recordSearchClick,
  type Area,
} from "./fetchDetail";
import { DownloadButton } from "./DownloadButton";
import { RelatedRail } from "./RelatedRail";
import type {
  DetailDoc,
  DetailWithInvitationDoc,
  MinimalInviteDoc,
} from "./types";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function parseDocId(raw: string): number | null {
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

function truncate(s: string, n: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length <= n ? t : `${t.slice(0, n - 1).trimEnd()}…`;
}

function metaDescription(detail: DetailDoc | DetailWithInvitationDoc): string {
  if (detail.abstract) return truncate(detail.abstract, 155);
  const tipo = TIPO_LABEL[detail.tipo] ?? detail.tipo;
  const autores = detail.autores.map((a) => a.display_name).join(", ");
  return truncate(
    [tipo, autores && `por ${autores}`, "UNSAM"].filter(Boolean).join(" · "),
    155,
  );
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const docId = parseDocId((await params).id);
  if (docId === null) return {};
  const detail = await fetchDocDetail(docId);
  // Pending-invitation minimal blocks are private by construction — keep them
  // out of the index even if a crawler somehow reaches one.
  if (!detail || detail.view === "minimal") return { robots: { index: false } };
  const description = metaDescription(detail);
  return {
    title: detail.titulo,
    description,
    keywords: detail.palabras_clave.length ? detail.palabras_clave : undefined,
    authors: detail.autores.map((a) => ({ name: a.display_name })),
    alternates: { canonical: `/docs/${docId}` },
    robots: detail.visibility === "publico" ? undefined : { index: false },
    openGraph: {
      type: "article",
      url: `/docs/${docId}`,
      title: detail.titulo,
      description,
      images: ["/opengraph-image"],
    },
  };
}

export default async function DocDetailPage({
  params,
  searchParams,
}: PageProps) {
  const docId = parseDocId((await params).id);
  if (docId === null) notFound();
  const [detail, areas] = await Promise.all([
    fetchDocDetail(docId),
    fetchAreas(),
  ]);
  if (!detail) notFound();
  // Arrived from a search result (?s=search_id&r=rank): attribute the click.
  // Runs post-response via after() so this non-critical write never delays the
  // page render (recordSearchClick is already best-effort/idempotent).
  const sp = await searchParams;
  const s = typeof sp.s === "string" ? sp.s : null;
  const r = typeof sp.r === "string" ? Number(sp.r) : NaN;
  if (s && Number.isInteger(r) && r >= 1) {
    after(() => recordSearchClick(s, docId, r));
  }
  // Pending invitee on a doc they cannot read: minimal disclosure only — no
  // metadata, abstract, archivo, adjuntos, related rail, or versions panel
  // (ADR-0010 §6).
  if (detail.view === "minimal") {
    return <MinimalInviteView detail={detail} docId={docId} />;
  }
  return (
    <DetailView
      detail={detail}
      docId={docId}
      areaName={areaLabel(areas, detail.area_path)}
    />
  );
}

// Resolve an ltree leaf path to an Escuela › Carrera › Materia breadcrumb,
// mapping each ancestor segment to its display_name and falling back to the raw
// segment. Mirrors useAreaLabel for this server-rendered view.
function areaLabel(areas: Area[], areaPath: string): string {
  const byPath = new Map(areas.map((a) => [a.area_path, a.display_name]));
  const segments = areaPath.split(".");
  return segments
    .map(
      (_, i) => byPath.get(segments.slice(0, i + 1).join(".")) ?? segments[i],
    )
    .join(" › ");
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

const UNSAM = "Universidad Nacional de San Martín (UNSAM)";

function publicBase(): string {
  return (process.env.BUSCASAM_BASE_URL ?? "http://localhost:3000").replace(
    /\/$/,
    "",
  );
}

// ScholarlyArticle + BreadcrumbList for the public doc page. JSON.stringify
// drops undefined keys, so optional fields fall away cleanly when absent.
function docJsonLd(
  detail: DetailDoc | DetailWithInvitationDoc,
  docId: number,
  areaName: string,
) {
  const base = publicBase();
  const url = `${base}/docs/${docId}`;
  const article = {
    "@context": "https://schema.org",
    "@type": "ScholarlyArticle",
    headline: detail.titulo,
    name: detail.titulo,
    inLanguage: "es",
    url,
    author: detail.autores.map((a) => ({
      "@type": "Person",
      name: a.display_name,
    })),
    abstract: detail.abstract || undefined,
    keywords: detail.palabras_clave.length
      ? detail.palabras_clave.join(", ")
      : undefined,
    datePublished: detail.fecha || undefined,
    genre: TIPO_LABEL[detail.tipo] ?? detail.tipo,
    publisher: { "@type": "Organization", name: UNSAM },
    isPartOf: { "@type": "Organization", name: UNSAM },
  };
  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: "Inicio",
        item: `${base}/buscar`,
      },
      {
        "@type": "ListItem",
        position: 2,
        name: areaName,
        item: `${base}/buscar?area=${encodeURIComponent(detail.area_path)}`,
      },
      { "@type": "ListItem", position: 3, name: detail.titulo, item: url },
    ],
  };
  return [article, breadcrumb];
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
    detail.visibility !== "publico"
      ? VISIBILITY_LABEL[detail.visibility]
      : null;
  const autores = detail.autores.map((a) => a.display_name).join(", ");

  return (
    <main className="mx-auto w-full max-w-[1120px] px-6 py-8">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(docJsonLd(detail, docId, areaName)),
        }}
      />
      {detail.view === "detail_with_invitation" && (
        <CoauthorInvitationBanner
          docId={docId}
          titulo={detail.titulo}
          inviter={detail.invitation.inviter_display_name}
          variant="banner"
        />
      )}
      <article className="grid grid-cols-1 items-start gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <header className="min-w-0">
          <BackButton />
          <h1 className="text-[28px] leading-[1.18] font-semibold tracking-tight">
            {detail.titulo}
          </h1>
          <div className="text-muted-foreground mt-2.5 text-sm">{autores}</div>

          <dl className="mt-6 grid grid-cols-[64px_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm">
            <dt className="text-muted-foreground">Área</dt>
            <dd className="text-foreground flex flex-wrap items-center gap-x-1.5">
              <AreaBreadcrumb areaName={areaName} />
            </dd>
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
            <section className="border-border mt-6 border-t pt-6">
              <h2 className="text-[19px] font-semibold tracking-tight">
                Resumen
              </h2>
              <p className="mt-3 text-[15px] leading-relaxed text-neutral-700">
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

        <aside className="flex flex-col gap-4 lg:sticky lg:top-[93px] lg:max-h-[calc(100dvh-108px)] lg:overflow-y-auto">
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
              <div className="hover:border-border-strong border-border bg-card flex items-center gap-3 rounded-md border p-3 transition-colors hover:bg-neutral-50">
                <div className="bg-primary-tint text-primary grid size-9 flex-none place-items-center rounded-md">
                  <FileText size={18} />
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  {detail.archivo_principal.original_filename}
                </span>
                <DownloadButton
                  docId={docId}
                  label="Descargar archivo principal"
                  href={`/api/docs/${docId}/download`}
                  eventProperties={{ tipo: detail.tipo, file_type: "main" }}
                />
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
                    className="hover:border-border-strong border-border bg-card flex items-center gap-3 rounded-md border p-3 transition-colors hover:bg-neutral-50"
                  >
                    <div className="bg-primary-tint text-primary grid size-9 flex-none place-items-center rounded-md">
                      <FileText size={18} />
                    </div>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {att.original_filename}
                    </span>
                    <DownloadButton
                      docId={docId}
                      label={`Descargar ${att.original_filename}`}
                      href={`/api/docs/${docId}/attachments/${att.id}`}
                      variant="outline"
                      eventProperties={{
                        tipo: detail.tipo,
                        file_type: "attachment",
                        attachment_id: att.id,
                      }}
                    />
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

          {detail.owner_email && (
            <section className="border-border bg-card overflow-hidden rounded-lg border">
              <div className="border-border flex items-center justify-between gap-3 border-b px-5 py-3.5">
                <h2 className="text-sm font-semibold whitespace-nowrap">
                  Contacto
                </h2>
              </div>
              <div className="p-3">
                <div className="border-border bg-card flex items-center gap-3 rounded-md border p-3">
                  <div className="bg-primary-tint text-primary grid size-9 flex-none place-items-center rounded-md">
                    <Mail size={18} />
                  </div>
                  <a
                    href={`mailto:${detail.owner_email}`}
                    className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
                  >
                    {detail.owner_email}
                  </a>
                  <CopyEmailButton email={detail.owner_email} />
                </div>
              </div>
            </section>
          )}

          {!detail.manageable && <ReportDialog docId={docId} />}
        </aside>
      </article>
    </main>
  );
}
