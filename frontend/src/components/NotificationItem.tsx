"use client";

import { useCoauthorInvitation } from "@/lib/useCoauthorInvitation";
import { useNotifications, type NotificationDTO } from "@/lib/useNotifications";

type CoauthorInvite = { doc_title?: string; inviter?: string; doc_id?: number };
type DocumentHidden = { doc_title?: string; reason?: string };
type DocumentUnhidden = { doc_title?: string; note?: string };
type ProcessingFailed = { doc_title?: string };

// Payloads come from out-of-scope producer PRDs (#3/#5/#8); degrade gracefully
// rather than render the literal "undefined" if a field is missing.
const FALLBACK_TITLE = "sin título";

function Title({ children }: { children: React.ReactNode }) {
  return <span className="text-foreground font-medium">«{children}»</span>;
}

function CoauthorInviteItem({
  payload,
  unread,
}: {
  payload: CoauthorInvite;
  unread: boolean;
}) {
  const { accept, decline } = useCoauthorInvitation();
  const docId = payload.doc_id;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>
        <span className="font-medium">{payload.inviter ?? "Alguien"}</span> te
        invitó como coautor en{" "}
        <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title>.
      </p>
      {unread && docId != null && (
        <div className="flex items-center gap-3 text-xs">
          <button
            type="button"
            onClick={() => accept(docId)}
            className="text-foreground font-medium underline-offset-4 hover:underline"
          >
            Aceptar
          </button>
          <button
            type="button"
            onClick={() => decline(docId)}
            className="text-muted-foreground underline-offset-4 hover:underline"
          >
            Rechazar
          </button>
          <a
            href={`/docs/${docId}`}
            className="text-muted-foreground underline-offset-4 hover:underline"
          >
            Ver
          </a>
        </div>
      )}
    </div>
  );
}

function DocumentHiddenItem({ payload }: { payload: DocumentHidden }) {
  return (
    <p className="text-sm">
      Tu documento <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title> fue
      ocultado.{payload.reason ? ` Motivo: ${payload.reason}` : ""}
    </p>
  );
}

function DocumentUnhiddenItem({ payload }: { payload: DocumentUnhidden }) {
  return (
    <p className="text-sm">
      Tu documento <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title> fue
      restaurado.{payload.note ? ` ${payload.note}` : ""}
    </p>
  );
}

function ProcessingFailedItem({ payload }: { payload: ProcessingFailed }) {
  return (
    <p className="text-sm">
      Falló el procesamiento de{" "}
      <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title>.
    </p>
  );
}

function renderBody(item: NotificationDTO, unread: boolean) {
  const payload = item.payload;
  switch (item.kind) {
    case "coauthor_invite":
      return <CoauthorInviteItem payload={payload} unread={unread} />;
    case "document_hidden":
      return <DocumentHiddenItem payload={payload} />;
    case "document_unhidden":
      return <DocumentUnhiddenItem payload={payload} />;
    case "processing_failed":
      return <ProcessingFailedItem payload={payload} />;
    default:
      return null;
  }
}

export function NotificationItem({ item }: { item: NotificationDTO }) {
  const { markRead } = useNotifications();
  const unread = item.read_at === null;
  return (
    <li
      className={`flex flex-col gap-1 px-3 py-2 ${unread ? "bg-muted/40" : ""}`}
    >
      {renderBody(item, unread)}
      {unread && (
        <button
          type="button"
          onClick={() => markRead(item.id)}
          className="text-muted-foreground self-start text-xs underline-offset-4 hover:underline"
        >
          Marcar como leída
        </button>
      )}
    </li>
  );
}
