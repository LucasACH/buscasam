/* ============================================================
   BUSCASAM — Search results + filters
   ============================================================ */

/* ---------- Área cascader popover ---------- */
function AreaCascader({ value, onChange, close }) {
  // value: {escuela, carrera, materia} or null
  const [esc, setEsc] = useState(value ? DATA.areas.find(a => a.escuela === value.escuela) : null);
  const [car, setCar] = useState(value && esc ? esc.carreras.find(c => c.carrera === value.carrera) : null);

  const back = () => { if (car) setCar(null); else if (esc) setEsc(null); };
  const crumb = ["Escuela", esc && esc.short, car && "Carrera"].filter(Boolean);

  return (
    <div style={{ width: 300, margin: -8 }}>
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8, minHeight: 42 }}>
        {(esc || car) && (
          <button className="btn btn--ghost btn--icon btn--sm" onClick={back} style={{ width: 26, height: 26 }}><Icon name="chevron-left" size={16} /></button>
        )}
        <div style={{ fontSize: 12, color: "var(--fg-muted)", display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {!esc && <span>Elegí una Escuela</span>}
          {esc && !car && <span><b style={{ color: "var(--fg)" }}>{esc.short}</b> · elegí Carrera</span>}
          {car && <span><b style={{ color: "var(--fg)" }}>{car.carrera}</b> · Materia</span>}
        </div>
      </div>
      <div style={{ maxHeight: 280, overflowY: "auto", padding: 6 }}>
        {!esc && DATA.areas.map(a => (
          <CascadeRow key={a.escuela} label={a.escuela} hint={a.short} arrow onClick={() => setEsc(a)} />
        ))}
        {esc && !car && esc.carreras.map(c => (
          <CascadeRow key={c.carrera} label={c.carrera} arrow onClick={() => setCar(c)} />
        ))}
        {car && car.materias.map(m => (
          <CascadeRow key={m} label={m} leaf
            selected={value && value.materia === m}
            onClick={() => { onChange({ escuela: esc.escuela, escuelaShort: esc.short, carrera: car.carrera, materia: m }); close(); }} />
        ))}
      </div>
      {value && (
        <div style={{ padding: 8, borderTop: "1px solid var(--border)" }}>
          <button className="btn btn--ghost btn--sm btn--block" onClick={() => { onChange(null); close(); }} style={{ color: "var(--danger)" }}>
            <Icon name="x" size={14} /> Quitar área
          </button>
        </div>
      )}
    </div>
  );
}
function CascadeRow({ label, hint, arrow, leaf, selected, onClick }) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left",
      padding: "9px 10px", border: "none", background: selected ? "var(--primary-tint)" : "none",
      borderRadius: "var(--r-sm)", cursor: "pointer", fontFamily: "inherit",
      fontSize: "var(--text-sm)", color: "var(--fg)",
    }} onMouseEnter={e => { if (!selected) e.currentTarget.style.background = "var(--neutral-100)"; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = "none"; }}>
      {leaf && <Icon name="map-pin" size={14} stroke={1.9} style={{ color: "var(--fg-subtle)", flex: "none" }} />}
      <span style={{ flex: 1 }}>{label}</span>
      {hint && <span style={{ fontSize: 11, color: "var(--fg-subtle)" }}>{hint}</span>}
      {arrow && <Icon name="chevron-right" size={15} style={{ color: "var(--fg-subtle)" }} />}
      {selected && <Icon name="check" size={15} stroke={2.5} style={{ color: "var(--primary)" }} />}
    </button>
  );
}

