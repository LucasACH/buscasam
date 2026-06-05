"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import confetti from "canvas-confetti";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Loader2,
  RotateCcw,
  Trash2,
} from "lucide-react";

import posthog from "posthog-js";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { TONE_CLASSES, type BadgeTone } from "@/components/StatusBadge";
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
import { AreaField } from "@/components/AreaField";
import { AttachmentsPanel } from "@/components/AttachmentsPanel";
import { CandidatePanel } from "@/components/CandidatePanel";
import { CoauthorsPanel } from "@/components/CoauthorsPanel";
import { DatePicker } from "@/components/DatePicker";
import { ProcessingSteps } from "@/components/ProcessingSteps";
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

const INPUT_CLASS =
  "h-10 w-full rounded-lg border border-border-strong bg-card px-3 text-sm outline-none transition hover:border-neutral-400 focus:border-primary focus:ring-[3px] focus:ring-primary-tint";

const STATUS_TONE: Record<string, BadgeTone> = {
  "Listo para publicar": "green",
  "Procesando…": "amber",
  "Falló el procesamiento": "red",
};

const formSchema = z.object({
  titulo: z.string().min(1, "El título es obligatorio"),
  abstract: z.string(),
  keywords: z.string(),
  fecha: z.string(),
  visibility: z.enum(["publico", "interno", "privado"]),
});

type FormValues = z.infer<typeof formSchema>;

type PublishPhase = "idle" | "publishing" | "done";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function fireConfetti() {
  const opts = { spread: 70, startVelocity: 45, ticks: 220, zIndex: 60 };
  confetti({ ...opts, particleCount: 90, origin: { x: 0.5, y: 0.62 } });
  confetti({
    ...opts,
    particleCount: 55,
    angle: 60,
    origin: { x: 0, y: 0.72 },
  });
  confetti({
    ...opts,
    particleCount: 55,
    angle: 120,
    origin: { x: 1, y: 0.72 },
  });
}

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
            className="mx-auto flex max-w-md flex-col items-center gap-5 py-16 text-center"
          >
            <div className="border-border bg-card w-full rounded-lg border p-7 text-left">
              <ProcessingSteps
                stage={state.lifecycle.stage}
                queued={state.lifecycle.queued}
              />
            </div>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Estamos procesando tu archivo. Esto puede tardar unos minutos.
              Podés cerrar esta página y volver más tarde: el trabajo sigue
              procesándose.
            </p>
          </div>
        ) : (
          <div
            data-testid="failed-block"
            className="border-border bg-card mx-auto flex max-w-md flex-col items-center gap-4 rounded-lg border px-6 py-12 text-center"
          >
            <div className="border-border bg-status-red-bg text-status-red-fg grid size-11 place-items-center rounded-lg border">
              <AlertTriangle className="size-5" strokeWidth={1.9} />
            </div>
            <p className="text-destructive text-sm leading-relaxed">
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

type PendingLeave = { type: "link"; href: string } | { type: "back" };

// Guards every way out of the page while the form is dirty: internal link
// clicks (back link, header, logo, …) and the browser Back button get the
// custom confirm dialog; reload, tab close and external URLs get the native
// prompt via beforeunload (browsers don't allow a custom dialog there).
function useLeaveGuard(isDirty: boolean) {
  const router = useRouter();
  const [pending, setPending] = useState<PendingLeave | null>(null);
  const leavingRef = useRef(false);
  const armedRef = useRef(false);

  useEffect(() => {
    if (!isDirty) return;
    // Sentinel entry: Back now pops to this same URL (a router no-op), which
    // lets us ask before actually leaving.
    window.history.pushState(null, "", window.location.href);
    armedRef.current = true;

    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (!(e.target instanceof Element)) return;
      const anchor = e.target.closest("a[href]");
      const href = anchor?.getAttribute("href");
      if (!href?.startsWith("/") || anchor?.getAttribute("target")) return;
      e.preventDefault();
      e.stopPropagation();
      setPending({ type: "link", href });
    };
    const onPopState = () => {
      armedRef.current = false; // Back consumed the sentinel
      if (!leavingRef.current) setPending({ type: "back" });
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onClick, true);
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("popstate", onPopState);
      // Form went clean (Save) while still here → pop the sentinel so Back
      // isn't a dead no-op. Skip when deliberately leaving (confirmLeave's
      // router.push / history.back already drive the stack).
      if (armedRef.current && !leavingRef.current) {
        armedRef.current = false;
        window.history.back();
      }
    };
  }, [isDirty]);

  function confirmLeave() {
    if (!pending) return;
    leavingRef.current = true;
    if (pending.type === "link") router.push(pending.href);
    else window.history.back();
    setPending(null);
  }

  function cancelLeave() {
    if (leavingRef.current || !pending) return;
    // The Back press consumed the sentinel; re-arm it for the next press.
    if (pending.type === "back") {
      window.history.pushState(null, "", window.location.href);
      armedRef.current = true;
    }
    setPending(null);
  }

  return { pending, confirmLeave, cancelLeave };
}

