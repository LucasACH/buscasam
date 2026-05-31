"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { api } from "@/api/client";
import { useUser } from "@/lib/useUser";
import { AreasCascader } from "@/components/AreasCascader";
import { CoauthorPicker } from "@/components/CoauthorPicker";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  Plus,
  Upload,
  X,
} from "lucide-react";

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
  external_authors: z.array(
    z.object({
      name: z.string().min(1, "El nombre es obligatorio"),
      surname: z.string().min(1, "El apellido es obligatorio"),
      email: z.string().email("Email inválido"),
    }),
  ),
  coauthor_user_ids: z.array(z.number()),
});

type FormValues = z.infer<typeof formSchema>;

function titleCase(s: string): string {
  return s.toLowerCase().replace(/\b\p{L}/gu, (c) => c.toUpperCase());
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
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      titulo: "",
      area_path: "",
      tipo: "tesis",
      visibilidad: "publico",
      external_authors: [],
      coauthor_user_ids: [],
    },
  });

  const externalAuthors = useFieldArray({ control, name: "external_authors" });

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
          external_authors: values.external_authors.map((a) => ({
            name: titleCase(a.name.trim()),
            surname: titleCase(a.surname.trim()),
            email: a.email.trim(),
          })),
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

  const inputClass =
    "h-10 w-full rounded-lg border border-border-strong bg-card px-3 text-sm outline-none hover:border-neutral-400 focus:border-primary focus:ring-[3px] focus:ring-primary-tint transition";

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <Link
        href="/mis-trabajos"
        className="-ml-1 mb-4 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        Mis trabajos
      </Link>

      <h1 className="text-[28px] font-semibold tracking-tight">Nuevo trabajo</h1>

      <form className="mt-7 space-y-6" onSubmit={handleSubmit(onSubmit)}>
        <div className="space-y-1.5">
          <label htmlFor="titulo" className="text-sm font-medium">
            Título <span className="text-destructive">*</span>
          </label>
          <input id="titulo" className={inputClass} {...register("titulo")} />
          {errors.titulo && (
            <p className="flex items-center gap-1.5 text-[13px] text-destructive">
              <AlertTriangle className="size-3.5" />
              {errors.titulo.message}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <span className="text-sm font-medium">
            Área <span className="text-destructive">*</span>
          </span>
          <Controller
            name="area_path"
            control={control}
            render={({ field }) => (
              <div className="overflow-hidden rounded-lg border border-border bg-card">
                <AreasCascader
                  value={field.value || null}
                  onChange={(area) => field.onChange(area ?? "")}
                />
              </div>
            )}
          />
          {errors.area_path && (
            <p className="flex items-center gap-1.5 text-[13px] text-destructive">
              <AlertTriangle className="size-3.5" />
              {errors.area_path.message}
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <label htmlFor="tipo" className="text-sm font-medium">
            Tipo <span className="text-destructive">*</span>
          </label>
          <div className="relative">
            <select
              id="tipo"
              className={`${inputClass} appearance-none pr-9`}
              {...register("tipo")}
            >
              {DOCUMENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          </div>
        </div>

        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium">Visibilidad</legend>
          <div className="flex flex-col gap-2">
            {VISIBILITIES.map((v) => (
              <label
                key={v.value}
                className="flex cursor-pointer items-start gap-3 rounded-lg border border-border-strong bg-card px-3.5 py-3 text-sm hover:border-neutral-400 has-[:checked]:border-primary has-[:checked]:bg-primary-tint transition"
              >
                <input
                  type="radio"
                  value={v.value}
                  className="mt-0.5 accent-[var(--primary)]"
                  {...register("visibilidad")}
                />
                <span>
                  <span className="block font-semibold">{v.label}</span>
                  <span className="mt-0.5 block text-[13px] text-muted-foreground">
                    {v.help}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="space-y-2.5">
          <span className="block text-sm font-medium">Coautores externos</span>
          {externalAuthors.fields.map((row, i) => (
            <div key={row.id} className="space-y-1">
              <div className="flex items-start gap-2">
                <div className="flex-1 space-y-1.5">
                  <input
                    placeholder="Nombre"
                    className={inputClass}
                    {...register(`external_authors.${i}.name`, {
                      onBlur: (e) =>
                        setValue(
                          `external_authors.${i}.name`,
                          titleCase(e.target.value.trim()),
                        ),
                    })}
                  />
                  {errors.external_authors?.[i]?.name && (
                    <p className="flex items-center gap-1.5 text-[13px] text-destructive">
                      <AlertTriangle className="size-3.5" />
                      {errors.external_authors[i]?.name?.message}
                    </p>
                  )}
                </div>
                <div className="flex-1 space-y-1.5">
                  <input
                    placeholder="Apellido"
                    className={inputClass}
                    {...register(`external_authors.${i}.surname`, {
                      onBlur: (e) =>
                        setValue(
                          `external_authors.${i}.surname`,
                          titleCase(e.target.value.trim()),
                        ),
                    })}
                  />
                  {errors.external_authors?.[i]?.surname && (
                    <p className="flex items-center gap-1.5 text-[13px] text-destructive">
                      <AlertTriangle className="size-3.5" />
                      {errors.external_authors[i]?.surname?.message}
                    </p>
                  )}
                </div>
                <div className="flex-[1.4] space-y-1.5">
                  <input
                    type="email"
                    placeholder="Email"
                    className={inputClass}
                    {...register(`external_authors.${i}.email`)}
                  />
                  {errors.external_authors?.[i]?.email && (
                    <p className="flex items-center gap-1.5 text-[13px] text-destructive">
                      <AlertTriangle className="size-3.5" />
                      {errors.external_authors[i]?.email?.message}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => externalAuthors.remove(i)}
                  className="grid size-10 flex-none place-items-center rounded-lg text-muted-foreground hover:bg-neutral-100 hover:text-destructive transition"
                  aria-label="Quitar coautor externo"
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              externalAuthors.append({ name: "", surname: "", email: "" })
            }
          >
            <Plus className="size-3.5" />
            Agregar coautor externo
          </Button>
        </div>

        <Controller
          name="coauthor_user_ids"
          control={control}
          render={({ field }) => (
            <CoauthorPicker value={field.value} onChange={field.onChange} />
          )}
        />

        <div className="space-y-1.5">
          <label htmlFor="main_file" className="text-sm font-medium">
            Archivo principal <span className="text-destructive">*</span>
          </label>
          <label
            htmlFor="main_file"
            className="flex cursor-pointer flex-col items-center rounded-lg border-[1.5px] border-dashed border-border-strong bg-neutral-50 px-6 py-8 text-center hover:border-neutral-400 hover:bg-neutral-100 transition"
          >
            <span className="grid size-11 place-items-center rounded-lg border border-border bg-card text-primary">
              <Upload className="size-5" />
            </span>
            <span className="mt-3 text-sm font-medium">
              {file ? file.name : "Arrastrá tu archivo o hacé clic para elegir"}
            </span>
            <span className="mt-1 text-[11px] text-muted-foreground">
              PDF, DOCX u ODT · hasta 50 MB
            </span>
            <input
              id="main_file"
              type="file"
              accept=".pdf,.docx,.odt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="sr-only"
            />
          </label>
        </div>

        {submitError && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-3 text-sm text-destructive"
          >
            <AlertTriangle className="mt-0.5 size-4 flex-none" />
            <span>{submitError}</span>
          </div>
        )}

        <Button type="submit" disabled={submitting}>
          Subir trabajo
        </Button>
      </form>
    </main>
  );
}
