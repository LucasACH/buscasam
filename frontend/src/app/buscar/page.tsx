"use client";

import { Suspense, useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, Search, X } from "lucide-react";

import { Wordmark } from "@/components/Wordmark";
import { Button } from "@/components/ui/button";

import { ResultCard, ResultCardSkeleton, TIPO_LABEL } from "./ResultCard";
import { SearchFilters, type FilterPatch } from "./SearchFilters";
import { useSearch, type Orden, type Tipo } from "./useSearch";

const PAGE_SIZE = 10;
const RELEVANCE_PAGE_CAP = 20;
const TIPO_VALUES = Object.keys(TIPO_LABEL) as Tipo[];
const QUICK_TIPOS: Tipo[] = [
  "tesis",
  "paper",
  "trabajo_practico",
  "monografia",
];

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
  const hasFilters =
    area !== null || tipos.length > 0 || desde !== null || hasta !== null;
  const showResults = q.length > 0 || orden === "recientes" || hasFilters;
  const total = data?.total ?? 0;
  let lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (orden === "relevancia") lastPage = Math.min(lastPage, RELEVANCE_PAGE_CAP);

  if (!showResults) {
    return (
      <main className="flex min-h-[calc(100dvh-61px)] flex-col items-center justify-center px-5 pt-10 pb-20">
        <div className="flex w-full max-w-[640px] flex-col items-center text-center">
          <Wordmark size="lg" />
          <h1 className="mt-7 max-w-[540px] text-[34px] leading-tight font-semibold tracking-tight">
            Encontrá trabajos académicos de la comunidad UNSAM
          </h1>

          <form
            role="search"
            className="mt-7 w-full max-w-[560px]"
            onSubmit={(e) => {
              e.preventDefault();
              update({ q: qInput.trim() });
            }}
          >
            <label htmlFor="q" className="sr-only">
              Consulta
            </label>
            <div className="border-input bg-background focus-within:border-primary focus-within:ring-primary-tint flex h-15 items-center gap-2.5 rounded-lg border py-2 pr-2 pl-[18px] shadow-[0_1px_2px_rgba(23,23,23,0.03)] transition focus-within:ring-4">
              <Search className="text-muted-foreground/70 size-[22px] shrink-0" />
              <input
                id="q"
                type="text"
                autoFocus
                className="flex-1 bg-transparent text-[17px] outline-none placeholder:text-muted-foreground/70"
                placeholder="Buscar por título, tema, autor…"
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
              />
              {qInput && (
                <button
                  type="button"
                  aria-label="Limpiar búsqueda"
                  onClick={() => setQInput("")}
                  className="text-muted-foreground/60 hover:text-foreground hover:bg-muted flex size-8 shrink-0 items-center justify-center rounded-full transition-colors"
                >
                  <X className="size-[18px]" />
                </button>
              )}
              <button
                type="submit"
                className="bg-primary text-primary-foreground hover:bg-primary-hover inline-flex h-11 items-center rounded-lg px-[22px] text-base font-medium transition-colors"
              >
                Buscar
              </button>
            </div>
          </form>

          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {QUICK_TIPOS.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => update({ tipos: [t] })}
                className="border-input hover:border-neutral-400 hover:bg-neutral-50 inline-flex h-[30px] items-center rounded-full border bg-background px-3 text-[13px] font-medium transition-colors"
              >
                {TIPO_LABEL[t]}
              </button>
            ))}
            <button
              type="button"
              onClick={() => update({ orden: "recientes" })}
              className="border-primary-tint-2 text-primary hover:bg-primary-tint inline-flex h-[30px] items-center rounded-full border bg-background px-3 text-[13px] font-medium transition-colors"
            >
              Ver más recientes
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <>
      <div className="border-border bg-background/90 sticky top-[61px] z-40 border-b backdrop-blur-md">
        <div className="mx-auto w-full max-w-3xl px-6 pt-4 pb-3.5">
          <form
            role="search"
            className="relative flex items-center"
            onSubmit={(e) => {
              e.preventDefault();
              update({ q: qInput.trim() });
            }}
          >
            <label htmlFor="q" className="sr-only">
              Consulta
            </label>
            <Search className="text-muted-foreground/70 pointer-events-none absolute left-3 size-[18px]" />
            <input
              id="q"
              type="text"
              className="border-input bg-background focus:border-primary focus:ring-primary-tint h-11 w-full rounded-lg border pr-10 pl-[42px] text-sm outline-none transition focus:ring-[3px]"
              placeholder="Buscar por título, tema, autor…"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
            />
            {qInput && (
              <button
                type="button"
                aria-label="Limpiar búsqueda"
                onClick={() => setQInput("")}
                className="text-muted-foreground/60 hover:text-foreground hover:bg-muted absolute right-2 flex size-7 items-center justify-center rounded-full transition-colors"
              >
                <X className="size-4" />
              </button>
            )}
          </form>

          <div className="mt-3">
            <SearchFilters
              area={area}
              tipos={tipos}
              desde={desde}
              hasta={hasta}
              orden={orden}
              onChange={update}
            />
          </div>
        </div>
      </div>

      <main className="mx-auto w-full max-w-3xl px-6 pt-5 pb-20">
        <p className="text-muted-foreground mb-4 min-h-[18px] text-[13px]">
          {isLoading ? (
            "Buscando…"
          ) : isError ? (
            <span className="text-destructive">
              No se pudo completar la búsqueda. Reintentá en unos segundos.
            </span>
          ) : (
            <>
              <span className="text-foreground font-semibold">{total}</span>{" "}
              resultado{total === 1 ? "" : "s"}
              {q && (
                <>
                  {" "}
                  para «<span className="text-foreground">{q}</span>»
                </>
              )}
            </>
          )}
        </p>

        {isLoading ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <ResultCardSkeleton key={i} />
            ))}
          </div>
        ) : total === 0 && !isError ? (
          <EmptyResults
            onClear={
              hasFilters
                ? () =>
                    update({
                      area: null,
                      tipos: [],
                      desde: null,
                      hasta: null,
                    })
                : undefined
            }
          />
        ) : (
          <section className="flex flex-col gap-3">
            {data?.results.map((r) => (
              <ResultCard key={r.doc_id} result={r} />
            ))}
          </section>
        )}

        {total > PAGE_SIZE && (
          <nav
            className="mt-7 flex items-center justify-center gap-3.5"
            aria-label="Paginación"
          >
            <Button
              variant="outline"
              size="sm"
              disabled={pagina <= 1}
              onClick={() => update({ pagina: pagina - 1 })}
            >
              <ChevronLeft data-icon="inline-start" />
              Anterior
            </Button>
            <span className="text-muted-foreground text-[13px]">
              Página {pagina} de {lastPage}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={pagina >= lastPage}
              onClick={() => update({ pagina: pagina + 1 })}
            >
              Siguiente
              <ChevronRight data-icon="inline-end" />
            </Button>
          </nav>
        )}
      </main>
    </>
  );
}

function EmptyResults({ onClear }: { onClear?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="border-border bg-neutral-100 text-muted-foreground/70 grid size-12 place-items-center rounded-lg border">
        <Search className="size-[22px]" />
      </div>
      <div className="text-base font-semibold tracking-tight">
        No encontramos resultados
      </div>
      <div className="text-muted-foreground max-w-[340px] text-sm">
        Probá con otras palabras clave o ajustá los filtros para ampliar la
        búsqueda.
      </div>
      {onClear && (
        <Button variant="outline" size="sm" className="mt-1.5" onClick={onClear}>
          Limpiar filtros
        </Button>
      )}
    </div>
  );
}
