/* ============================================================
   BUSCASAM — Search view explorations (chatbot-inspired)
   Three refined directions on a design canvas.
   ============================================================ */

/* ---------- Derived sample data ---------- */
const MOST_READ = [
  { id: "d_8f2a1c", title: "Detección temprana de mal de Chagas mediante visión por computadora",
    authors: "M. Rodríguez · J. Pérez · L. Gómez", area: "ECyT", tipo: "Tesis", year: 2024, reads: "1.243" },
  { id: "d_3b9e07", title: "Modelos de lenguaje para corpus en español rioplatense",
    authors: "A. Ferreyra · C. Bianchi", area: "ECyT", tipo: "Paper", year: 2025, reads: "986" },
  { id: "d_5c1f88", title: "Estudio de microplásticos en la cuenca del Río Reconquista",
    authors: "P. Sosa · R. Medina · F. Aguirre", area: "EHyS", tipo: "Informe técnico", year: 2023, reads: "742" },
  { id: "d_7a44d2", title: "Optimización de rutas de recolección de residuos con algoritmos genéticos",
    authors: "D. Ledesma", area: "EHyS", tipo: "Proyecto final", year: 2024, reads: "531" },
];

const TRENDING = [
  { term: "visión por computadora", count: 48 },
  { term: "modelos de lenguaje", count: 41 },
  { term: "microplásticos", count: 33 },
  { term: "algoritmos genéticos", count: 27 },
  { term: "probióticos", count: 19 },
  { term: "política monetaria", count: 16 },
];

const SUGGESTED = [
  "visión por computadora en medicina",
  "modelos de lenguaje en español",
  "microplásticos en el Reconquista",
  "algoritmos genéticos",
];

const INDEX_COUNT = "12.480";

/* ---------- Shared pieces ---------- */

// The BUSCASAM search glyph, standalone (for greeting flourish)
function Mark({ size = 30, tone = "var(--primary)" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" fill="none" style={{ display: "block" }}>
      <rect width="26" height="26" rx="7.5" fill={tone} />
      <circle cx="11" cy="11" r="4.4" stroke="#fff" strokeWidth="2.1" />
      <path d="M14.4 14.4 18.5 18.5" stroke="#fff" strokeWidth="2.1" strokeLinecap="round" />
    </svg>
  );
}

function ArrowUp({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V6" /><path d="m6 12 6-6 6 6" />
    </svg>
  );
}

// Minimal static chrome so each frame reads as a real screen
function MockHeader() {
  return (
    <div style={{
      height: 60, padding: "0 26px", display: "flex", alignItems: "center",
      justifyContent: "space-between", borderBottom: "1px solid var(--border)",
      background: "rgba(255,255,255,0.8)", backdropFilter: "blur(8px)",
    }}>
      <Wordmark />
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", fontWeight: 500 }}>Mis trabajos</span>
        <span className="avatar">SM</span>
      </div>
    </div>
  );
}

// The hero composer — the chatbot-style input. `tall` gives the multiline feel.
function Composer({ placeholder = "Buscá un tema, título o autor…", value = "", tall = true, footnote }) {
  return (
    <div style={{ width: "100%" }}>
      <div className="xpl-composer" data-tall={tall ? "true" : "false"}>
        <div className="xpl-composer__text">
          {value
            ? <span style={{ color: "var(--fg)" }}>{value}</span>
            : <span style={{ color: "var(--fg-subtle)" }}>{placeholder}</span>}
        </div>
        <div className="xpl-composer__bar">
          <span className="xpl-composer__hint">
            <span className="mono" style={{ fontSize: 11, color: "var(--fg-subtle)" }}>↩</span>
            <span style={{ fontSize: 12, color: "var(--fg-subtle)" }}>para buscar</span>
          </span>
          <button className="xpl-send" aria-label="Buscar" tabIndex={-1}>
            <ArrowUp size={19} />
          </button>
        </div>
      </div>
      {footnote && (
        <div style={{ textAlign: "center", marginTop: 12, fontSize: 12, color: "var(--fg-subtle)" }}>
          {footnote}
        </div>
      )}
    </div>
  );
}

