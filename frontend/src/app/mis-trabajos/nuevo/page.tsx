"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { api } from "@/api/client";
import { useUser } from "@/lib/useUser";
import { AreasCascader } from "@/components/AreasCascader";
import { CoauthorPicker } from "@/components/CoauthorPicker";
import { Button } from "@/components/ui/button";

const DOCUMENT_TYPES = [
  { value: "tesis", label: "Tesis" },
  { value: "paper", label: "Paper" },
  { value: "trabajo_practico", label: "Trabajo práctico" },
  { value: "proyecto_investigacion", label: "Proyecto de investigación" },
  { value: "monografia", label: "Monografía" },
  { value: "ponencia_poster", label: "Ponencia / Póster" },
  { value: "apunte_resumen", label: "Apunte / Resumen" },
  { value: "informe_catedra", label: "Informe de cátedra" },
] as const;

const VISIBILITIES = [
  {
    value: "publico",
    label: "Público",
    help: "Cualquier persona puede encontrarlo y leerlo.",
  },
  {
    value: "interno",
    label: "Interno",
    help: "Sólo personas con cuenta UNSAM pueden encontrarlo y leerlo.",
  },
  {
    value: "privado",
    label: "Privado",
    help: "Sólo vos y tus coautores aceptados.",
  },
] as const;

const formSchema = z.object({
  titulo: z.string().min(1, "El título es obligatorio"),
  area_path: z.string().min(1, "Elegí una Materia"),
  tipo: z.enum([
    "tesis",
    "paper",
    "trabajo_practico",
    "proyecto_investigacion",
    "monografia",
    "ponencia_poster",
    "apunte_resumen",
    "informe_catedra",
  ]),
  visibilidad: z.enum(["publico", "interno", "privado"]),
  external_authors: z.string(),
  coauthor_user_ids: z.array(z.number()),
});

type FormValues = z.infer<typeof formSchema>;

function parseExternalAuthors(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function NuevoPage() {
  const { isInvitado, isLoading } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (isInvitado) router.replace("/login?next=/mis-trabajos/nuevo");
  }, [isInvitado, router]);

  if (isLoading || isInvitado) return null;
  return <NuevoForm />;
}

function NuevoForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      titulo: "",
      area_path: "",
      tipo: "tesis",
      visibilidad: "publico",
      external_authors: "",
      coauthor_user_ids: [],
    },
  });

  async function onSubmit(values: FormValues) {
    setSubmitError(null);
    if (!file) {
      setSubmitError("Adjuntá el archivo principal");
      return;
    }
    setSubmitting(true);
    try {
      const { data, error } = await api.POST("/api/documents", {
        body: {
          title: values.titulo,
          area_path: values.area_path,
          document_type: values.tipo,
          visibility: values.visibilidad,
          external_authors: parseExternalAuthors(values.external_authors),
          coauthor_user_ids: values.coauthor_user_ids,
        },
      });
      if (error || !data) {
        const detail = (error as { detail?: string } | undefined)?.detail;
        setSubmitError(detail ?? "No se pudo crear el borrador. Revisá los datos.");
        return;
      }
      const { id } = data;

      // Raw fetch: the generated body type for /upload is `{ file: string }`
      // (FastAPI's binary placeholder), not assignable from a runtime File +
      // FormData. The typed client does not help here.
      const form = new FormData();
      form.append("file", file);
      const uploadResp = await fetch(`/api/documents/${id}/upload`, {
        method: "POST",
        credentials: "same-origin",
        body: form,
      });
      if (uploadResp.status === 202) {
        router.replace(`/mis-trabajos/${id}/editar`);
        return;
      }
      const detail = await uploadResp
        .json()
        .then((b) => (b as { detail?: string }).detail)
        .catch(() => undefined);
      setSubmitError(detail ?? "No se pudo subir el archivo.");
    } catch {
      setSubmitError("No se pudo conectar con el servidor. Intentá de nuevo.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Nuevo trabajo</h1>

      <form className="mt-6 space-y-6" onSubmit={handleSubmit(onSubmit)}>
        <div className="space-y-1">
          <label htmlFor="titulo" className="text-sm font-medium">
            Título
          </label>
          <input
            id="titulo"
            className="w-full rounded-md border px-3 py-2 text-sm"
            {...register("titulo")}
          />
          {errors.titulo && (
            <p className="text-destructive text-xs">{errors.titulo.message}</p>
          )}
        </div>

        <Controller
          name="area_path"
          control={control}
          render={({ field }) => (
            <AreasCascader
              requireLeaf
              onChange={(area) => field.onChange(area ?? "")}
            />
          )}
        />
        {errors.area_path && (
          <p className="text-destructive text-xs">{errors.area_path.message}</p>
        )}

        <div className="space-y-1">
          <label htmlFor="tipo" className="text-sm font-medium">
            Tipo
          </label>
          <select
            id="tipo"
            className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
            {...register("tipo")}
          >
            {DOCUMENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Visibilidad</legend>
          {VISIBILITIES.map((v) => (
            <label key={v.value} className="flex items-start gap-2 text-sm">
              <input type="radio" value={v.value} {...register("visibilidad")} />
              <span>
                <span className="font-medium">{v.label}</span>
                <span className="text-muted-foreground ml-2 text-xs">{v.help}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="space-y-1">
          <label htmlFor="external_authors" className="text-sm font-medium">
            Coautores externos
          </label>
          <textarea
            id="external_authors"
            rows={2}
            placeholder="Uno por línea o separados por coma"
            className="w-full rounded-md border px-3 py-2 text-sm"
            {...register("external_authors")}
          />
        </div>

        <Controller
          name="coauthor_user_ids"
          control={control}
          render={({ field }) => (
            <CoauthorPicker value={field.value} onChange={field.onChange} />
          )}
        />

        <div className="space-y-1">
          <label htmlFor="main_file" className="text-sm font-medium">
            Archivo principal
          </label>
          <input
            id="main_file"
            type="file"
            accept=".pdf,.docx,.odt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm"
          />
        </div>

        {submitError && (
          <p role="alert" className="text-destructive text-sm">
            {submitError}
          </p>
        )}

        <Button type="submit" disabled={submitting}>
          Subir trabajo
        </Button>
      </form>
    </main>
  );
}
