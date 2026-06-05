import type { Metadata } from "next";

import { OverallBanner, StatusList, type Health } from "./StatusList";

export const metadata: Metadata = {
  title: "Estado del servicio",
  description: "Estado operativo de los servicios de BUSCASAM.",
  robots: { index: false },
};

// Live probe: must hit the API on every request, never prerender or cache.
export const dynamic = "force-dynamic";

function internalApiBase(): string {
  const internal = process.env.BUSCASAM_INTERNAL_API_URL;
  if (internal) return internal.replace(/\/$/, "");
  const fallback = process.env.BUSCASAM_API_URL ?? "http://127.0.0.1:8000";
  return `${fallback.replace(/\/$/, "")}/api`;
}

async function fetchHealth(): Promise<Health | null> {
  try {
    const r = await fetch(`${internalApiBase()}/health`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as Health;
  } catch {
    return null;
  }
}

export default async function EstadoPage() {
  const health = await fetchHealth();

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-[28px] font-semibold tracking-tight">
          Estado del servicio
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm leading-relaxed">
          Estado operativo de los servicios de BUSCASAM.
        </p>
      </div>

      <OverallBanner status={health?.status ?? null} />
      {health ? <StatusList services={health.services} /> : null}
    </main>
  );
}
