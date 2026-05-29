"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { AttachmentsPanel } from "@/components/AttachmentsPanel";
import { CandidatePanel } from "@/components/CandidatePanel";
import { CoauthorsPanel } from "@/components/CoauthorsPanel";
import { VersionsPanel } from "@/components/VersionsPanel";
import { useUser } from "@/lib/useUser";
import {
  useDraftState,
  type DraftWorkspaceActions,
  type DraftState,
} from "../../useDraftState";

const VISIBILITIES = [
  { value: "publico", label: "Público" },
  { value: "interno", label: "Interno" },
  { value: "privado", label: "Privado" },
] as const;

const formSchema = z.object({
  titulo: z.string().min(1, "El título es obligatorio"),
  abstract: z.string(),
  keywords: z.string(),
  fecha: z.string(),
});

type FormValues = z.infer<typeof formSchema>;

export default function EditarPage() {
  const { user, isInvitado, isLoading: userLoading } = useUser();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const docId = Number(params.id);
  const { state, isLoading, refresh, actions } = useDraftState(docId);

  useEffect(() => {
    if (isInvitado) router.replace(`/login?next=/mis-trabajos/${docId}/editar`);
  }, [isInvitado, router, docId]);

  if (userLoading || isInvitado || !user) return null;
  if (isLoading || !state) return null;

  // Re-seed the form when the candidate's status changes (e.g. processing →
  // indexed): RHF captures defaultValues once at mount, so polled staged_*
  // would otherwise never reach the editable inputs.
  return (
    <EditarForm
      key={state.lifecycle.formSeedKey}
      docId={docId}
      state={state}
      refresh={refresh}
      actions={actions}
    />
  );
}

