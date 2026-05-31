import Link from "next/link";

import { TIPO_LABEL, VISIBILITY_LABEL } from "@/lib/labels";

// Re-exported so existing search consumers keep importing it from here.
export { TIPO_LABEL };

type AuthorDisplay = {
  display_name: string;
  user_id: number | null;
};

export type ResultCardData = {
  doc_id: number;
  titulo: string;
  fecha: string | null;
  area_path: string;
  tipo: string;
  abstract?: string | null;
  snippet?: string;
  snippet_is_html?: boolean;
  visibility?: string;
  autores?: AuthorDisplay[];
};

function truncate(text: string | null | undefined, max: number): string {
  if (!text) return "";
  return text.length <= max ? text : text.slice(0, max - 1).trimEnd() + "…";
}

function renderHighlightedSnippet(snippet: string) {
  let highlighted = false;
  return snippet.split(/(<mark>|<\/mark>)/).map((part, index) => {
    if (part === "<mark>") {
      highlighted = true;
      return null;
    }
    if (part === "</mark>") {
      highlighted = false;
      return null;
    }
    return highlighted ? <mark key={index}>{part}</mark> : part;
  });
}

export function ResultCard({ result }: { result: ResultCardData }) {
  const year = result.fecha ? result.fecha.slice(0, 4) : null;
  const tipo = TIPO_LABEL[result.tipo] ?? result.tipo;
  const visibilityBadge =
    result.visibility && result.visibility !== "publico"
      ? VISIBILITY_LABEL[result.visibility]
      : null;
  const autores = result.autores?.map((a) => a.display_name).join(", ");
  const meta = [year, result.area_path, tipo].filter(Boolean) as string[];
  return (
    <article className="group border-border hover:border-border-strong relative rounded-lg border bg-card px-5 py-[18px] transition-all hover:shadow-[0_2px_8px_-2px_rgba(23,23,23,0.08)]">
      <h2 className="text-[17px] leading-[1.3] font-semibold tracking-tight">
        <Link
          href={`/docs/${result.doc_id}`}
          className="text-foreground transition-colors group-hover:text-primary group-hover:underline underline-offset-2 after:absolute after:inset-0 after:content-['']"
        >
          {result.titulo}
        </Link>
      </h2>
      {autores && (
        <div className="text-muted-foreground mt-1.5 text-[13px]">{autores}</div>
      )}
      <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-2 text-[13px]">
        {meta.map((m, i) => (
          <span key={i} className="flex items-center gap-2">
            {i > 0 && <span className="text-muted-foreground/60">·</span>}
            {m}
          </span>
        ))}
        {visibilityBadge && (
          <span className="bg-status-blue-bg text-status-blue-fg ml-0.5 inline-flex h-[22px] items-center rounded-full px-[9px] text-xs font-medium">
            {visibilityBadge}
          </span>
        )}
      </div>
      {result.abstract && (
        <p className="mt-2.5 text-sm leading-relaxed text-neutral-700">
          {truncate(result.abstract, 280)}
        </p>
      )}
      {result.snippet !== undefined &&
        (result.snippet_is_html ? (
          <p className="mt-2.5 text-sm leading-relaxed text-neutral-700">
            {renderHighlightedSnippet(result.snippet)}
          </p>
        ) : (
          <p className="mt-2.5 text-sm leading-relaxed text-neutral-700">
            {result.snippet}
          </p>
        ))}
    </article>
  );
}

export function ResultCardSkeleton() {
  return (
    <div className="border-border rounded-lg border bg-card px-5 py-[18px]">
      <div className="bg-muted h-4 w-[72%] animate-pulse rounded-sm" />
      <div className="bg-muted mt-3 h-[11px] w-[38%] animate-pulse rounded-sm" />
      <div className="bg-muted mt-2 h-[11px] w-[64%] animate-pulse rounded-sm" />
      <div className="bg-muted mt-3.5 h-[11px] w-full animate-pulse rounded-sm" />
      <div className="bg-muted mt-1.5 h-[11px] w-[92%] animate-pulse rounded-sm" />
    </div>
  );
}
