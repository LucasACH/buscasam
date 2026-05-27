"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { ResultCard } from "@/app/buscar/ResultCard";
import { VersionsPanel } from "@/components/VersionsPanel";

import { useDocDetail, type DocDetail } from "./useDocDetail";
import { useRelated } from "./useRelated";

type Area = components["schemas"]["AreaDTO"];

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

function useAreaDisplayName(area_path: string | undefined): string | undefined {
  const { data } = useQuery<Area[]>({
    queryKey: ["areas"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/areas");
      if (error) throw error;
      return data ?? [];
    },
    enabled: area_path !== undefined,
    staleTime: 5 * 60_000,
  });
  return data?.find((a) => a.area_path === area_path)?.display_name;
}

export default function DocDetailPage() {
  const params = useParams<{ id: string }>();
  const docId = Number(params.id);
  const { detail, is404, isLoading } = useDocDetail(docId);

  useEffect(() => {
    if (!detail) return;
    const previous = document.title;
    document.title = detail.titulo;
    return () => {
      document.title = previous;
    };
  }, [detail]);

  if (is404) {
    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-8">
        <p className="text-muted-foreground text-sm">
          No encontramos este documento
        </p>
      </main>
    );
  }

  if (isLoading || !detail) return null;

  return <DetailView detail={detail} docId={docId} />;
}

function DetailView({ detail, docId }: { detail: DocDetail; docId: number }) {
  const areaName = useAreaDisplayName(detail.area_path);
  const tipo = TIPO_LABEL[detail.tipo] ?? detail.tipo;
  const visibilityBadge =
    detail.visibility !== "publico" ? VISIBILITY_LABEL[detail.visibility] : null;
  const autores = detail.autores.map((a) => a.display_name).join(", ");

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <article className="md:grid md:grid-cols-3 md:gap-8">
        <header className="md:col-span-2">
          <h1 className="text-2xl leading-snug font-semibold tracking-tight">
            {detail.titulo}
          </h1>
          <dl className="text-muted-foreground mt-3 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="font-medium">Autores</dt>
            <dd>{autores}</dd>
            <dt className="font-medium">Área</dt>
            <dd>{areaName ?? detail.area_path}</dd>
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

function RelatedRail({ docId }: { docId: number }) {
  const { related } = useRelated(docId);
  if (!related || related.length === 0) return null;
  return (
    <section className="mt-10">
      <h2 className="text-sm font-medium">Trabajos relacionados</h2>
      <div className="mt-3 flex flex-col gap-3">
        {related.map((r) => (
          <ResultCard
            key={r.doc_id}
            result={{
              doc_id: r.doc_id,
              titulo: r.titulo,
              fecha: r.fecha,
              area_path: r.area_path,
              tipo: r.tipo,
              autores: r.autores,
            }}
          />
        ))}
      </div>
    </section>
  );
}