function EditarForm({
  docId,
  state,
  refresh,
  actions,
}: {
  docId: number;
  state: DraftState;
  refresh: () => Promise<void>;
  actions: DraftWorkspaceActions;
}) {
  const router = useRouter();
  const [publishing, setPublishing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { register, getValues, formState } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      titulo: state.title,
      abstract: state.staged_abstract ?? "",
      keywords: (state.staged_keywords ?? []).join(", "),
      fecha: state.staged_fecha ?? "",
    },
  });
  const { dirtyFields } = formState;

  async function patchField(field: keyof FormValues) {
    // Skip no-op blurs (e.g. tabbing through untouched fields).
    if (!dirtyFields[field]) return;
    const v = getValues();
    const body: Record<string, unknown> = {};
    if (field === "titulo") body.title = v.titulo;
    if (field === "abstract") body.abstract = v.abstract;
    if (field === "keywords")
      body.keywords = v.keywords
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    if (field === "fecha") body.fecha = v.fecha || null;
    const { error } = await api.PATCH("/api/documents/{doc_id}", {
      params: { path: { doc_id: docId } },
      body,
    });
    if (error) {
      toast.error("No se pudo guardar el cambio");
      return;
    }
    await refresh();
  }

  async function patchVisibility(visibility: string) {
    const { error } = await api.PATCH("/api/documents/{doc_id}", {
      params: { path: { doc_id: docId } },
      body: { visibility: visibility as DraftState["visibility"] },
    });
    if (error) {
      toast.error("No se pudo cambiar la visibilidad");
      return;
    }
    await refresh();
  }

  async function onPublish() {
    setPublishing(true);
    try {
      const result = await actions.publish();
      if (result === "published") {
        router.push("/mis-trabajos");
        return;
      }
      if (result === "publish_failed") {
        toast.error("No se pudo publicar");
      }
    } catch {
      toast.error("No se pudo publicar");
    } finally {
      setPublishing(false);
    }
  }

  async function onDelete() {
    setDeleting(true);
    try {
      const error = await actions.softDelete();
      if (error) {
        toast.error("No se pudo eliminar");
        return;
      }
      router.push("/mis-trabajos");
    } catch {
      toast.error("No se pudo eliminar");
    } finally {
      setDeleting(false);
    }
  }

  const { lifecycle } = state;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          Editar trabajo
        </h1>
        <span
          data-testid="status-pill"
          className="bg-muted rounded-full px-3 py-1 text-sm"
        >
          {lifecycle.statusLabel}
        </span>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
        <form className="space-y-4">
          <Field label="Título" htmlFor="titulo">
            <input
              id="titulo"
              className="w-full rounded-md border px-3 py-2 text-sm"
              {...register("titulo", { onBlur: () => patchField("titulo") })}
            />
          </Field>
          <Field label="Resumen" htmlFor="abstract">
            <textarea
              id="abstract"
              className="w-full rounded-md border px-3 py-2 text-sm"
              rows={5}
              {...register("abstract", {
                onBlur: () => patchField("abstract"),
              })}
            />
          </Field>
          <Field label="Palabras clave" htmlFor="keywords">
            <input
              id="keywords"
              className="w-full rounded-md border px-3 py-2 text-sm"
              placeholder="separadas por comas"
              {...register("keywords", {
                onBlur: () => patchField("keywords"),
              })}
            />
          </Field>
          <Field label="Fecha" htmlFor="fecha">
            <input
              id="fecha"
              type="date"
              className="w-full rounded-md border px-3 py-2 text-sm"
              {...register("fecha", { onBlur: () => patchField("fecha") })}
            />
          </Field>
          {/* Visibility is owner-only (ADR-0010 §8); accepted coautores edit
              metadata but cannot change who can read the trabajo. */}
          {state.isOwner && (
            <Field label="Visibilidad" htmlFor="visibility">
              <select
                id="visibility"
                className="w-full rounded-md border px-3 py-2 text-sm"
                defaultValue={state.visibility}
                onChange={(e) => patchVisibility(e.target.value)}
              >
                {VISIBILITIES.map((v) => (
                  <option key={v.value} value={v.value}>
                    {v.label}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </form>

        <section className="bg-muted/30 relative rounded-lg border p-4">
          <h2 className="text-muted-foreground text-sm font-medium">
            Sugerencias del extractor
          </h2>
          {lifecycle.showSuggestionsSpinner && (
            <div
              data-testid="suggestions-spinner"
              className="bg-background/60 absolute inset-0 flex items-center justify-center"
            >
              <Loader2 className="animate-spin" />
            </div>
          )}
          <dl className="mt-4 space-y-3 text-sm">
            <Suggestion label="Resumen" testId="suggestion-abstract">
              {state.staged_abstract || "—"}
            </Suggestion>
            <Suggestion label="Palabras clave" testId="suggestion-keywords">
              {(state.staged_keywords ?? []).join(", ") || "—"}
            </Suggestion>
            <Suggestion label="Fecha" testId="suggestion-fecha">
              {state.staged_fecha || "—"}
            </Suggestion>
          </dl>
        </section>
      </div>

      <div className="mt-8">
        <CandidatePanel candidate={state.candidate} actions={actions} />
      </div>

      <div className="mt-8">
        <VersionsPanel docId={docId} versions={state.versions} canManage />
      </div>

      <div className="mt-8">
        {/* The draft state only loads for manageable users (owner + accepted
            coauthors); reaching this page means the user can manage attachments. */}
        <AttachmentsPanel
          attachments={state.attachments}
          actions={actions.attachments}
          canManage
        />
      </div>

      <div className="mt-8">
        <CoauthorsPanel docId={docId} />
      </div>

      {/* Initial-publication affordance only. Once the doc has a published
          version (state.versions non-empty), CandidatePanel owns the
          candidate Publicar — keeping this here too would show two Publicar
          buttons and let a click re-publish the current version. */}
      {state.versions.length === 0 && (
        <div className="mt-8">
          <Button
            disabled={!lifecycle.canPublish || publishing}
            onClick={onPublish}
          >
            Publicar
          </Button>
          {lifecycle.gateMessage && (
            <p
              data-testid="gate-reason"
              className="text-muted-foreground mt-2 text-sm"
            >
              {lifecycle.gateMessage}
            </p>
          )}
        </div>
      )}

      {/* Eliminar is owner-only and lives only here (not on Mis trabajos rows),
          keeping the delete mutation single-copy (module map §Frontend Papelera). */}
      {state.isOwner && (
        <div className="mt-8 border-t pt-8">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={deleting}>
                Eliminar
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>¿Eliminar este trabajo?</AlertDialogTitle>
                <AlertDialogDescription>
                  El trabajo pasará a la papelera. Podés restaurarlo en
                  cualquier momento durante los próximos 180 días; pasado ese
                  plazo se eliminará de forma permanente.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleting}>
                  Cancelar
                </AlertDialogCancel>
                <AlertDialogAction
                  disabled={deleting}
                  onClick={(e) => {
                    e.preventDefault();
                    onDelete();
                  }}
                >
                  Eliminar
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </main>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}

function Suggestion({
  label,
  testId,
  children,
}: {
  label: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd data-testid={testId} className="mt-0.5">
        {children}
      </dd>
    </div>
  );
}
