"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import posthog from "posthog-js";

import { api } from "@/api/client";
import { useUser } from "@/lib/useUser";
import { AreasCascader } from "@/components/AreasCascader";
import { CoauthorPicker } from "@/components/CoauthorPicker";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  Info,
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
  const [fileHintOpen, setFileHintOpen] = useState(false);

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
        setSubmitError(
          detail ?? "No se pudo crear el borrador. Revisá los datos.",
        );
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
        posthog.capture("document_created", {
          doc_id: id,
          tipo: values.tipo,
          visibilidad: values.visibilidad,
          has_external_authors: values.external_authors.length > 0,
          has_coauthors: values.coauthor_user_ids.length > 0,
        });
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
        className="text-muted-foreground hover:text-foreground mb-4 -ml-1 inline-flex items-center gap-1 text-[13px]"
      >
        <ChevronLeft className="size-4" />
        Mis trabajos
      </Link>

      <h1 className="text-[28px] font-semibold tracking-tight">
        Nuevo trabajo
      </h1>

      <form className="mt-7 space-y-6" onSubmit={handleSubmit(onSubmit)}>
        <div className="space-y-1.5">
          <label htmlFor="titulo" className="text-sm font-medium">
            Título <span className="text-destructive">*</span>
          </label>
          <input id="titulo" className={inputClass} {...register("titulo")} />
          {errors.titulo && (
            <p className="text-destructive flex items-center gap-1.5 text-[13px]">
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
              <div className="border-border bg-card overflow-hidden rounded-lg border">
                <AreasCascader
                  value={field.value || null}
                  onChange={(area) => field.onChange(area ?? "")}
                />
              </div>
            )}
          />
          {errors.area_path && (
            <p className="text-destructive flex items-center gap-1.5 text-[13px]">
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
            <ChevronDown className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2" />
          </div>
        </div>

        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium">Visibilidad</legend>
          <div className="flex flex-col gap-2">
            {VISIBILITIES.map((v) => (
              <label
                key={v.value}
                className="border-border-strong bg-card has-[:checked]:border-primary has-[:checked]:bg-primary-tint flex cursor-pointer items-start gap-3 rounded-lg border px-3.5 py-3 text-sm transition hover:border-neutral-400"
              >
                <input
                  type="radio"
                  value={v.value}
                  className="mt-0.5 accent-[var(--primary)]"
                  {...register("visibilidad")}
                />
                <span>
                  <span className="block font-semibold">{v.label}</span>
                  <span className="text-muted-foreground mt-0.5 block text-[13px]">
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
                    <p className="text-destructive flex items-center gap-1.5 text-[13px]">
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
                    <p className="text-destructive flex items-center gap-1.5 text-[13px]">
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
                    <p className="text-destructive flex items-center gap-1.5 text-[13px]">
                      <AlertTriangle className="size-3.5" />
                      {errors.external_authors[i]?.email?.message}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => externalAuthors.remove(i)}
                  className="text-muted-foreground hover:text-destructive grid size-10 flex-none place-items-center rounded-lg transition hover:bg-neutral-100"
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
          <span className="flex items-center gap-1.5 text-sm font-medium">
            Archivo principal <span className="text-destructive">*</span>
            <Tooltip
              open={fileHintOpen}
              onOpenChange={setFileHintOpen}
              delayDuration={0}
            >
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Más información sobre el archivo principal"
                  className="text-muted-foreground hover:text-foreground inline-flex"
                  onClick={() => setFileHintOpen((o) => !o)}
                >
                  <Info className="size-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                Subí el documento principal del trabajo. Una vez procesado, vas
                a poder sumar archivos adicionales (anexos, datasets, código)
                desde la edición.
              </TooltipContent>
            </Tooltip>
          </span>
          <label
            htmlFor="main_file"
            className="border-border-strong flex cursor-pointer flex-col items-center rounded-lg border-[1.5px] border-dashed bg-neutral-50 px-6 py-8 text-center transition hover:border-neutral-400 hover:bg-neutral-100"
          >
            <span className="border-border bg-card text-primary grid size-11 place-items-center rounded-lg border">
              <Upload className="size-5" />
            </span>
            <span className="mt-3 text-sm font-medium">
              {file ? file.name : "Arrastrá tu archivo o hacé clic para elegir"}
            </span>
            <span className="text-muted-foreground mt-1 text-[11px]">
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
            className="border-destructive/30 bg-destructive/5 text-destructive flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm"
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
