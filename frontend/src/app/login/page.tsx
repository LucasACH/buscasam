"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";

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
    <main className="mx-auto flex w-full max-w-md flex-col items-center gap-6 px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">BUSCASAM</h1>

      {isNotUnsam ? (
        <>
          <p className="text-muted-foreground text-center text-sm">
            Solo cuentas @unsam.edu.ar o @estudiantes.unsam.edu.ar pueden
            ingresar.
          </p>
          <Button asChild>
            <a href={LOGIN_HREF}>Probar otra cuenta</a>
          </Button>
        </>
      ) : (
        <Button asChild>
          <a href={LOGIN_HREF}>Iniciar sesión con UNSAM</a>
        </Button>
      )}
    </main>
  );
}
