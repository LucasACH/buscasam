"use client";

import { ResultCard } from "@/app/buscar/ResultCard";

import { useRelated } from "./useRelated";

export function RelatedRail({ docId }: { docId: number }) {
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
