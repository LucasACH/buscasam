import Link from "next/link";
import { notFound } from "next/navigation";

import { CoauthorInvitationBanner } from "@/components/CoauthorInvitationBanner";
import { VersionsPanel } from "@/components/VersionsPanel";

import { fetchAreas, fetchDocDetail } from "./fetchDetail";
import { RelatedRail } from "./RelatedRail";
import type { DetailDoc, DetailWithInvitationDoc, MinimalInviteDoc } from "./types";

const TIPO_LABEL: Record<string, string> = {
  tesis: "Tesis",
  paper: "Paper",
  trabajo_practico: "Trabajo práctico",
  proyecto_investigacion: "Proyecto de investigación",
  monografia: "Monografía",
  ponencia_poster: "Ponencia / Póster",
  apunte_resumen: "Apunte / Resumen",
  informe_catedra: "Informe de cátedra",
};

const VISIBILITY_LABEL: Record<string, string> = {
  interno: "Interno",
  privado: "Privado",
};

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
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
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
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      {detail.view === "detail_with_invitation" && (
        <CoauthorInvitationBanner
          docId={docId}
          titulo={detail.titulo}
          inviter={detail.invitation.inviter_display_name}
          variant="banner"
        />
      )}
      <article className="md:grid md:grid-cols-3 md:gap-8">
        <header className="md:col-span-2">
          <h1 className="text-2xl leading-snug font-semibold tracking-tight">
            {detail.titulo}
          </h1>
          <dl className="text-muted-foreground mt-3 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="font-medium">Autores</dt>
            <dd>{autores}</dd>
            <dt className="font-medium">Área</dt>
            <dd>{areaName}</dd>
            <dt className="font-medium">Tipo</dt>
            <dd>{tipo}</dd>
            {detail.fecha && (
              <>
                <dt className="font-medium">Fecha</dt>
                <dd>{detail.fecha}</dd>
              </>
            )}
            {visibilityBadge && (
              <>
                <dt className="font-medium">Visibilidad</dt>
                <dd>
                  <span className="border-border bg-muted text-foreground rounded-full border px-2 py-0.5 text-xs font-medium">
                    {visibilityBadge}
                  </span>
                </dd>
              </>
            )}
          </dl>

          {detail.abstract && (
            <section className="mt-6">
              <h2 className="text-sm font-medium">Resumen</h2>
              <p className="text-foreground mt-1 text-sm leading-relaxed">
                {detail.abstract}
              </p>
            </section>
          )}

          {detail.palabras_clave.length > 0 && (
            <section className="mt-6">
              <h2 className="text-sm font-medium">Palabras clave</h2>
              <ul className="mt-2 flex flex-wrap gap-2">
                {detail.palabras_clave.map((kw) => (
                  <li
                    key={kw}
                    className="border-border bg-muted rounded-full border px-2 py-0.5 text-xs"
                  >
                    {kw}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </header>

        <aside className="mt-8 md:col-span-1 md:mt-0">
          <section>
            <h2 className="text-sm font-medium">Archivo principal</h2>
            <div className="border-border mt-2 flex items-center justify-between gap-3 rounded-lg border p-3">
              <span className="truncate text-sm">
                {detail.archivo_principal.original_filename}
              </span>
              <a
                href={`/api/docs/${docId}/download`}
                download
                aria-label="Descargar archivo principal"
                className="text-primary text-sm underline-offset-2 hover:underline"
              >
                Descargar
              </a>
            </div>
          </section>

          {detail.adjuntos.length > 0 && (
            <section className="mt-6">
              <h2 className="text-sm font-medium">Adjuntos</h2>
              <ul className="mt-2 space-y-2">
                {detail.adjuntos.map((att) => (
                  <li
                    key={att.id}
                    className="border-border flex items-center justify-between gap-3 rounded-lg border p-3"
                  >
                    <span className="truncate text-sm">
                      {att.original_filename}
                    </span>
                    <a
                      href={`/api/docs/${docId}/attachments/${att.id}`}
                      download
                      aria-label={`Descargar ${att.original_filename}`}
                      className="text-primary text-sm underline-offset-2 hover:underline"
                    >
                      Descargar
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {detail.manageable && (
            <div className="mt-6">
              <Link
                href={`/mis-trabajos/${docId}/editar`}
                className="border-border hover:bg-muted inline-flex items-center rounded-lg border px-3 py-1.5 text-sm font-medium"
              >
                Editar
              </Link>
            </div>
          )}

          <VersionsPanel
            docId={docId}
            versions={detail.versions}
            canManage={detail.manageable}
          />
        </aside>
      </article>

      <RelatedRail docId={docId} />
    </main>
  );
}
