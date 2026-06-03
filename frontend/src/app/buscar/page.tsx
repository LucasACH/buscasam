import type { Metadata } from "next";

import { BuscarClient } from "./BuscarClient";

// Canonical strips query params (q/area/tipo/pagina) so filtered/search states
// don't fragment into thousands of near-duplicate indexable URLs.
export const metadata: Metadata = {
  title: "Trabajos académicos de la UNSAM",
  description:
    "Buscá tesis, papers, monografías, trabajos prácticos y proyectos de investigación de la comunidad de la Universidad Nacional de San Martín (UNSAM).",
  alternates: { canonical: "/buscar" },
  openGraph: { url: "/buscar", images: ["/opengraph-image"] },
};

// No server prefetch: reading searchParams would force dynamic rendering and a
// no-store header (breaks bfcache), while prefetching unconditionally bakes
// empty data into the static prerender at build time. The client fetches areas
// and the most-read ranking fresh on mount, so the page stays a cacheable
// static shell and the data is always live.
export default function BuscarPage() {
  return <BuscarClient />;
}
