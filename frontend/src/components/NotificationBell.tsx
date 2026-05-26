"use client";

import { Bell } from "lucide-react";

import { useNotifications, useUnreadCount } from "@/lib/useNotifications";

import { BandejaPanel } from "./BandejaPanel";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export function NotificationBell() {
  const { count } = useUnreadCount();
  const { markAllRead } = useNotifications();

  return (
    <Popover
      onOpenChange={(open) => {
        if (open) markAllRead();
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Notificaciones"
          className="hover:bg-muted relative inline-flex size-8 items-center justify-center rounded-lg"
        >
          <Bell className="size-4" />
          {count > 0 && (
            <span className="bg-primary text-primary-foreground absolute -top-0.5 -right-0.5 inline-flex min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-medium">
              {count}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <BandejaPanel />
      </PopoverContent>
    </Popover>
  );
}
