"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, Search } from "lucide-react";

import { GoogleIcon } from "@/components/GoogleIcon";
import { Wordmark } from "@/components/Wordmark";

const LOGIN_HREF = `/api/auth/login?next=${encodeURIComponent("/buscar")}`;

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const params = useSearchParams();
  const isNotUnsam = params.get("error") === "not_unsam";

  return (
    <main className="grid min-h-[100dvh] place-items-center px-5 py-8">
      <div className="flex w-full max-w-[400px] flex-col items-center gap-5 text-center">
        <Wordmark size="lg" />
        <p className="text-muted-foreground max-w-[320px] text-base leading-snug">
          Búsqueda de trabajos académicos de la comunidad UNSAM.
        </p>

        {isNotUnsam && (
          <div
            role="alert"
            className="bg-destructive/5 flex w-full gap-2.5 rounded-lg border border-red-200 px-3.5 py-3 text-left"
          >
            <AlertTriangle className="text-destructive mt-px size-[17px] shrink-0" />
            <span className="text-[13px] leading-relaxed text-red-900">
              Solo cuentas{" "}
              <span className="font-mono">@unsam.edu.ar</span>,{" "}
              <span className="font-mono">@estudiantes.unsam.edu.ar</span> o{" "}
              <span className="font-mono">@unsam-bue.edu.ar</span> pueden
              ingresar.
            </span>
          </div>
        )}

        <a
          href={LOGIN_HREF}
          className="bg-primary text-primary-foreground hover:bg-primary-hover mt-1 inline-flex h-[46px] w-full items-center justify-center gap-2.5 rounded-lg text-base font-medium transition-colors"
        >
          <GoogleIcon size={20} variant="mono" />
          {isNotUnsam ? "Probar otra cuenta" : "Iniciar sesión con UNSAM"}
        </a>

        <p className="text-muted-foreground/70 mt-1 text-[11px]">
          Acceso institucional mediante Google · UNSAM
        </p>

        <div className="my-0.5 flex w-full items-center gap-3">
          <span className="bg-border h-px flex-1" />
          <span className="text-muted-foreground/70 text-[11px]">o</span>
          <span className="bg-border h-px flex-1" />
        </div>

        <Link
          href="/buscar"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-[7px] text-sm font-medium transition-colors"
        >
          <Search className="size-[15px]" />
          Explorar trabajos públicos sin iniciar sesión
        </Link>
      </div>
    </main>
  );
}
