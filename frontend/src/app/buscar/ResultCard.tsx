import Link from "next/link";

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

const VISIBILITY_LABEL: Record<string, string> = {
  interno: "Interno",
  privado: "Privado",
};

export const TIPO_LABEL: Record<string, string> = {
  tesis: "Tesis",
  paper: "Paper",
  trabajo_practico: "Trabajo práctico",
  proyecto_investigacion: "Proyecto de investigación",
  monografia: "Monografía",
  ponencia_poster: "Ponencia / Póster",
  apunte_resumen: "Apunte / Resumen",
  informe_catedra: "Informe de cátedra",
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
  return (
    <article className="border-border bg-background rounded-lg border p-4 shadow-sm">
      <h2 className="text-foreground text-lg leading-snug font-semibold">
        <Link
          href={`/docs/${result.doc_id}`}
          className="hover:underline underline-offset-2"
        >
          {result.titulo}
        </Link>
      </h2>
      {autores && (
        <div className="text-muted-foreground mt-1 text-xs">{autores}</div>
      )}
      <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {year && <span>{year}</span>}
        <span>{result.area_path}</span>
        <span>{tipo}</span>
        {visibilityBadge && (
          <span className="border-border bg-muted text-foreground rounded-full border px-2 py-0.5 font-medium">
            {visibilityBadge}
          </span>
        )}
      </div>
      {result.abstract && (
        <p className="text-muted-foreground mt-3 text-sm">
          {truncate(result.abstract, 280)}
        </p>
      )}
      {result.snippet !== undefined &&
        (result.snippet_is_html ? (
          <p className="mt-3 text-sm leading-relaxed [&_mark]:bg-yellow-200 [&_mark]:px-0.5 [&_mark]:font-medium">
            {renderHighlightedSnippet(result.snippet)}
          </p>
        ) : (
          <p className="mt-3 text-sm leading-relaxed">{result.snippet}</p>
        ))}
    </article>
  );
}
