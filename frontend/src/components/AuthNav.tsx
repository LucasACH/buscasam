"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";

import { NOTIFICATIONS_QUERY_KEY } from "@/lib/useNotifications";
import { ME_QUERY_KEY, useUser, type User } from "@/lib/useUser";

import { NotificationBell } from "./NotificationBell";

const ROLE_LABEL: Record<User["role"], string> = {
  estudiante: "Estudiante",
  docente: "Docente",
};

export function AuthNav() {
  const { user, isInvitado } = useUser();
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const qc = useQueryClient();

  if (isInvitado) {
    return (
      <nav className="flex items-center gap-2">
        <Link
          href={`/login?next=${encodeURIComponent(pathname)}`}
          className="text-sm font-medium underline-offset-4 hover:underline"
        >
          Iniciar sesión con UNSAM
        </Link>
      </nav>
    );
  }

  if (!user) return null;

  async function onLogout() {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    qc.setQueryData(ME_QUERY_KEY, null);
    // Drop the prior user's notifications so a next login can't flash them
    // (the count key is a prefix of NOTIFICATIONS_QUERY_KEY, removed too).
    qc.removeQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    router.replace("/");
  }

  return (
    <nav className="flex items-center gap-3">
      <NotificationBell />
      {user.picture_url ? (
        <Image
          src={user.picture_url}
          alt=""
          width={28}
          height={28}
          className="rounded-full"
          unoptimized
        />
      ) : (
        <span
          aria-hidden
          className="bg-muted inline-flex size-7 items-center justify-center rounded-full text-xs"
        >
          {user.name.slice(0, 1).toUpperCase()}
        </span>
      )}
      <span className="text-sm font-medium">{user.name}</span>
      <span className="text-muted-foreground text-xs">
        {ROLE_LABEL[user.role]}
      </span>
      <button
        type="button"
        onClick={onLogout}
        className="text-sm underline-offset-4 hover:underline"
      >
        Cerrar sesión
      </button>
    </nav>
  );
}
