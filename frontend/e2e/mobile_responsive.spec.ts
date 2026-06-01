import { expect, test, type Page } from "@playwright/test";

import { setMockRoute } from "./mock-helpers";

// Mobile layout audit: drive every reliably-renderable view at phone
// viewports, assert no horizontal overflow, and screenshot full-page for
// visual review. Run with:
//   pnpm exec playwright test e2e/mobile_responsive.spec.ts
// Screenshots land in test-results/mobile/.
const VIEWPORTS = [
  { name: "sm-360", width: 360, height: 740 },
  { name: "lg-414", width: 414, height: 896 },
] as const;

const DOC_ID = 42;

const USER = {
  user_id: 7,
  role: "docente",
  name: "Ada Lovelace",
  email: "ada@unsam.edu.ar",
  picture_url: null,
  hd: "unsam.edu.ar",
};

const AREAS = [
  { area_path: "escuela_ciencia", display_name: "Escuela de Ciencia y Tecnología" },
  { area_path: "escuela_ciencia.cyt", display_name: "Ciencia y Tecnología" },
  {
    area_path: "escuela_ciencia.cyt.ciencia_datos",
    display_name: "Ciencia de Datos",
  },
  {
    area_path: "escuela_ciencia.cyt.ciencia_datos.analisis2",
    display_name: "Análisis Matemático Multivariable Avanzado",
  },
];

// Deep breadcrumb + long unbreakable tokens — the shape that actually overflows
// on a phone, so the layout regression is caught instead of waved through.
const DEEP_AREA = "escuela_ciencia.cyt.ciencia_datos.analisis2";

const RESULTS = {
  results: Array.from({ length: 5 }).map((_, i) => ({
    doc_id: i + 1,
    titulo: "Un título de trabajo académico bastante largo para probar el wrap",
    fecha: "2023-05-01",
    area_path: "escuela_ciencia.carrera_informatica",
    tipo: "tesis",
    abstract: "Resumen de ejemplo ".repeat(8),
    autores: [{ display_name: "Ada Lovelace", user_id: 7 }],
  })),
  total: 5,
  saturated: false,
  unfiltered_total: null,
  lexical_fallback: false,
};

const OWN_DOCS = [
  {
    id: 11,
    title: "Redes neuronales aplicadas a la detección temprana de fallas",
    publication_status: "published",
    visibility: "publico",
    published_at: "2024-01-01T00:00:00Z",
    moderation_hidden: false,
  },
  {
    id: 12,
    title: "Borrador sin publicar",
    publication_status: "draft",
    visibility: "privado",
    published_at: null,
    moderation_hidden: false,
  },
];

const DELETED_DOCS = [
  {
    id: 13,
    title: "Trabajo eliminado pendiente de purga",
    publication_status: "draft",
    purge_at: "2026-07-01T00:00:00Z",
  },
];

const QUEUE = [
  {
    doc_id: 21,
    report_id: 31,
    title: "Documento con varios reportes acumulados para revisión",
    reasons: ["spam", "contenido duplicado"],
    first_reported_at: "2026-05-01T00:00:00Z",
    last_reported_at: "2026-05-20T00:00:00Z",
    report_count: 3,
  },
];

const DOC_DETAIL = {
  view: "detail",
  doc_id: DOC_ID,
  titulo: "Búsqueda híbrida en repositorios académicos",
  autores: [{ display_name: "Ada Lovelace", user_id: 7 }],
  area_path: DEEP_AREA,
  tipo: "tesis",
  fecha: "2024-03-15",
  visibility: "publico",
  abstract:
    "Este trabajo práctico de Análisis II aborda la aplicación de cálculo " +
    "diferencial multivariable. Se analiza la función g(x,y) = (x+y)^3 + " +
    "(x-y)^2, resolviendo ejercicios en puntos como Q=(0, -2) y P=(0,1). " +
    "Resumen del trabajo. ".repeat(20),
  palabras_clave: ["recuperación de información", "embeddings", "trigramas"],
  // Long unbreakable strings (filename, email) are the other half of the
  // overflow class — they must truncate, not push the grid track wide.
  archivo_principal: {
    original_filename: "informe-final-analisis-multivariable-version-definitiva.pdf",
    size_bytes: 2048,
    mime: "application/pdf",
  },
  adjuntos: [
    {
      id: 101,
      original_filename: "datos-experimentales-completos-2024.csv",
      size_bytes: 512,
      mime: "text/csv",
    },
  ],
  owner_email: "lucasachavalrodriguez@estudiantes.unsam.edu.ar",
  versions: [],
  manageable: false,
};

