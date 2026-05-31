/* ============================================================
   BUSCASAM — Login + Search landing (hero)
   ============================================================ */

function Login({ error, navigate, onLogin, onGuest }) {
  return (
    <div style={{ minHeight: "100dvh", display: "grid", placeItems: "center", padding: "32px 20px", background: "var(--background)" }}>
      <div className="rise" style={{ width: "100%", maxWidth: 400, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 22 }}>
        <Wordmark size="lg" />
        <p style={{ fontSize: "var(--text-lg)", color: "var(--fg-muted)", lineHeight: 1.45, margin: 0, maxWidth: 320 }}>
          Búsqueda de trabajos académicos de la comunidad UNSAM.
        </p>

        {error && (
          <div role="alert" style={{
            display: "flex", gap: 10, textAlign: "left", width: "100%",
            background: "var(--danger-tint)", border: "1px solid #fecaca",
            borderRadius: "var(--r-base)", padding: "12px 14px",
          }}>
            <Icon name="alert-triangle" size={17} stroke={2} style={{ color: "var(--danger)", flex: "none", marginTop: 1 }} />
            <span style={{ fontSize: "var(--text-meta)", color: "#7f1d1d", lineHeight: 1.5 }}>
              Solo cuentas <span className="mono">@unsam.edu.ar</span>, <span className="mono">@estudiantes.unsam.edu.ar</span> o <span className="mono">@unsam-bue.edu.ar</span> pueden ingresar.
            </span>
          </div>
        )}

        <button className="btn btn--primary btn--lg btn--block" onClick={onLogin} style={{ marginTop: 4 }}>
          <GoogleG size={20} mono />
          {error ? "Probar otra cuenta" : "Iniciar sesión con UNSAM"}
        </button>

        <p style={{ fontSize: 11, color: "var(--fg-subtle)", margin: 0, marginTop: 4 }}>
          Acceso institucional mediante Google · UNSAM
        </p>

        {onGuest && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12, width: "100%", margin: "2px 0" }}>
              <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
              <span style={{ fontSize: 11, color: "var(--fg-subtle)" }}>o</span>
              <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
            </div>
            <button className="linkish" onClick={onGuest}
              style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "var(--text-sm)", fontWeight: 500, color: "var(--fg-muted)", display: "inline-flex", alignItems: "center", gap: 7 }}>
              <Icon name="search" size={15} stroke={2} /> Explorar trabajos públicos sin iniciar sesión
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/* ---- Search landing helpers (chatbot-style "Prompt" direction) ---- */
const SUGGESTED = [
  "visión por computadora",
  "modelos de lenguaje",
  "microplásticos",
  "algoritmos genéticos",
];
// pseudo "reads this week" per doc id — drives the Más leídos ranking
const HOME_READS = {
  d_8f2a1c: 1243, d_3b9e07: 986, d_4f81c0: 712, d_5c1f88: 742,
  d_7a44d2: 531, d_2e90b5: 410, d_9d12af: 388, d_6b23e9: 140,
};
const HOME_INDEX = "12.480";

function fmtNum(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
function greetWord() { const h = new Date().getHours(); return h < 12 ? "Buenos días" : h < 20 ? "Buenas tardes" : "Buenas noches"; }
function escShort(esc) { const a = DATA.areas.find(x => x.escuela === esc); return a ? a.short : esc; }

function HomeMark({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" fill="none" style={{ display: "block" }}>
      <rect width="26" height="26" rx="7.5" fill="var(--primary)" />
      <circle cx="11" cy="11" r="4.4" stroke="#fff" strokeWidth="2.1" />
      <path d="M14.4 14.4 18.5 18.5" stroke="#fff" strokeWidth="2.1" strokeLinecap="round" />
    </svg>
  );
}
function ArrowUp({ size = 19 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V6" /><path d="m6 12 6-6 6 6" />
    </svg>
  );
}

function Landing({ navigate, onSearch, user, isGuest }) {
  const [q, setQ] = useState("");
  const submit = () => onSearch(q.trim());
  const onKey = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } };

  // featured: most-read among docs visible to this viewer
  const visible = DATA.docs.filter(d => isGuest
    ? d.visibility === "publico"
    : (d.visibility !== "privado" || (user && d.authors.includes(user.name))));
  const featured = visible
    .map(d => ({ ...d, reads: HOME_READS[d.id] || 120 }))
    .sort((a, b) => b.reads - a.reads)
    .slice(0, 3);

  const first = user && user.name ? user.name.split(" ")[0] : null;
  const title = (first && !isGuest) ? `${greetWord()}, ${first}` : greetWord();

  return (
    <div className="home-stage">
      <div className="home-col">
        <div className="home-greet">
          <HomeMark />
          <h1 className="home-title">{title}</h1>
          <p className="home-sub">¿Qué querés investigar hoy?</p>
        </div>

        {/* chatbot-style composer */}
        <form className="home-composer-wrap" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <div className="home-composer">
            <textarea autoFocus rows={1} className="home-composer__input"
              value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey}
              placeholder="Buscá un tema, título o autor…" aria-label="Buscar trabajos" />
            <div className="home-composer__bar">
              <span className="home-composer__hint"><span className="kbd">↩</span><span>para buscar</span></span>
              <button type="submit" className="home-send" aria-label="Buscar"><ArrowUp /></button>
            </div>
          </div>
          <div className="home-foot">Buscando en <b>{HOME_INDEX}</b> trabajos de la comunidad UNSAM</div>
        </form>

        {/* suggested queries */}
        <div className="home-suggests">
          {SUGGESTED.map(s => (
            <button key={s} type="button" className="home-suggest" onClick={() => onSearch(s)}>
              <span className="home-suggest__ico">↗</span>{s}
            </button>
          ))}
        </div>

        {/* most read this week */}
        <div className="home-featured">
          <div className="home-eyebrow">
            <span>Más leídos esta semana</span>
            <button type="button" className="home-eyebrow__link" onClick={() => onSearch("")}>Ver todo</button>
          </div>
          <div className="home-readlist">
            {featured.map((d, i) => (
              <button key={d.id} type="button" className="home-readrow" onClick={() => navigate("docs", { id: d.id })}>
                <span className="home-rank">{i + 1}</span>
                <span className="home-readrow__body">
                  <span className="home-readrow__title">{d.title}</span>
                  <span className="home-readrow__meta">{escShort(d.escuela)} · {d.tipo} · {d.year}</span>
                </span>
                <span className="home-reads"><b>{fmtNum(d.reads)}</b> lecturas</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Login, Landing });
