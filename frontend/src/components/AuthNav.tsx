"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown, LogOut } from "lucide-react";

import { api } from "@/api/client";
import { cn } from "@/lib/utils";
import { NOTIFICATIONS_QUERY_KEY } from "@/lib/useNotifications";
import { ME_QUERY_KEY, useUser, type User } from "@/lib/useUser";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

import { GoogleIcon } from "./GoogleIcon";
import { NotificationBell } from "./NotificationBell";

const ROLE_LABEL: Record<User["role"], string> = {
  estudiante: "Estudiante",
  docente: "Docente",
};

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "relative py-1.5 text-sm tracking-tight transition-colors",
        active
          ? "text-foreground font-semibold"
          : "text-muted-foreground hover:text-foreground font-medium",
      )}
    >
      {children}
      {active && (
        <span className="bg-primary absolute -bottom-[14px] left-0 right-0 h-0.5 rounded-full" />
      )}
    </Link>
  );
}

export function AuthNav() {
  const { user, isInvitado, isLoading } = useUser();
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const qc = useQueryClient();

  if (isLoading) {
    return (
      <div className="flex items-center gap-5" aria-hidden>
        <span className="h-4 w-20 animate-pulse rounded bg-neutral-200" />
        <span className="size-5 animate-pulse rounded-full bg-neutral-200" />
        <span className="flex items-center gap-2 py-1 pr-1.5 pl-1">
          <span className="size-8 animate-pulse rounded-full bg-neutral-200" />
          <span className="flex flex-col gap-1">
            <span className="h-3.5 w-28 animate-pulse rounded bg-neutral-200" />
            <span className="h-2.5 w-16 animate-pulse rounded bg-neutral-200" />
          </span>
        </span>
      </div>
    );
  }

  if (isInvitado) {
    return (
      <nav className="flex items-center gap-2">
        <Link
          href={`/login?next=${encodeURIComponent(pathname)}`}
          className="bg-primary text-primary-foreground hover:bg-primary-hover inline-flex h-[38px] items-center gap-2 rounded-lg px-4 text-sm font-medium tracking-tight transition-colors"
        >
          <GoogleIcon size={17} variant="mono" />
          Iniciar sesión con UNSAM
        </Link>
      </nav>
    );
  }

  if (!user) return null;

  async function onLogout() {
    await api.POST("/api/auth/logout");
    qc.setQueryData(ME_QUERY_KEY, null);
    // Drop the prior user's notifications so a next login can't flash them
    // (the count key is a prefix of NOTIFICATIONS_QUERY_KEY, removed too).
    qc.removeQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    router.replace("/");
  }

  return (
    <nav className="flex items-center gap-5">
      <NavLink href="/mis-trabajos" active={pathname.startsWith("/mis-trabajos")}>
        Mis trabajos
      </NavLink>
      {user.role === "docente" && (
        <NavLink href="/moderacion" active={pathname.startsWith("/moderacion")}>
          Moderación
        </NavLink>
      )}
      <NotificationBell />
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-2 rounded-lg py-1 pr-1.5 pl-1 transition-colors hover:bg-neutral-100"
          >
            {user.picture_url ? (
              <Image
                src={user.picture_url}
                alt=""
                width={32}
                height={32}
                className="size-8 rounded-full"
                unoptimized
              />
            ) : (
              <span
                aria-hidden
                className="bg-primary-tint text-primary-hover inline-flex size-8 items-center justify-center rounded-full text-[13px] font-semibold"
              >
                {user.name.slice(0, 1).toUpperCase()}
              </span>
            )}
            <span className="text-left leading-tight">
              <span className="block text-sm font-semibold whitespace-nowrap">
                {user.name}
              </span>
              <span className="text-muted-foreground block text-[11px] whitespace-nowrap">
                {ROLE_LABEL[user.role]}
              </span>
            </span>
            <ChevronDown className="text-muted-foreground size-[15px]" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[284px] p-0">
          <div className="border-border border-b px-3.5 py-3">
            <div className="text-sm font-semibold">{user.name}</div>
            <div className="text-muted-foreground mt-0.5 text-[11px]">
              {user.email}
            </div>
          </div>
          <div className="p-1.5">
            <button
              type="button"
              onClick={onLogout}
              className="text-foreground hover:bg-neutral-100 flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors"
            >
              <LogOut className="size-4" />
              Cerrar sesión
            </button>
          </div>
        </PopoverContent>
      </Popover>
    </nav>
  );
}
