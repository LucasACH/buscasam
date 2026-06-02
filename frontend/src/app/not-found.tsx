import { Search } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto grid min-h-[calc(100dvh-60px)] w-full max-w-[560px] place-items-center px-6 py-8">
      <div className="flex flex-col items-center text-center">
        <p className="text-primary text-[15px] font-semibold tracking-wide">
          404
        </p>
        <h1 className="mt-2 text-[32px] leading-[1.1] font-semibold tracking-[-0.02em]">
          Página no encontrada
        </h1>
        <p className="text-muted-foreground mt-3 text-[15px] leading-relaxed">
          La página que buscás no existe o fue movida.
        </p>
        <Button asChild className="mt-6">
          <Link href="/buscar">
            <Search data-icon="inline-start" />
            Ir al buscador
          </Link>
        </Button>
      </div>
    </main>
  );
}
