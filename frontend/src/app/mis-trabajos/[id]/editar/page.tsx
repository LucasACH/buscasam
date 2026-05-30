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

  // Initial-publication path: until the first version finishes indexing, block
  // all interaction behind a single loading state. The work runs server-side,
  // so the author can leave and return; polling unblocks the page automatically.
  if (state.lifecycle.initialPhase !== "ready") {
    return (
      <BlockedShell statusLabel={state.lifecycle.statusLabel}>
        {state.lifecycle.initialPhase === "indexing" ? (
          <div
            data-testid="indexing-block"
            className="flex flex-col items-center gap-4 py-24 text-center"
          >
            <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
            <p className="text-muted-foreground max-w-md text-sm">
              Estamos procesando tu archivo. Esto puede tardar unos minutos.
              Podés cerrar esta página y volver más tarde: el trabajo sigue
              procesándose.
            </p>
          </div>
        ) : (
          <div
            data-testid="failed-block"
            className="flex flex-col items-center gap-4 py-24 text-center"
          >
            <p className="text-destructive max-w-md text-sm">
              {state.lifecycle.gateMessage ?? "Falló el procesamiento"}
            </p>
            {state.isOwner && <DeleteTrabajo softDelete={actions.softDelete} />}
          </div>
        )}
      </BlockedShell>
    );
  }

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
  const { register, getValues, setValue, watch, formState } = useForm<FormValues>({
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

  // Revert a single generated field back to the extractor's immutable snapshot
  // and persist it through the same metadata PATCH (issue #94). The form is not
  // re-seeded on metadata edits, so setValue keeps the visible input in sync.
  async function restoreField(field: "abstract" | "keywords" | "fecha") {
    const body: Record<string, unknown> = {};
    if (field === "abstract") {
      const value = state.generated_abstract ?? "";
      setValue("abstract", value, { shouldDirty: true });
      body.abstract = value;
    }
    if (field === "keywords") {
      const value = state.generated_keywords ?? [];
      setValue("keywords", value.join(", "), { shouldDirty: true });
      body.keywords = value;
    }
    if (field === "fecha") {
      setValue("fecha", state.generated_fecha ?? "", { shouldDirty: true });
      body.fecha = state.generated_fecha ?? null;
    }
    const { error } = await api.PATCH("/api/documents/{doc_id}", {
      params: { path: { doc_id: docId } },
      body,
    });
    if (error) {
      toast.error("No se pudo restaurar el valor del extractor");
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

  const { lifecycle } = state;

  // The prefilled inputs subsume the old suggestions panel; Restaurar appears
  // per field only while the live input diverges from the generated snapshot.
  // Driven off watch() (not staged_*) so it toggles on every keystroke rather
  // than waiting for the blur-time PATCH + refresh to land.
  const watched = watch();
  const canRestoreAbstract =
    state.generated_abstract != null &&
    (watched.abstract ?? "") !== state.generated_abstract;
  const canRestoreKeywords =
    state.generated_keywords != null &&
    state.generated_keywords.length > 0 &&
    !keywordsEqual(
      (watched.keywords ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      state.generated_keywords,
    );
  const canRestoreFecha =
    state.generated_fecha != null &&
    (watched.fecha ?? "") !== state.generated_fecha;

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

      <form className="mt-8 space-y-4">
        <Field label="Título" htmlFor="titulo">
          <input
            id="titulo"
            className="w-full rounded-md border px-3 py-2 text-sm"
            {...register("titulo", { onBlur: () => patchField("titulo") })}
          />
        </Field>
        <Field
          label="Resumen"
          htmlFor="abstract"
          action={
            canRestoreAbstract && (
              <Restaurar
                testId="restore-abstract"
                onClick={() => restoreField("abstract")}
              />
            )
          }
        >
          <textarea
            id="abstract"
            className="w-full rounded-md border px-3 py-2 text-sm"
            rows={5}
            {...register("abstract", {
              onBlur: () => patchField("abstract"),
            })}
          />
        </Field>
        <Field
          label="Palabras clave"
          htmlFor="keywords"
          action={
            canRestoreKeywords && (
              <Restaurar
                testId="restore-keywords"
                onClick={() => restoreField("keywords")}
              />
            )
          }
        >
          <input
            id="keywords"
            className="w-full rounded-md border px-3 py-2 text-sm"
            placeholder="separadas por comas"
            {...register("keywords", {
              onBlur: () => patchField("keywords"),
            })}
          />
        </Field>
        <Field
          label="Fecha"
          htmlFor="fecha"
          action={
            canRestoreFecha && (
              <Restaurar
                testId="restore-fecha"
                onClick={() => restoreField("fecha")}
              />
            )
          }
        >
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

      {/* Pre-publish, the initial version matches the candidate predicate and
          its staged metadata equals the form fields above (always). The panel
          is only meaningful for replacements, so render it once published. */}
      {state.versions.length > 0 && (
        <div className="mt-8">
          <CandidatePanel candidate={state.candidate} actions={actions} />
        </div>
      )}

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
          <DeleteTrabajo softDelete={actions.softDelete} />
        </div>
      )}
    </main>
  );
}

function BlockedShell({
  statusLabel,
  children,
}: {
  statusLabel: string;
  children: React.ReactNode;
}) {
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
          {statusLabel}
        </span>
      </div>
      {children}
    </main>
  );
}

function DeleteTrabajo({
  softDelete,
}: {
  softDelete: DraftWorkspaceActions["softDelete"];
}) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  async function onDelete() {
    setDeleting(true);
    try {
      const error = await softDelete();
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

  return (
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
            El trabajo pasará a la papelera. Podés restaurarlo en cualquier
            momento durante los próximos 180 días; pasado ese plazo se eliminará
            de forma permanente.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancelar</AlertDialogCancel>
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
  );
}

function keywordsEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}

function Field({
  label,
  htmlFor,
  action,
  children,
}: {
  label: string;
  htmlFor: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label htmlFor={htmlFor} className="text-sm font-medium">
          {label}
        </label>
        {action}
      </div>
      {children}
    </div>
  );
}

function Restaurar({
  testId,
  onClick,
}: {
  testId: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className="text-primary text-xs hover:underline"
    >
      Restaurar
    </button>
  );
}
