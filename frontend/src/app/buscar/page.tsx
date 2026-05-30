"use client";

import { Suspense, useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";

import { ResultCard, TIPO_LABEL } from "./ResultCard";
import { SearchFilters, type FilterPatch } from "./SearchFilters";
import { useSearch, type Orden, type Tipo } from "./useSearch";

const PAGE_SIZE = 10;
const RELEVANCE_PAGE_CAP = 20;
const TIPO_VALUES = Object.keys(TIPO_LABEL) as Tipo[];

function parsePagina(raw: string | null): number {
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : 1;
}

function parseYear(raw: string | null): number | null {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1000 && n <= 9999 ? n : null;
}

function parseOrden(raw: string | null): Orden {
  return raw === "recientes" ? "recientes" : "relevancia";
}

function parseTipos(raw: string[]): Tipo[] {
  return raw.filter((t): t is Tipo => TIPO_VALUES.includes(t as Tipo));
}

export default function BuscarPage() {
  return (
    <Suspense fallback={null}>
      <BuscarPageInner />
    </Suspense>
  );
}

function BuscarPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  const pagina = parsePagina(params.get("pagina"));
  const area = params.get("area");
  const tipos = parseTipos(params.getAll("tipo"));
  const desde = parseYear(params.get("desde"));
  const hasta = parseYear(params.get("hasta"));
  const orden = parseOrden(params.get("orden"));
  const [qInput, setQInput] = useState(q);

  const update = useCallback(
    (next: FilterPatch & { q?: string; pagina?: number }) => {
      const sp = new URLSearchParams(params.toString());
      const set = (key: string, val: string | null | undefined) => {
        if (val) sp.set(key, val);
        else sp.delete(key);
      };
      if (next.q !== undefined) set("q", next.q);
      if (next.area !== undefined) set("area", next.area);
      if (next.desde !== undefined) set("desde", next.desde?.toString());
      if (next.hasta !== undefined) set("hasta", next.hasta?.toString());
      if (next.orden !== undefined)
        set("orden", next.orden === "recientes" ? "recientes" : null);
      if (next.tipos !== undefined) {
        sp.delete("tipo");
        for (const t of next.tipos) sp.append("tipo", t);
      }
      // any change other than pagination resets to page 1
      if (Object.keys(next).some((k) => k !== "pagina")) sp.delete("pagina");
      if (next.pagina !== undefined) {
        if (next.pagina > 1) sp.set("pagina", String(next.pagina));
        else sp.delete("pagina");
      }
      const qs = sp.toString();
      router.replace(qs ? `/buscar?${qs}` : "/buscar");
    },
    [params, router],
  );

  const { data, isLoading, isError } = useSearch({
    q,
    pagina,
    area,
    tipos,
    desde,
    hasta,
    orden,
  });
  const active = q.length > 0 || orden === "recientes";
  const total = data?.total ?? 0;
  let lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (orden === "relevancia") lastPage = Math.min(lastPage, RELEVANCE_PAGE_CAP);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Buscar</h1>
      <form
        className="mt-4"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: qInput.trim() });
        }}
      >
        <label htmlFor="q" className="sr-only">
          Consulta
        </label>
        <input
          id="q"
          type="search"
          className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-lg border px-3 text-sm outline-none focus-visible:ring-2"
          placeholder="Buscar por título, tema, autor…"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
        />
      </form>

      <SearchFilters
        area={area}
        tipos={tipos}
        desde={desde}
        hasta={hasta}
        orden={orden}
        onChange={update}
      />

      {active && (
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

      {active && total > PAGE_SIZE && (
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
