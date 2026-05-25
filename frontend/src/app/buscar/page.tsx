"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";

import { ResultCard } from "./ResultCard";
import { useSearch } from "./useSearch";

const PAGE_SIZE = 10;

function parsePagina(raw: string | null): number {
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1;
}

export default function BuscarPage() {
  const router = useRouter();
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  const pagina = parsePagina(params.get("pagina"));

  const update = useCallback(
    (next: { q?: string; pagina?: number }) => {
      const sp = new URLSearchParams(params.toString());
      if (next.q !== undefined) {
        if (next.q) sp.set("q", next.q);
        else sp.delete("q");
        sp.delete("pagina");
      }
      if (next.pagina !== undefined) {
        if (next.pagina > 1) sp.set("pagina", String(next.pagina));
        else sp.delete("pagina");
      }
      const qs = sp.toString();
      router.replace(qs ? `/buscar?${qs}` : "/buscar");
    },
    [params, router],
  );

  const { data, isLoading, isError } = useSearch({ q, pagina });
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Buscar</h1>
      <form className="mt-4" role="search" onSubmit={(e) => e.preventDefault()}>
        <label htmlFor="q" className="sr-only">
          Consulta
        </label>
        <input
          id="q"
          type="search"
          className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-lg border px-3 text-sm outline-none focus-visible:ring-2"
          placeholder="Buscar por título, tema, autor…"
          value={q}
          onChange={(e) => update({ q: e.target.value })}
        />
      </form>

      {q && (
        <p className="text-muted-foreground mt-3 text-xs">
          {isLoading
            ? "Buscando…"
            : isError
              ? "Hubo un problema al buscar."
              : `${total} resultado${total === 1 ? "" : "s"}`}
        </p>
      )}

      <section className="mt-6 flex flex-col gap-3">
        {data?.results.map((r) => (
          <ResultCard key={r.doc_id} result={r} />
        ))}
      </section>

      {q && total > PAGE_SIZE && (
        <nav
          className="mt-8 flex items-center justify-between"
          aria-label="Paginación"
        >
          <Button
            variant="outline"
            size="sm"
            disabled={pagina <= 1}
            onClick={() => update({ pagina: pagina - 1 })}
          >
            Anterior
          </Button>
          <span className="text-muted-foreground text-xs">
            Página {pagina} de {lastPage}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={pagina >= lastPage}
            onClick={() => update({ pagina: pagina + 1 })}
          >
            Siguiente
          </Button>
        </nav>
      )}
    </main>
  );
}