function Greeting({ size = "lg", subtitle = "¿Qué querés investigar hoy?" }) {
  const px = size === "lg" ? 40 : 32;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
      <Mark size={size === "lg" ? 34 : 28} />
      <h1 style={{
        fontSize: px, fontWeight: 600, letterSpacing: "-0.035em", lineHeight: 1.05,
        color: "var(--fg)", margin: size === "lg" ? "20px 0 0" : "16px 0 0",
      }}>
        Buenas tardes, Sofía
      </h1>
      {subtitle && (
        <p style={{ fontSize: 17, color: "var(--fg-muted)", margin: "10px 0 0", letterSpacing: "-0.01em" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}

// ============================================================
// VARIATION 1 — "Prompt"  (Claude / ChatGPT energy)
// Greeting + big composer + suggested prompt chips + slim most-read
// ============================================================
function VarPrompt() {
  return (
    <div className="xpl-screen">
      <MockHeader />
      <div className="xpl-stage">
        <div className="xpl-col" style={{ maxWidth: 660 }}>
          <Greeting />

          <div style={{ width: "100%", marginTop: 30 }}>
            <Composer footnote={<>Buscando en <b style={{ color: "var(--fg-muted)", fontWeight: 600 }}>{INDEX_COUNT}</b> trabajos de la comunidad UNSAM</>} />
          </div>

          {/* suggested prompts */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 22 }}>
            {SUGGESTED.map(s => (
              <button key={s} className="xpl-suggest">
                <span className="mono" style={{ color: "var(--primary)", fontSize: 12 }}>↗</span>
                {s}
              </button>
            ))}
          </div>

          {/* slim most-read */}
          <div style={{ width: "100%", marginTop: 44 }}>
            <div className="xpl-eyebrow">
              <span>Más leídos esta semana</span>
              <span className="xpl-eyebrow__link">Ver todo</span>
            </div>
            <div style={{ marginTop: 6 }}>
              {MOST_READ.slice(0, 3).map((d, i) => (
                <div key={d.id} className="xpl-readrow">
                  <span className="xpl-rank">{i + 1}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="xpl-readrow__title">{d.title}</div>
                    <div className="xpl-readrow__meta">{d.area} · {d.tipo} · {d.year}</div>
                  </div>
                  <span className="xpl-reads"><b>{d.reads}</b> lecturas</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// VARIATION 2 — "Discover"
// Composer hero + two quiet panels: Tendencias | Más leídos
// ============================================================
function VarDiscover() {
  const max = TRENDING[0].count;
  return (
    <div className="xpl-screen">
      <MockHeader />
      <div className="xpl-stage" style={{ paddingTop: 40 }}>
        <div className="xpl-col" style={{ maxWidth: 880 }}>
          <Greeting size="sm" subtitle="Buscá en la producción académica de la UNSAM" />

          <div style={{ width: "100%", maxWidth: 640, marginTop: 24 }}>
            <Composer />
          </div>

          {/* two panels */}
          <div className="xpl-panels">
            {/* Tendencias */}
            <section className="xpl-panel">
              <div className="xpl-panel__head">
                <span>Tendencias</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--fg-subtle)", textTransform: "none" }}>7 días</span>
              </div>
              <div>
                {TRENDING.map((t, i) => (
                  <button key={t.term} className="xpl-trend">
                    <span className="xpl-trend__rank mono">{String(i + 1).padStart(2, "0")}</span>
                    <span className="xpl-trend__term">{t.term}</span>
                    <span className="xpl-trend__bar">
                      <span style={{ width: (t.count / max * 100) + "%" }} />
                    </span>
                    <span className="xpl-trend__count mono">{t.count}</span>
                  </button>
                ))}
              </div>
            </section>

            {/* Más leídos */}
            <section className="xpl-panel">
              <div className="xpl-panel__head">
                <span>Más leídos</span>
                <span className="xpl-eyebrow__link" style={{ textTransform: "none", letterSpacing: 0 }}>Ver todo</span>
              </div>
              <div>
                {MOST_READ.map((d, i) => (
                  <div key={d.id} className="xpl-discover-read">
                    <span className="xpl-rank">{i + 1}</span>
                    <div style={{ minWidth: 0 }}>
                      <div className="xpl-discover-read__title">{d.title}</div>
                      <div className="xpl-readrow__meta">{d.authors}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// VARIATION 3 — "Editorial"  (quiet, expensive, reading-list)
// Composer + understated inline trending + generous most-read list
// ============================================================
function VarEditorial() {
  return (
    <div className="xpl-screen">
      <MockHeader />
      <div className="xpl-stage" style={{ paddingTop: 52 }}>
        <div className="xpl-col" style={{ maxWidth: 680 }}>
          <Greeting subtitle={null} />
          <p style={{ fontSize: 17, color: "var(--fg-muted)", margin: "12px 0 0", letterSpacing: "-0.01em", textAlign: "center" }}>
            Encontrá tesis, papers e informes de la comunidad UNSAM.
          </p>

          <div style={{ width: "100%", marginTop: 30 }}>
            <Composer />
          </div>

          {/* inline trending — understated text links */}
          <div style={{ marginTop: 18, fontSize: 13, color: "var(--fg-subtle)", textAlign: "center", lineHeight: 1.9 }}>
            <span style={{ marginRight: 4 }}>Tendencias</span>
            {TRENDING.slice(0, 5).map((t, i) => (
              <React.Fragment key={t.term}>
                <span className="xpl-inline-dot">·</span>
                <button className="xpl-inline-link">{t.term}</button>
              </React.Fragment>
            ))}
          </div>

          {/* editorial most-read */}
          <div style={{ width: "100%", marginTop: 46 }}>
            <div className="xpl-eyebrow" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12, marginBottom: 4 }}>
              <span>Lo más leído</span>
              <span className="xpl-eyebrow__link">Explorar el catálogo</span>
            </div>
            <div>
              {MOST_READ.map((d, i) => (
                <div key={d.id} className="xpl-edit-row">
                  <span className="xpl-edit-num mono">{String(i + 1).padStart(2, "0")}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="xpl-edit-title">{d.title}</div>
                    <div className="xpl-readrow__meta" style={{ marginTop: 4 }}>{d.authors} · {d.year}</div>
                  </div>
                  <span className="xpl-reads" style={{ alignSelf: "center" }}><b>{d.reads}</b></span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Canvas
// ============================================================
function ExploreApp() {
  const W = 1120, H = 860;
  return (
    <DesignCanvas>
      <DCSection id="search" title="Vista de búsqueda — exploraciones" subtitle="Estilo chatbot · pantalla única centrada · neutros + azul">
        <DCArtboard id="v1" label="1 · Prompt" width={W} height={H}><VarPrompt /></DCArtboard>
        <DCArtboard id="v2" label="2 · Discover" width={W} height={H}><VarDiscover /></DCArtboard>
        <DCArtboard id="v3" label="3 · Editorial" width={W} height={H}><VarEditorial /></DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<ExploreApp />);
