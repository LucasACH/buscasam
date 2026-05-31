"use client";

import {
  AlertTriangle,
  EyeOff,
  RotateCcw,
  UserPlus,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCoauthorInvitation } from "@/lib/useCoauthorInvitation";
import { useNotifications, type NotificationDTO } from "@/lib/useNotifications";

type CoauthorInvite = { doc_title?: string; inviter?: string; doc_id?: number };
type DocumentHidden = { doc_title?: string; reason?: string };
type DocumentUnhidden = { doc_title?: string; note?: string };
type ProcessingFailed = { doc_title?: string };

// Payloads come from out-of-scope producer PRDs (#3/#5/#8); degrade gracefully
// rather than render the literal "undefined" if a field is missing.
const FALLBACK_TITLE = "sin título";

const KIND_ICON: Record<NotificationDTO["kind"], LucideIcon> = {
  coauthor_invite: UserPlus,
  document_hidden: EyeOff,
  document_unhidden: RotateCcw,
  processing_failed: AlertTriangle,
};

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
    <div className="flex flex-col gap-1">
      <p className="text-foreground text-[13px] leading-snug">
        <span className="font-medium">{payload.inviter ?? "Alguien"}</span> te
        invitó como coautor en{" "}
        <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title>.
      </p>
      {unread && docId != null && (
        <div className="mt-2 flex gap-1.5">
          <Button
            type="button"
            size="sm"
            onClick={() => accept(docId)}
          >
            Aceptar
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => decline(docId)}
          >
            Rechazar
          </Button>
          <Button asChild size="sm" variant="ghost">
            <a href={`/docs/${docId}`}>Ver</a>
          </Button>
        </div>
      )}
    </div>
  );
}

function DocumentHiddenItem({ payload }: { payload: DocumentHidden }) {
  return (
    <p className="text-foreground text-[13px] leading-snug">
      Tu documento <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title> fue
      ocultado.
      {payload.reason ? (
        <span className="text-muted-foreground"> Motivo: {payload.reason}</span>
      ) : (
        ""
      )}
    </p>
  );
}

function DocumentUnhiddenItem({ payload }: { payload: DocumentUnhidden }) {
  return (
    <p className="text-foreground text-[13px] leading-snug">
      Tu documento <Title>{payload.doc_title ?? FALLBACK_TITLE}</Title> fue
      restaurado.
      {payload.note ? (
        <span className="text-muted-foreground"> {payload.note}</span>
      ) : (
        ""
      )}
    </p>
  );
}

function ProcessingFailedItem({ payload }: { payload: ProcessingFailed }) {
  return (
    <p className="text-foreground text-[13px] leading-snug">
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
  const Icon = KIND_ICON[item.kind];
  return (
    <li
      className={`border-border relative flex gap-2.5 border-b px-3.5 py-3 ${unread ? "bg-primary-tint" : ""}`}
    >
      {unread && (
        <span className="bg-primary absolute top-0 bottom-0 left-0 w-[3px]" />
      )}
      {Icon && (
        <Icon className="text-muted-foreground mt-px size-[17px] shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        {renderBody(item, unread)}
        {unread && (
          <div className="mt-1.5 flex items-center gap-3">
            <button
              type="button"
              onClick={() => markRead(item.id)}
              className="text-muted-foreground hover:text-foreground text-[11px]"
            >
              Marcar como leída
            </button>
          </div>
        )}
      </div>
    </li>
  );
}