/* ---------- Tipo multi-select ---------- */
function TipoPicker({ value, onChange }) {
  const toggle = (t) => onChange(value.includes(t) ? value.filter(x => x !== t) : [...value, t]);
  return (
    <div style={{ width: 248, margin: -8 }}>
      <div style={{ padding: 6, maxHeight: 320, overflowY: "auto" }}>
        {DATA.tipos.map(t => {
          const on = value.includes(t);
          return (
            <button key={t} onClick={() => toggle(t)} style={{
              display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left",
              padding: "8px 10px", border: "none", background: "none", borderRadius: "var(--r-sm)",
              cursor: "pointer", fontFamily: "inherit", fontSize: "var(--text-sm)", color: "var(--fg)",
            }} onMouseEnter={e => e.currentTarget.style.background = "var(--neutral-100)"}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              <span style={{
                width: 17, height: 17, borderRadius: 5, flex: "none", display: "grid", placeItems: "center",
                border: "1.5px solid " + (on ? "var(--primary)" : "var(--border-strong)"),
                background: on ? "var(--primary)" : "transparent", transition: "all var(--dur)",
              }}>{on && <Icon name="check" size={12} stroke={3} style={{ color: "#fff" }} />}</span>
              {t}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ---------- Año range ---------- */
function YearPicker({ value, onChange, close }) {
  const [from, setFrom] = useState(value.from || "");
  const [to, setTo] = useState(value.to || "");
  return (
    <div style={{ width: 230, margin: -8, padding: 12 }}>
      <div style={{ display: "flex", gap: 10 }}>
        <div className="field" style={{ flex: 1 }}>
          <label className="label" style={{ fontSize: 12 }}>Desde</label>
          <input className="input" style={{ height: 34 }} inputMode="numeric" placeholder="2018" value={from} onChange={e => setFrom(e.target.value.replace(/\D/g, "").slice(0,4))} />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label className="label" style={{ fontSize: 12 }}>Hasta</label>
          <input className="input" style={{ height: 34 }} inputMode="numeric" placeholder="2025" value={to} onChange={e => setTo(e.target.value.replace(/\D/g, "").slice(0,4))} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        {value.from || value.to ? (
          <button className="btn btn--ghost btn--sm" onClick={() => { onChange({}); close(); }}>Quitar</button>
        ) : null}
        <button className="btn btn--primary btn--sm" style={{ flex: 1 }}
          onClick={() => { onChange({ from: from || null, to: to || null }); close(); }}>Aplicar</button>
      </div>
    </div>
  );
}

/* ---------- Result card ---------- */
function ResultCard({ doc, query, onOpen, i }) {
  const vis = VIS_BADGE[doc.visibility];
  return (
    <a className="result-card rise" style={{ animationDelay: (i * 45) + "ms", cursor: "pointer", display: "block" }}
      onClick={() => onOpen(doc.id)}>
      <h3 className="result-card__title">{doc.title}</h3>
      <div className="result-card__authors">{doc.authors.join(", ")}</div>
      <div className="result-card__meta">
        <span>{doc.year}</span><span className="dot">·</span>
        <span>{doc.escuelaShort || shortOf(doc.escuela)} › {doc.carrera} › {doc.materia}</span>
        <span className="dot">·</span><span>{doc.tipo}</span>
        {vis && <span className={"badge badge--" + vis.tone} style={{ marginLeft: 4 }}>{vis.label}</span>}
      </div>
      <p className="result-card__abstract" dangerouslySetInnerHTML={{ __html: query && doc.snippet ? doc.snippet : truncate(doc.abstract, 240) }} />
    </a>
  );
}
function shortOf(esc) { const a = DATA.areas.find(x => x.escuela === esc); return a ? a.short : esc; }
function truncate(s, n) { return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "") + "…" : s; }

/* ---------- Filtering ---------- */
function runQuery({ query, order, area, tipos, year, isGuest }) {
  let res = DATA.docs.filter(d => isGuest
    ? d.visibility === "publico"
    : (d.visibility !== "privado" || d.authors.includes(DATA.user.name)));
  if (query) {
    const q = query.toLowerCase();
    res = res.filter(d =>
      d.title.toLowerCase().includes(q) ||
      d.abstract.toLowerCase().includes(q) ||
      d.keywords.some(k => k.toLowerCase().includes(q)) ||
      d.authors.some(a => a.toLowerCase().includes(q)) ||
      d.materia.toLowerCase().includes(q));
  }
  if (area) res = res.filter(d => d.escuela === area.escuela && (!area.materia || d.materia === area.materia));
  if (tipos.length) res = res.filter(d => tipos.includes(d.tipo));
  if (year.from) res = res.filter(d => d.year >= +year.from);
  if (year.to) res = res.filter(d => d.year <= +year.to);
  if (order === "recientes") res = [...res].sort((a, b) => b.year - a.year);
  return res;
}

/* ---------- Results screen ---------- */
function Results({ initial, onOpen, isGuest }) {
  const [query, setQuery] = useState(initial.query || "");
  const [draft, setDraft] = useState(initial.query || "");
  const [order, setOrder] = useState("relevancia");
  const [area, setArea] = useState(null);
  const [tipos, setTipos] = useState(initial.tipos || []);
  const [year, setYear] = useState({});
  const [phase, setPhase] = useState("loading"); // loading | list | empty | error
  const [page, setPage] = useState(1);
  const PER = 4;

  const hasFilter = !!area || tipos.length > 0 || !!year.from || !!year.to;

  // simulate async on any change
  useEffect(() => {
    setPhase("loading");
    const t = setTimeout(() => {
      const r = runQuery({ query, order, area, tipos, year, isGuest });
      setResults(r);
      setPhase(r.length ? "list" : "empty");
    }, 520);
    return () => clearTimeout(t);
  }, [query, order, area, JSON.stringify(tipos), JSON.stringify(year), isGuest]);

  const [results, setResults] = useState([]);
  useEffect(() => { setPage(1); }, [query, order, area, JSON.stringify(tipos), JSON.stringify(year)]);

  const totalPages = Math.min(Math.ceil(results.length / PER) || 1, order === "relevancia" ? 20 : 999);
  const pageItems = results.slice((page - 1) * PER, page * PER);

  const clearAll = () => { setArea(null); setTipos([]); setYear({}); };
  const submitSearch = (e) => { e.preventDefault(); setQuery(draft.trim()); };

  return (
    <div>
      {/* slim sticky search + filters */}
      <div style={{ position: "sticky", top: "var(--header-h)", zIndex: 40, background: "rgba(255,255,255,0.9)", backdropFilter: "blur(8px)", borderBottom: "1px solid var(--border)" }}>
        <div style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "16px 24px 14px" }}>
          <form onSubmit={submitSearch} className="input-group" style={{ marginBottom: 12 }}>
            <Icon name="search" size={18} className="input-group__icon" stroke={2} />
            <input className="input" style={{ height: 44, paddingLeft: 42 }} value={draft}
              onChange={e => setDraft(e.target.value)} placeholder="Buscar por título, tema, autor…" aria-label="Buscar" />
          </form>

          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <div className="segmented">
              <button className={order === "relevancia" ? "is-active" : ""} onClick={() => setOrder("relevancia")}>Relevancia</button>
              <button className={order === "recientes" ? "is-active" : ""} onClick={() => setOrder("recientes")}>Recientes</button>
            </div>

            {/* Área */}
            <Popover width={300} trigger={({ toggle }) => (
              <button className={"btn btn--outline btn--filter" + (area ? " is-set" : "")} onClick={toggle}>
                <Icon name="layers" size={15} stroke={2} />
                {area ? <span style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{area.escuelaShort} › {area.materia}</span> : "Área"}
                <Icon name="chevron-down" size={14} />
              </button>
            )}>
              {({ close }) => <AreaCascader value={area} onChange={setArea} close={close} />}
            </Popover>

            {/* Tipo */}
            <Popover width={248} trigger={({ toggle }) => (
              <button className={"btn btn--outline btn--filter" + (tipos.length ? " is-set" : "")} onClick={toggle}>
                Tipo {tipos.length > 0 && <span className="count">{tipos.length}</span>}
                <Icon name="chevron-down" size={14} />
              </button>
            )}>
              <TipoPicker value={tipos} onChange={setTipos} />
            </Popover>

            {/* Año */}
            <Popover width={230} trigger={({ toggle }) => (
              <button className={"btn btn--outline btn--filter" + ((year.from || year.to) ? " is-set" : "")} onClick={toggle}>
                <Icon name="calendar" size={15} stroke={1.9} />
                {(year.from || year.to) ? `${year.from || "…"}–${year.to || "…"}` : "Año"}
                <Icon name="chevron-down" size={14} />
              </button>
            )}>
              {({ close }) => <YearPicker value={year} onChange={setYear} close={close} />}
            </Popover>

            {hasFilter && (
              <button className="btn btn--ghost btn--sm" onClick={clearAll} style={{ color: "var(--fg-muted)" }}>
                <Icon name="x" size={14} /> Limpiar
              </button>
            )}
          </div>
        </div>
      </div>

      {/* results column */}
      <div style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "20px 24px 80px" }}>
        <div style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", marginBottom: 16, minHeight: 18 }}>
          {phase === "loading" && "Buscando…"}
          {phase === "list" && <span><b style={{ color: "var(--fg)" }}>{results.length}</b> resultado{results.length !== 1 ? "s" : ""}{query && <> para «<span style={{ color: "var(--fg)" }}>{query}</span>»</>}</span>}
          {phase === "error" && <span style={{ color: "var(--danger)" }}>No se pudo completar la búsqueda. Reintentá en unos segundos.</span>}
        </div>

        {phase === "loading" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {[0,1,2,3,4].map(i => (
              <div key={i} className="result-card">
                <Sk w="72%" h={17} mb={12} />
                <Sk w="38%" h={11} mb={9} />
                <Sk w="64%" h={11} mb={14} />
                <Sk w="100%" h={11} mb={6} /><Sk w="92%" h={11} />
              </div>
            ))}
          </div>
        )}

        {phase === "empty" && (
          <Empty icon="search-x" title="No encontramos resultados"
            text="Probá con otras palabras clave o ajustá los filtros para ampliar la búsqueda."
            action={hasFilter ? <button className="btn btn--outline btn--sm" onClick={clearAll}>Limpiar filtros</button> : null} />
        )}

        {phase === "list" && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {pageItems.map((d, i) => <ResultCard key={d.id} doc={d} query={query} onOpen={onOpen} i={i} />)}
            </div>

            {totalPages > 1 && (
              <nav style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, marginTop: 28 }}>
                <button className="btn btn--outline btn--sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                  <Icon name="chevron-left" size={15} /> Anterior
                </button>
                <span style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)" }}>Página {page} de {totalPages}</span>
                <button className="btn btn--outline btn--sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
                  Siguiente <Icon name="chevron-right" size={15} />
                </button>
              </nav>
            )}
          </>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { Results, runQuery });
