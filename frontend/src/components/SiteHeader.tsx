"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthNav } from "@/components/AuthNav";
import { Wordmark } from "@/components/Wordmark";

export function SiteHeader() {
  const pathname = usePathname();
  if (pathname === "/login") return null;

  return (
    <header className="border-border sticky top-0 z-50 border-b bg-background/85 backdrop-blur-md backdrop-saturate-150">
      <div className="mx-auto flex h-15 w-full max-w-[1120px] items-center justify-between gap-4 px-6">
        <Link href="/buscar" aria-label="BUSCASAM — inicio">
          <Wordmark />
        </Link>
        <AuthNav />
      </div>
    </header>
  );
}
