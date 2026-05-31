/* ============================================================
   BUSCASAM — Shared form pieces
   Dropzone · CoautorPicker · VisibilityCards · ProcessingSteps · StatusPill
   ============================================================ */

function Spinner({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="bs-spin" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeOpacity="0.22" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/* ---- Status pill (foundations status set) ---- */
const STATUS_MAP = {
  borrador:   { tone: "neutral", label: "Borrador" },
  procesando: { tone: "amber",   label: "Procesando", spin: true },
  listo:      { tone: "blue",    label: "Listo para publicar" },
  publicado:  { tone: "green",   label: "Publicado" },
  oculto:     { tone: "red",     label: "Oculto por moderación" },
  fallo:      { tone: "red",     label: "Falló" },
};
function StatusPill({ status }) {
  const s = STATUS_MAP[status] || STATUS_MAP.borrador;
  return (
    <span className={"badge badge--" + s.tone}>
      {s.spin && <Spinner size={11} />}
      {s.label}
    </span>
  );
}

/* ---- Dropzone (real file input, drag + click) ---- */
function Dropzone({ accept, file, onFile, onClear, hint, label = "Arrastrá un archivo o hacé clic para elegir", compact }) {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);
  const pick = (f) => { if (f) onFile({ name: f.name, size: fmtSize(f.size) }); };

  if (file) {
    return (
      <div className="file-row" style={{ borderStyle: "solid" }}>
        <div className="file-row__icon"><Icon name="file-text" size={18} stroke={1.8} /></div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{file.name}</div>
          <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 1 }}>{file.size}</div>
        </div>
        <button className="btn btn--ghost btn--sm" onClick={() => inputRef.current.click()}>Reemplazar</button>
        <button className="btn btn--ghost btn--icon btn--sm" aria-label="Quitar" onClick={onClear}><Icon name="x" size={15} /></button>
        <input ref={inputRef} type="file" accept={accept} hidden onChange={e => pick(e.target.files[0])} />
      </div>
    );
  }
  return (
    <div onClick={() => inputRef.current.click()}
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); }}
      className="dropzone" data-over={over} style={{ padding: compact ? "18px" : "30px 24px" }}>
      <div className="dropzone__icon"><Icon name="upload" size={compact ? 18 : 22} stroke={1.8} /></div>
      <div style={{ fontSize: "var(--text-sm)", fontWeight: 500, marginTop: compact ? 8 : 12 }}>{label}</div>
      {hint && <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 4 }}>{hint}</div>}
      <input ref={inputRef} type="file" accept={accept} hidden onChange={e => pick(e.target.files[0])} />
    </div>
  );
}
function fmtSize(b) {
  if (!b) return "—";
  if (b > 1048576) return (b / 1048576).toFixed(1).replace(".", ",") + " MB";
  return Math.max(1, Math.round(b / 1024)) + " KB";
}

/* ---- Coautor picker (search registered users → chips) ---- */
function CoautorPicker({ selected, onChange }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const results = q.trim()
    ? DATA.people.filter(p => !selected.some(s => s.id === p.id) &&
        (p.name.toLowerCase().includes(q.toLowerCase()) || p.email.toLowerCase().includes(q.toLowerCase())))
    : [];
  const add = (p) => { onChange([...selected, p]); setQ(""); setOpen(false); };
  const remove = (id) => onChange(selected.filter(s => s.id !== id));
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div className="input-group">
        <Icon name="search" size={16} className="input-group__icon" stroke={2} />
        <input className="input" style={{ paddingLeft: 38 }} value={q}
          onChange={e => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          placeholder="Buscar por nombre o email…" />
      </div>
      {open && results.length > 0 && (
        <div className="popover pop-anim" style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 30, maxHeight: 220, overflowY: "auto" }}>
          {results.map(p => (
            <button key={p.id} onClick={() => add(p)} style={pickRow}
              onMouseEnter={e => e.currentTarget.style.background = "var(--neutral-100)"}
              onMouseLeave={e => e.currentTarget.style.background = "none"}>
              <span className="avatar" style={{ width: 26, height: 26, fontSize: 11 }}>{initials(p.name)}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontSize: "var(--text-sm)", fontWeight: 500 }}>{p.name}</span>
                <span style={{ display: "block", fontSize: 11, color: "var(--fg-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.email}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      {open && q.trim() && results.length === 0 && (
        <div className="popover pop-anim" style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 30, padding: "12px 14px", fontSize: "var(--text-meta)", color: "var(--fg-muted)" }}>
          Sin resultados para «{q}».
        </div>
      )}
      {selected.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 10 }}>
          {selected.map(p => (
            <span key={p.id} className="chip chip--active chip--removable">
              {p.name}
              <span className="chip__x" onClick={() => remove(p.id)}><Icon name="x" size={12} /></span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
const pickRow = { display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", padding: "7px 9px", border: "none", background: "none", borderRadius: "var(--r-sm)", cursor: "pointer", fontFamily: "inherit" };
function initials(name) { return name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase(); }

/* ---- Visibility selectable cards ---- */
const VIS_OPTS = [
  { value: "publico", label: "Público", help: "Cualquier persona puede encontrarlo y leerlo.", icon: "search" },
  { value: "interno", label: "Interno", help: "Sólo personas con cuenta UNSAM pueden verlo.", icon: "layers" },
  { value: "privado", label: "Privado", help: "Sólo vos y tus coautores aceptados.", icon: "eye-off" },
];
function VisibilityCards({ value, onChange }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {VIS_OPTS.map(o => {
        const on = value === o.value;
        return (
          <button key={o.value} type="button" onClick={() => onChange(o.value)} className="vis-card" data-on={on}>
            <span className="vis-card__radio" data-on={on}>{on && <span className="vis-card__dot" />}</span>
            <span style={{ flex: 1 }}>
              <span style={{ display: "block", fontSize: "var(--text-sm)", fontWeight: 600, color: on ? "var(--primary-hover)" : "var(--fg)" }}>{o.label}</span>
              <span style={{ display: "block", fontSize: "var(--text-meta)", color: "var(--fg-muted)", marginTop: 2 }}>{o.help}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ---- Processing steps (honest backend checkpoints) ---- */
const PROC_STEPS = [
  "Leyendo el documento",
  "Reconociendo texto (puede tardar varios minutos)",
  "Generando resumen y palabras clave",
  "Analizando contenido",
  "Preparando la búsqueda",
];
function ProcessingSteps({ step = 1 }) {
  const total = 4;
  const pct = Math.min(100, Math.round((step / total) * 100));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ color: "var(--primary)" }}><Spinner size={16} /></span>
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 500 }}>{PROC_STEPS[Math.min(step, PROC_STEPS.length - 1)] || "Procesando…"}</span>
      </div>
      <div className="progress"><div className="progress__fill" style={{ width: pct + "%" }} /></div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
        <span style={{ fontSize: 11, color: "var(--fg-muted)" }}>Paso {Math.min(step, total)} de {total}</span>
        <span style={{ fontSize: 11, color: "var(--fg-subtle)" }}>{pct}%</span>
      </div>
    </div>
  );
}

Object.assign(window, { Spinner, StatusPill, STATUS_MAP, Dropzone, fmtSize, CoautorPicker, initials, VisibilityCards, VIS_OPTS, ProcessingSteps, PROC_STEPS });
