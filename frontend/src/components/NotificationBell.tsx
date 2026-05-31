"use client";

import { Bell } from "lucide-react";

import { usePrefetchNotifications, useUnreadCount } from "@/lib/useNotifications";

import { BandejaPanel } from "./BandejaPanel";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export function NotificationBell() {
  const { count } = useUnreadCount();
  usePrefetchNotifications();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Notificaciones"
          className="hover:bg-muted relative inline-flex size-8 items-center justify-center rounded-lg"
        >
          <Bell className="size-4" />
          {count > 0 && (
            <span className="bg-primary text-primary-foreground border-background absolute top-1 right-1 inline-flex h-[17px] min-w-[17px] items-center justify-center rounded-full border-2 px-1 text-[10px] font-bold">
              {count > 9 ? "9+" : count}
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
