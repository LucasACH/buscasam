import type { Metadata } from "next";
import {
  HydrationBoundary,
  QueryClient,
  dehydrate,
} from "@tanstack/react-query";

import { BuscarClient } from "./BuscarClient";
import { fetchAreas, fetchPopular } from "./fetchLanding";

// Canonical strips query params (q/area/tipo/pagina) so filtered/search states
// don't fragment into thousands of near-duplicate indexable URLs.
export const metadata: Metadata = {
  title: "Trabajos académicos de la UNSAM",
  description:
    "Buscá tesis, papers, monografías, trabajos prácticos y proyectos de investigación de la comunidad de la Universidad Nacional de San Martín (UNSAM).",
  alternates: { canonical: "/buscar" },
  openGraph: { url: "/buscar", images: ["/opengraph-image"] },
};

export default async function BuscarPage() {
  const queryClient = new QueryClient();
  // Areas back both the filter tree and the breadcrumb labels; the most-read
  // ranking only renders on the landing. Both are prefetched unconditionally so
  // the route stays static (reading searchParams would force dynamic rendering
  // and a no-store header, which disables bfcache); the popular query is
  // ISR-cached, so prefetching it on the results view is cheap and unused.
  await Promise.all([
    queryClient.prefetchQuery({ queryKey: ["areas"], queryFn: fetchAreas }),
    queryClient.prefetchQuery({ queryKey: ["popular"], queryFn: fetchPopular }),
  ]);

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <BuscarClient />
    </HydrationBoundary>
  );
}
