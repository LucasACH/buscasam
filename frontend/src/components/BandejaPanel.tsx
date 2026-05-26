"use client";

import { useNotifications } from "@/lib/useNotifications";

import { NotificationItem } from "./NotificationItem";

export function BandejaPanel() {
  const { items, markAllRead } = useNotifications();
  const anyUnread = items.some((n) => n.read_at === null);

  if (items.length === 0) {
    return (
      <p className="text-muted-foreground px-3 py-6 text-center text-sm">
        No tenés notificaciones.
      </p>
    );
  }

  return (
    <div className="flex flex-col">
      <ul className="divide-border max-h-80 divide-y overflow-y-auto">
        {items.map((item) => (
          <NotificationItem key={item.id} item={item} />
        ))}
      </ul>
      {anyUnread && (
        <div className="border-border border-t p-2">
          <button
            type="button"
            onClick={() => markAllRead()}
            className="text-primary w-full text-sm underline-offset-4 hover:underline"
          >
            Marcar todas como leídas
          </button>
        </div>
      )}
    </div>
  );
}
