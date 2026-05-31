"use client";

import { Inbox } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { useNotifications } from "@/lib/useNotifications";

import { NotificationItem } from "./NotificationItem";

export function BandejaPanel() {
  const { items, isLoading, markAllRead } = useNotifications();
  const unread = items.filter((n) => n.read_at === null).length;

  return (
    <div className="flex flex-col">
      <div className="border-border flex items-center justify-between border-b px-3.5 py-3">
        <span className="text-sm font-semibold tracking-tight">
          Notificaciones
        </span>
        {unread > 0 && <StatusBadge tone="blue">{unread} sin leer</StatusBadge>}
      </div>

      {isLoading && items.length === 0 ? (
        <ul className="flex flex-col">
          {[0, 1, 2].map((i) => (
            <li
              key={i}
              className="border-border flex gap-2.5 border-b px-3.5 py-3"
            >
              <div className="bg-muted mt-px size-[17px] shrink-0 animate-pulse rounded" />
              <div className="flex flex-1 flex-col gap-1.5">
                <div className="bg-muted h-3 w-full animate-pulse rounded" />
                <div className="bg-muted h-3 w-2/3 animate-pulse rounded" />
              </div>
            </li>
          ))}
        </ul>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-3.5 py-8 text-center">
          <div className="border-border bg-neutral-100 text-muted-foreground/70 grid size-12 place-items-center rounded-lg border">
            <Inbox className="size-5" />
          </div>
          <p className="text-base font-semibold">No tenés notificaciones.</p>
        </div>
      ) : (
        <>
          <ul className="max-h-[380px] overflow-y-auto">
            {items.map((item) => (
              <NotificationItem key={item.id} item={item} />
            ))}
          </ul>
          {unread > 0 && (
            <div className="border-border border-t p-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => markAllRead()}
                className="w-full"
              >
                Marcar todas como leídas
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
