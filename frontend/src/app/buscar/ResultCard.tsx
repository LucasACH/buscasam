import type { components } from "@/api/schema";

type Result = components["schemas"]["ResultDTO"];

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

function truncate(text: string | null, max: number): string {
  if (!text) return "";
  return text.length <= max ? text : text.slice(0, max - 1).trimEnd() + "…";
}

export function ResultCard({ result }: { result: Result }) {
  const year = result.fecha.slice(0, 4);
  const tipo = TIPO_LABEL[result.tipo] ?? result.tipo;
  return (
    <article className="border-border bg-background rounded-lg border p-4 shadow-sm">
      <h2 className="text-foreground text-lg leading-snug font-semibold">
        {result.titulo}
      </h2>
      <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        <span>{year}</span>
        <span>{result.area_path}</span>
        <span>{tipo}</span>
      </div>
      {result.abstract && (
        <p className="text-muted-foreground mt-3 text-sm">
          {truncate(result.abstract, 280)}
        </p>
      )}
      <p
        className="mt-3 text-sm leading-relaxed [&_mark]:bg-yellow-200 [&_mark]:px-0.5 [&_mark]:font-medium"
        dangerouslySetInnerHTML={{ __html: result.snippet }}
      />
    </article>
  );
}