function json(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

// Catch-all for browser-side /api/** calls. `authed` toggles /api/me between a
// docente session and the 401 (invitado) state.
async function installApiMocks(page: Page, authed: boolean) {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/api/me")) {
      return authed
        ? route.fulfill(json(USER))
        : route.fulfill({ status: 401, body: "" });
    }
    if (path.includes("/api/notifications")) return route.fulfill(json({ items: [], count: 0 }));
    if (path.includes("/api/search")) return route.fulfill(json(RESULTS));
    if (path.includes("/api/me/documents/deleted")) return route.fulfill(json(DELETED_DOCS));
    if (path.endsWith("/api/me/documents")) return route.fulfill(json(OWN_DOCS));
    if (path.includes("/api/moderation/queue")) return route.fulfill(json({ items: QUEUE }));
    if (path.includes("/api/areas")) return route.fulfill(json(AREAS));
    if (path.includes("/api/users/search")) return route.fulfill(json([]));
    if (path.includes("/related")) return route.fulfill(json([]));
    return route.fulfill(json({}));
  });
}

async function noHScroll(page: Page) {
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow (px)").toBeLessThanOrEqual(0);
}

type Case = {
  name: string;
  path: string;
  authed: boolean;
  ready: (page: Page) => Promise<unknown>;
  ssr?: (page: Page) => Promise<void>;
};

const CASES: Case[] = [
  {
    name: "login",
    path: "/login",
    authed: false,
    ready: (p) => p.getByRole("button").first().waitFor(),
  },
  {
    name: "buscar-guest-empty",
    path: "/buscar",
    authed: false,
    ready: (p) => p.getByRole("link", { name: /Iniciar sesión/i }).waitFor(),
  },
  {
    name: "buscar-guest-results",
    path: "/buscar?q=fisica",
    authed: false,
    ready: (p) => p.getByText(/resultado/i).first().waitFor(),
  },
  {
    name: "buscar-authed",
    path: "/buscar?q=fisica",
    authed: true,
    ready: (p) => p.getByRole("button", { name: /Ada Lovelace/i }).waitFor(),
  },
  {
    name: "docs-detail",
    path: `/docs/${DOC_ID}`,
    authed: false,
    ssr: async () => {
      await setMockRoute({ path: "/api/areas", status: 200, body: AREAS });
      await setMockRoute({ path: `/api/docs/${DOC_ID}`, status: 200, body: DOC_DETAIL });
    },
    ready: (p) => p.getByText(DOC_DETAIL.titulo).waitFor(),
  },
  {
    name: "mis-trabajos",
    path: "/mis-trabajos",
    authed: true,
    ready: (p) => p.getByText(OWN_DOCS[0].title).waitFor(),
  },
  {
    name: "mis-trabajos-nuevo",
    path: "/mis-trabajos/nuevo",
    authed: true,
    ready: (p) => p.getByRole("button").first().waitFor(),
  },
  {
    name: "mis-trabajos-papelera",
    path: "/mis-trabajos/papelera",
    authed: true,
    ready: (p) => p.getByText(DELETED_DOCS[0].title).waitFor(),
  },
  {
    name: "moderacion",
    path: "/moderacion",
    authed: true,
    ready: (p) => p.getByText(QUEUE[0].title).waitFor(),
  },
];

for (const vp of VIEWPORTS) {
  test.describe(`mobile ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const c of CASES) {
      test(c.name, async ({ page }) => {
        await installApiMocks(page, c.authed);
        if (c.ssr) await c.ssr(page);
        await page.goto(c.path);
        await c.ready(page);
        await page.screenshot({
          path: `test-results/mobile/${vp.name}-${c.name}.png`,
          fullPage: true,
        });
        await noHScroll(page);
      });
    }
  });
}
