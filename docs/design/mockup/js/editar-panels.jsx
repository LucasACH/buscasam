/* ============================================================
   BUSCASAM — Editar workspace sub-panels
   CandidatePanel · VersionsPanel · CoautoresPanel · AdjuntosPanel
   ============================================================ */

function SectionPanel({ title, action, children }) {
  return (
    <div className="section-panel">
      <div className="section-panel__head">
        <h3>{title}</h3>
        {action}
      </div>
      <div className="section-panel__body">{children}</div>
    </div>
  );
}

/* ---------- C10 — Candidate / replace main file (published docs) ---------- */
function CandidatePanel({ push }) {
  const [state, setState] = useState("none"); // none | processing | ready | failed
  const [file, setFile] = useState(null);

  const startReplace = (f) => {
    setFile(f); setState("processing");
    setTimeout(() => setState("ready"), 2600);
  };
  const discard = () => { setState("none"); setFile(null); };

  return (
    <SectionPanel title="Archivo principal"
      action={
        <div className="segmented" style={{ transform: "scale(0.86)", transformOrigin: "right" }} title="Estados (demo)">
          {[["none","Vacío"],["processing","Procesando"],["ready","Listo"],["failed","Falló"]].map(([v,l]) => (
            <button key={v} className={state === v ? "is-active" : ""} onClick={() => setState(v)}>{l}</button>
          ))}
        </div>
      }>
      <p style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", margin: "0 0 14px", lineHeight: 1.5 }}>
        La versión previa permanece pública hasta que publiques la nueva.
      </p>

      {state === "none" && (
        <Dropzone compact accept=".pdf,.docx,.odt" file={null} onFile={startReplace} onClear={() => {}}
          label="Reemplazar archivo principal" hint="PDF, DOCX u ODT · hasta 50 MB" />
      )}

      {state === "processing" && (
        <div>
          <ProcessingSteps step={2} />
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn btn--ghost btn--sm" onClick={discard}>Descartar</button>
          </div>
        </div>
      )}

      {state === "ready" && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <StatusPill status="listo" />
            <span style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)" }}>{(file && file.name) || "trabajo_v4.pdf"}</span>
          </div>
          <div style={{ background: "var(--neutral-50)", border: "1px solid var(--border)", borderRadius: "var(--r-base)", padding: 14, marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>Metadatos detectados</div>
            <dl className="meta-dl" style={{ gridTemplateColumns: "110px 1fr", gap: "9px 16px" }}>
              <dt>Resumen</dt><dd style={{ color: "var(--neutral-700)", lineHeight: 1.5 }}>Versión revisada con una sección de resultados ampliada y nuevas referencias…</dd>
              <dt>Palabras clave</dt><dd>algoritmos genéticos, logística, optimización</dd>
              <dt>Fecha</dt><dd>2025</dd>
            </dl>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn--primary btn--sm" onClick={() => { push("Nueva versión publicada", "success"); discard(); }}>Publicar nueva versión</button>
            <button className="btn btn--ghost btn--sm" onClick={discard}>Descartar</button>
          </div>
        </div>
      )}

      {state === "failed" && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <StatusPill status="fallo" />
          </div>
          <p style={{ fontSize: "var(--text-sm)", color: "var(--danger)", margin: "0 0 14px" }}>
            Formato no soportado o PDF cifrado. Probá con otro archivo.
          </p>
          <button className="btn btn--ghost btn--sm" onClick={discard}>Descartar</button>
        </div>
      )}
    </SectionPanel>
  );
}

/* ---------- Versiones anteriores ---------- */
function VersionsPanel() {
  const [errVer, setErrVer] = useState(null);
  return (
    <SectionPanel title="Versiones anteriores">
      <div className="list--divided" style={{ border: "1px solid var(--border)", borderRadius: "var(--r-base)" }}>
        {DATA.versions.map(v => (
          <div key={v.v} className="item" style={{ padding: "12px 14px" }}>
            <span className="mono" style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", flex: "none", width: 28 }}>v{v.v}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 500, display: "flex", alignItems: "center", gap: 8 }}>
                {v.file}{v.current && <span className="badge badge--green">actual</span>}
              </div>
              <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 2 }}>{v.size} · {v.date}</div>
              {errVer === v.v && <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 4 }}>No se pudo descargar. Reintentá.</div>}
            </div>
            <button className="btn btn--outline btn--sm" onClick={() => setErrVer(v.v === 1 ? 1 : null)}>
              <Icon name="download" size={14} stroke={2} /> Descargar
            </button>
          </div>
        ))}
      </div>
    </SectionPanel>
  );
}