function LeaveGuardDialog({
  guard,
}: {
  guard: ReturnType<typeof useLeaveGuard>;
}) {
  return (
    <AlertDialog
      open={guard.pending !== null}
      onOpenChange={(open) => !open && guard.cancelLeave()}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Salir sin guardar?</AlertDialogTitle>
          <AlertDialogDescription>
            Tenés cambios sin guardar. Si salís ahora, se perderán.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Seguir editando</AlertDialogCancel>
          <AlertDialogAction onClick={guard.confirmLeave}>
            Salir sin guardar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
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
  const [publishPhase, setPublishPhase] = useState<PublishPhase>("idle");
  const [saving, setSaving] = useState(false);
  const { register, getValues, setValue, reset, control, formState } =
    useForm<FormValues>({
      resolver: zodResolver(formSchema),
      mode: "onBlur",
      defaultValues: {
        titulo: state.title,
        abstract: state.staged_abstract ?? "",
        keywords: (state.staged_keywords ?? []).join(", "),
        fecha: state.staged_fecha ?? "",
        visibility: state.visibility,
      },
    });
  const { dirtyFields, isDirty } = formState;
  const leaveGuard = useLeaveGuard(isDirty);

  // Persist every dirty field in one metadata PATCH. The Save button is only
  // enabled while isDirty, so at least one field is sent. visibility is gated
  // on isOwner (ADR-0010 §8); for coautores dirtyFields.visibility never sets.
  async function saveAll() {
    setSaving(true);
    const v = getValues();
    const body: Record<string, unknown> = {};
    if (dirtyFields.titulo) body.title = v.titulo;
    if (dirtyFields.abstract) body.abstract = v.abstract;
    if (dirtyFields.keywords)
      body.keywords = v.keywords
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    if (dirtyFields.fecha) body.fecha = v.fecha || null;
    if (dirtyFields.visibility) body.visibility = v.visibility;
    const { error } = await api.PATCH("/api/documents/{doc_id}", {
      params: { path: { doc_id: docId } },
      body,
    });
    if (error) {
      toast.error("No se pudieron guardar los cambios");
      setSaving(false);
      return;
    }
    // Clear dirty state without remounting (metadata edits don't re-seed).
    reset(v);
    await refresh();
    setSaving(false);
  }

  // Stage a generated field's extractor snapshot (issue #94) back into the
  // form; it persists on the next Save like any other edit. The form is not
  // re-seeded on metadata edits, so setValue keeps the visible input in sync.
  function restoreField(field: "abstract" | "keywords" | "fecha") {
    if (field === "abstract") {
      setValue("abstract", state.generated_abstract ?? "", {
        shouldDirty: true,
      });
    }
    if (field === "keywords") {
      setValue("keywords", (state.generated_keywords ?? []).join(", "), {
        shouldDirty: true,
      });
    }
    if (field === "fecha") {
      setValue("fecha", state.generated_fecha ?? "", { shouldDirty: true });
    }
  }

  async function onPublish() {
    setPublishPhase("publishing");
    try {
      // Hold the progress widget for at least 2s so the publish feels deliberate
      // rather than a flash before the redirect.
      const [result] = await Promise.all([actions.publish(), sleep(2000)]);
      if (result === "published") {
        posthog.capture("document_published", {
          doc_id: docId,
          visibility: state.visibility,
        });
        setPublishPhase("done");
        fireConfetti();
        await sleep(1600);
        router.push("/mis-trabajos");
        return;
      }
      setPublishPhase("idle");
      if (result === "publish_failed") {
        toast.error("No se pudo publicar");
      }
    } catch {
      setPublishPhase("idle");
      toast.error("No se pudo publicar");
    }
  }

  const { lifecycle } = state;

  // The prefilled inputs subsume the old suggestions panel; Restaurar appears
  // per field only while the live input diverges from the generated snapshot.
  // Driven off useWatch() (not staged_*) so it toggles on every keystroke rather
  // than waiting for the blur-time PATCH + refresh to land.
  const watched = useWatch({ control });
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
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <PageHeader
        statusLabel={lifecycle.statusLabel}
        publishedAt={lifecycle.publishedAt}
      />

      <form className="space-y-6">
        <Field label="Título" htmlFor="titulo">
          <input id="titulo" className={INPUT_CLASS} {...register("titulo")} />
        </Field>
        <AreaField areaPath={state.area_path} />
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
            className="border-border-strong bg-card focus:border-primary focus:ring-primary-tint min-h-24 w-full rounded-lg border px-3 py-[11px] text-sm leading-relaxed transition outline-none focus:ring-[3px]"
            rows={5}
            {...register("abstract")}
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
            className={INPUT_CLASS}
            placeholder="separadas por comas"
            {...register("keywords")}
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
          <div className="max-w-[260px]">
            <DatePicker
              id="fecha"
              value={watched.fecha ?? ""}
              onChange={(v) => setValue("fecha", v, { shouldDirty: true })}
            />
          </div>
        </Field>
        {/* Visibility is owner-only (ADR-0010 §8); accepted coautores edit
            metadata but cannot change who can read the trabajo. */}
        {state.isOwner && (
          <Field label="Visibilidad" htmlFor="visibility">
            <div className="relative max-w-[240px]">
              <select
                id="visibility"
                className={`${INPUT_CLASS} appearance-none pr-9`}
                {...register("visibility")}
              >
                {VISIBILITIES.map((v) => (
                  <option key={v.value} value={v.value}>
                    {v.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2" />
            </div>
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
        <div className="mt-8 flex flex-wrap items-center gap-3.5">
          <Button
            disabled={!lifecycle.canPublish || publishPhase !== "idle"}
            onClick={onPublish}
          >
            Publicar
          </Button>
          {lifecycle.gateMessage ? (
            <p
              data-testid="gate-reason"
              className="text-muted-foreground text-sm"
            >
              {lifecycle.gateMessage}
            </p>
          ) : (
            <span className="text-muted-foreground text-sm">
              Al publicar, el trabajo será visible según la visibilidad elegida.
            </span>
          )}
        </div>
      )}

      {/* Guardar cambios surfaces only while there's something to save; Eliminar
          is owner-only and lives only here (not on Mis trabajos rows), keeping the
          delete mutation single-copy (module map §Frontend Papelera). */}
      {(isDirty || state.isOwner) && (
        <div className="border-border mt-8 flex flex-wrap items-center gap-3 border-t pt-8">
          {isDirty && (
            <Button type="button" disabled={saving} onClick={saveAll}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              Guardar cambios
            </Button>
          )}
          {state.isOwner && <DeleteTrabajo softDelete={actions.softDelete} />}
        </div>
      )}

      <LeaveGuardDialog guard={leaveGuard} />

      {publishPhase !== "idle" && <PublishOverlay phase={publishPhase} />}
    </main>
  );
}

function PublishOverlay({ phase }: { phase: Exclude<PublishPhase, "idle"> }) {
  return (
    <div className="bg-background/70 fixed inset-0 z-50 flex [animation:overlay-in_.2s_ease-out] items-center justify-center backdrop-blur-sm">
      <div className="border-border bg-card flex w-[300px] flex-col items-center gap-5 rounded-2xl border px-8 py-10 text-center shadow-xl">
        <div className="grid size-16 place-items-center">
          {phase === "publishing" ? (
            <Loader2
              className="text-primary size-14 animate-spin"
              strokeWidth={1.5}
            />
          ) : (
            <div className="bg-status-green-bg text-status-green-fg grid size-16 [animation:publish-pop_.45s_cubic-bezier(.18,.89,.32,1.28)] place-items-center rounded-full">
              <CheckCircle2 className="size-9" strokeWidth={2} />
            </div>
          )}
        </div>
        <div className="space-y-1">
          <p className="text-base font-semibold">
            {phase === "publishing" ? "Publicando tu trabajo…" : "¡Publicado!"}
          </p>
          <p className="text-muted-foreground text-sm">
            {phase === "publishing"
              ? "Estamos haciendo visible tu trabajo."
              : "Te llevamos a Mis trabajos."}
          </p>
        </div>
      </div>
      <style>{`@keyframes overlay-in{from{opacity:0}to{opacity:1}}@keyframes publish-pop{0%{transform:scale(.4);opacity:0}60%{transform:scale(1.08)}100%{transform:scale(1);opacity:1}}`}</style>
    </div>
  );
}

function StatusPill({ label, tone }: { label: string; tone?: BadgeTone }) {
  const resolvedTone = tone ?? STATUS_TONE[label] ?? "neutral";
  return (
    <span
      data-testid="status-pill"
      className={`inline-flex h-[26px] items-center gap-1 rounded-full px-3 text-[13px] font-medium whitespace-nowrap ${TONE_CLASSES[resolvedTone]}`}
    >
      {label}
    </span>
  );
}

function BackLink() {
  return (
    <Link
      href="/mis-trabajos"
      className="text-muted-foreground hover:text-foreground mb-4 -ml-1 inline-flex items-center gap-1 text-[13px]"
    >
      <ChevronLeft className="size-4" />
      Mis trabajos
    </Link>
  );
}

function PageHeader({
  statusLabel,
  publishedAt = null,
}: {
  statusLabel: string;
  publishedAt?: string | null;
}) {
  return (
    <div className="mb-7">
      <BackLink />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-[28px] font-semibold tracking-tight">
          Editar trabajo
        </h1>
        {publishedAt ? (
          <StatusPill
            label={`Publicado el ${new Date(publishedAt).toLocaleDateString("es-AR")}`}
            tone="green"
          />
        ) : (
          <StatusPill label={statusLabel} />
        )}
      </div>
    </div>
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
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <PageHeader statusLabel={statusLabel} />
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
      posthog.capture("document_deleted");
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
        <Button
          variant="outline"
          disabled={deleting}
          className="border-destructive text-destructive hover:bg-destructive/5 hover:text-destructive"
        >
          <Trash2 className="size-3.5" strokeWidth={1.9} />
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
            className="bg-destructive border-transparent text-white hover:bg-[#b91c1c]"
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
      className="text-primary hover:text-primary-hover inline-flex items-center gap-1 text-xs hover:underline"
    >
      <RotateCcw className="size-3" strokeWidth={2} />
      Restaurar
    </button>
  );
}
