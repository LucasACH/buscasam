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

const QUICK_TYPES = ["Tesis", "Paper", "Trabajo práctico", "Informe técnico"];

function Landing({ navigate, onSearch }) {
  const [q, setQ] = useState("");
  const submit = (query) => { const v = (query ?? q).trim(); onSearch(v || ""); };
  return (
    <div style={{ minHeight: "calc(100dvh - var(--header-h))", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 20px 80px" }}>
      <div className="rise" style={{ width: "100%", maxWidth: 640, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
        <Wordmark size="lg" />
        <h1 style={{ fontSize: 34, fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.15, margin: "30px 0 0", maxWidth: 540, color: "var(--fg)" }}>
          Encontrá trabajos académicos<br/>de la comunidad UNSAM
        </h1>

        {/* hero search */}
        <form onSubmit={(e) => { e.preventDefault(); submit(); }} style={{ width: "100%", maxWidth: 560, marginTop: 30 }}>
          <div className="hero-search">
            <Icon name="search" size={22} className="hero-search__icon" stroke={2} />
            <input autoFocus value={q} onChange={e => setQ(e.target.value)}
              placeholder="Buscar por título, tema, autor…"
              aria-label="Buscar trabajos" />
            <button type="submit" className="btn btn--primary" aria-label="Buscar">
              Buscar
            </button>
          </div>
        </form>

        {/* quick entry */}
        <div style={{ marginTop: 20, display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
          {QUICK_TYPES.map(t => (
            <button key={t} className="chip" onClick={() => onSearch("", { tipos: [t] })}>{t}</button>
          ))}
          <button className="chip" onClick={() => onSearch("")} style={{ color: "var(--primary)", borderColor: "var(--primary-tint-2)" }}>
            <Icon name="layers" size={14} stroke={2} /> Explorar por área
          </button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Login, Landing });