/* ---------- Coautores ---------- */
const CO_STATUS = { pendiente: { tone: "amber", label: "Pendiente" }, aceptado: { tone: "green", label: "Aceptado" }, rechazado: { tone: "neutral", label: "Rechazado" } };
function CoautoresPanel({ push }) {
  const [list, setList] = useState(DATA.coautores);
  const [picker, setPicker] = useState([]);
  const remove = (id) => { setList(l => l.filter(c => c.id !== id)); push("Coautor quitado"); };
  // invite newly picked people as pending
  useEffect(() => {
    if (!picker.length) return;
    const p = picker[picker.length - 1];
    if (!list.some(c => c.name === p.name)) {
      setList(l => [...l, { id: "new_" + p.id, name: p.name, email: p.email.split("@")[0], status: "pendiente" }]);
      push("Invitación enviada", "success");
    }
    setPicker([]);
  }, [picker]);

  return (
    <SectionPanel title="Coautores">
      <div className="list--divided" style={{ border: "1px solid var(--border)", borderRadius: "var(--r-base)", marginBottom: 16 }}>
        {list.map(c => (
          <div key={c.id} className="item" style={{ padding: "11px 14px" }}>
            <span className="avatar" style={{ width: 30, height: 30, fontSize: 12 }}>{initials(c.name)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 500 }}>{c.name}{c.owner && <span style={{ color: "var(--fg-muted)", fontWeight: 400 }}> · Vos</span>}</div>
              <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 1 }}>@{c.email}</div>
            </div>
            {!c.owner && <span className={"badge badge--" + CO_STATUS[c.status].tone}>{CO_STATUS[c.status].label}</span>}
            {!c.owner && c.status === "pendiente" && (
              <button className="btn btn--ghost btn--sm" onClick={() => remove(c.id)}>Quitar</button>
            )}
          </div>
        ))}
      </div>
      <div className="field">
        <label className="label" style={{ fontSize: var12() }}>Invitar coautor</label>
        <CoautorPicker selected={picker} onChange={setPicker} />
      </div>
    </SectionPanel>
  );
}
function var12() { return "13px"; }

/* ---------- Adjuntos ---------- */
function AdjuntosPanel({ push }) {
  const [list, setList] = useState(DATA.attachments);
  const cap = list.length >= 5;
  const add = (f) => { if (cap) return; setList(l => [...l, { id: "at_" + Date.now(), name: f.name, size: f.size }]); push("Adjunto agregado", "success"); };
  const remove = (id) => setList(l => l.filter(a => a.id !== id));
  return (
    <SectionPanel title="Adjuntos">
      {list.length === 0 ? (
        <p style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", margin: "0 0 14px" }}>Sin adjuntos.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
          {list.map(a => (
            <div key={a.id} className="file-row">
              <div className="file-row__icon"><Icon name="file-text" size={16} stroke={1.8} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 500 }}>{a.name}</div>
                <div style={{ fontSize: 11, color: "var(--fg-muted)" }}>{a.size}</div>
              </div>
              <button className="btn btn--ghost btn--sm" onClick={() => remove(a.id)}>Quitar</button>
            </div>
          ))}
        </div>
      )}
      {cap ? (
        <div style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", display: "flex", alignItems: "center", gap: 7 }}>
          <Icon name="alert-triangle" size={14} stroke={1.9} /> Llegaste al máximo de 5 adjuntos.
        </div>
      ) : (
        <Dropzone compact accept=".csv,.json,.txt,.py,.ipynb,.png,.jpg,.gif,.zip" file={null} onFile={add} onClear={() => {}}
          label="Agregar adjunto" hint="CSV, JSON, TXT, PY, IPYNB, imágenes o ZIP" />
      )}
    </SectionPanel>
  );
}

Object.assign(window, { SectionPanel, CandidatePanel, VersionsPanel, CoautoresPanel, AdjuntosPanel });
