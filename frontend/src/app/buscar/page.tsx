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

type SearchParams = Record<string, string | string[] | undefined>;

function has(sp: SearchParams, key: string): boolean {
  const v = sp[key];
  return Array.isArray(v) ? v.length > 0 : v != null && v !== "";
}

export default async function BuscarPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const isLanding =
    !has(sp, "q") &&
    sp.orden !== "recientes" &&
    !has(sp, "area") &&
    !has(sp, "tipo") &&
    !has(sp, "desde") &&
    !has(sp, "hasta");

  const queryClient = new QueryClient();
  // Areas back both the filter tree and the breadcrumb labels in either view;
  // the most-read ranking only renders on the landing.
  await Promise.all([
    queryClient.prefetchQuery({ queryKey: ["areas"], queryFn: fetchAreas }),
    isLanding
      ? queryClient.prefetchQuery({
          queryKey: ["popular"],
          queryFn: fetchPopular,
        })
      : Promise.resolve(),
  ]);

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <BuscarClient />
    </HydrationBoundary>
  );
}
