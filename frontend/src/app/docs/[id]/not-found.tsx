import { FileX } from "lucide-react";

export default function DocNotFound() {
  return (
    <main className="mx-auto grid min-h-[calc(100dvh-60px)] w-full max-w-3xl place-items-center px-6 py-8">
      <div className="flex flex-col items-center text-center">
        <div className="text-muted-foreground/70 grid size-12 place-items-center rounded-lg border border-border bg-neutral-100">
          <FileX size={22} />
        </div>
        <h1 className="mt-4 text-base font-semibold">
          No encontramos este documento
        </h1>
        <p className="text-muted-foreground mt-1.5 max-w-[340px] text-sm">
          Puede que haya sido eliminado, o que no tengas permiso para verlo.
        </p>
      </div>
    </main>
  );
}
