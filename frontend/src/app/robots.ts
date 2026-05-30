import type { MetadataRoute } from "next";

// ADR-0004 §3. Crawlers may index public pages; authenticated/management
// surfaces are disallowed. The sitemap lists only `publico` documents.
function publicBase(): string {
  return (process.env.BUSCASAM_BASE_URL ?? "http://localhost:3000").replace(
    /\/$/,
    "",
  );
}

export default function robots(): MetadataRoute.Robots {
  const base = publicBase();
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/api/", "/mis-trabajos/", "/moderacion/", "/login"],
    },
    sitemap: `${base}/sitemap.xml`,
  };
}
