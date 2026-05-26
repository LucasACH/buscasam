"use client";

import { useNotifications, type NotificationDTO } from "@/lib/useNotifications";

type CoauthorInvite = { doc_title?: string; inviter?: string };
type DocumentHidden = { doc_title?: string; reason?: string };
type DocumentUnhidden = { doc_title?: string; note?: string };
type ProcessingFailed = { doc_title?: string };

function Title({ children }: { children: React.ReactNode }) {
  return <span className="text-foreground font-medium">«{children}»</span>;
}

function CoauthorInviteItem({ payload }: { payload: CoauthorInvite }) {
  return (
    <p className="text-sm">
      <span className="font-medium">{payload.inviter}</span> te invitó como
      coautor en <Title>{payload.doc_title}</Title>.
    </p>
  );
}

function DocumentHiddenItem({ payload }: { payload: DocumentHidden }) {
  return (
    <p className="text-sm">
      Tu documento <Title>{payload.doc_title}</Title> fue ocultado. Motivo:{" "}
      {payload.reason}
    </p>
  );
}

function DocumentUnhiddenItem({ payload }: { payload: DocumentUnhidden }) {
  return (
    <p className="text-sm">
      Tu documento <Title>{payload.doc_title}</Title> fue restaurado.{" "}
      {payload.note}
    </p>
  );
}

function ProcessingFailedItem({ payload }: { payload: ProcessingFailed }) {
  return (
    <p className="text-sm">
      Falló el procesamiento de <Title>{payload.doc_title}</Title>.
    </p>
  );
}

function renderBody(item: NotificationDTO) {
  const payload = item.payload;
  switch (item.kind) {
    case "coauthor_invite":
      return <CoauthorInviteItem payload={payload} />;
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
      {renderBody(item)}
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
