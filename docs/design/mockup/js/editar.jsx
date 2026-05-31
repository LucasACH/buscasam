/* ============================================================
   BUSCASAM — Editar trabajo (workspace)
   Modes: indexing · failed · ready  (+ demo mode switcher)
   ============================================================ */

function RestoreField({ label, diverged, onRestore, children }) {
  return (
    <div className="field" style={{ gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <label className="label">{label}</label>
        {diverged && (
          <button className="restore-link" onClick={onRestore}>
            <Icon name="rotate-ccw" size={12} stroke={2} /> Restaurar
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

const SUGGEST = {
  resumen: "Se modela la recolección de residuos del partido de San Martín como un problema de ruteo de vehículos con ventanas temporales y se resuelve mediante un algoritmo genético con operadores específicos del dominio. La solución reduce un 17% la distancia total recorrida.",
  keywords: "algoritmos genéticos, logística, residuos, optimización",
  fecha: "2024",
};

function EditarReady({ owner, push, onDelete }) {
  const [titulo, setTitulo] = useState("Optimización de rutas de recolección urbana con algoritmos genéticos");
  const [resumen, setResumen] = useState(SUGGEST.resumen);
  const [keywords, setKeywords] = useState(SUGGEST.keywords);
  const [fecha, setFecha] = useState(SUGGEST.fecha);
  const [vis, setVis] = useState("publico");
  const [saved, setSaved] = useState(false);
  const onBlurSave = () => { setSaved(true); setTimeout(() => setSaved(false), 1600); };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* saved indicator */}
      <div style={{ height: 16, marginTop: -8 }}>
        {saved && <span className="rise" style={{ fontSize: 11, color: "var(--status-green-fg)", display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="check" size={13} stroke={2.5} /> Cambios guardados</span>}
      </div>

      <div className="field" style={{ gap: 8 }}>
        <label className="label">Título</label>
        <input className="input" value={titulo} onChange={e => setTitulo(e.target.value)} onBlur={onBlurSave} />
      </div>

      <div className="field" style={{ gap: 8 }}>
        <label className="label">Área</label>
        <div style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", padding: "10px 12px", background: "var(--neutral-50)", border: "1px solid var(--border)", borderRadius: "var(--r-base)" }}>
          ECyT › Ingeniería Ambiental Urbana › Urbanismo sostenible
        </div>
      </div>

      <RestoreField label="Resumen" diverged={resumen !== SUGGEST.resumen} onRestore={() => { setResumen(SUGGEST.resumen); onBlurSave(); }}>
        <textarea className="textarea" rows={5} value={resumen} onChange={e => setResumen(e.target.value)} onBlur={onBlurSave} />
      </RestoreField>

      <RestoreField label="Palabras clave" diverged={keywords !== SUGGEST.keywords} onRestore={() => { setKeywords(SUGGEST.keywords); onBlurSave(); }}>
        <input className="input" value={keywords} onChange={e => setKeywords(e.target.value)} onBlur={onBlurSave} placeholder="Separadas por comas" />
      </RestoreField>

      <RestoreField label="Fecha" diverged={fecha !== SUGGEST.fecha} onRestore={() => { setFecha(SUGGEST.fecha); onBlurSave(); }}>
        <input className="input" value={fecha} onChange={e => setFecha(e.target.value.replace(/\D/g, "").slice(0,4))} onBlur={onBlurSave} style={{ maxWidth: 140 }} />
      </RestoreField>

      {owner && (
        <div className="field" style={{ gap: 8 }}>
          <label className="label">Visibilidad</label>
          <select className="native-select" value={vis} onChange={e => { setVis(e.target.value); onBlurSave(); }} style={{ maxWidth: 220 }}>
            <option value="publico">Público</option>
            <option value="interno">Interno</option>
            <option value="privado">Privado</option>
          </select>
        </div>
      )}

      <CandidatePanel push={push} />
      <VersionsPanel />
      <AdjuntosPanel push={push} />
      <CoautoresPanel push={push} />

      {/* publish */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <button className="btn btn--primary" onClick={() => push("Trabajo publicado", "success")}>Publicar</button>
        <span style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)" }}>Al publicar, el trabajo será visible según la visibilidad elegida.</span>
      </div>

      {/* delete */}
      {owner && (
        <>
          <hr className="sep" style={{ margin: "8px 0" }} />
          <button className="btn btn--destructive-outline btn--sm" onClick={onDelete} style={{ alignSelf: "flex-start" }}>
            <Icon name="trash" size={14} stroke={1.9} /> Eliminar trabajo
          </button>
        </>
      )}
    </div>
  );
}

function Editar({ navigate, push, startMode = "ready" }) {
  const [mode, setMode] = useState(startMode); // indexing | failed | ready
  const [step, setStep] = useState(1);
  const [confirmDel, setConfirmDel] = useState(false);

  useEffect(() => {
    if (mode !== "indexing") return;
    const t = setInterval(() => setStep(s => (s >= 4 ? 1 : s + 1)), 1600);
    return () => clearInterval(t);
  }, [mode]);

  const statusForMode = { indexing: "procesando", failed: "fallo", ready: "listo" }[mode];

  return (
    <div className="rise" style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "32px 24px 90px" }}>
      <button className="btn btn--ghost btn--sm" onClick={() => navigate("mis-trabajos")} style={{ marginBottom: 16, marginLeft: -8, color: "var(--fg-muted)" }}>
        <Icon name="chevron-left" size={15} /> Mis trabajos
      </button>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", margin: 0 }}>Editar trabajo</h1>
        <StatusPill status={statusForMode} />
      </div>

      {/* demo mode switcher */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
        <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--fg-subtle)" }}>demo · estado</span>
        <div className="segmented">
          {[["indexing","Indexando"],["failed","Falló"],["ready","Listo"]].map(([v,l]) => (
            <button key={v} className={mode === v ? "is-active" : ""} onClick={() => setMode(v)}>{l}</button>
          ))}
        </div>
      </div>

      {mode === "indexing" && (
        <div style={{ maxWidth: 480, margin: "40px auto", textAlign: "center" }}>
          <div className="section-panel" style={{ padding: 28, textAlign: "left" }}>
            <ProcessingSteps step={step} />
          </div>
          <p style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", lineHeight: 1.6, marginTop: 22 }}>
            Estamos procesando tu archivo. Esto puede tardar unos minutos. Podés cerrar esta página y volver más tarde — te avisamos cuando esté listo.
          </p>
        </div>
      )}

      {mode === "failed" && (
        <div style={{ maxWidth: 460, margin: "40px auto" }}>
          <Empty icon="alert-triangle"
            title="No pudimos procesar tu archivo"
            text="El documento no pudo leerse (formato no soportado o PDF cifrado). Eliminá este trabajo y volvé a subirlo con otro archivo."
            action={<button className="btn btn--destructive-outline btn--sm" onClick={() => setConfirmDel(true)}><Icon name="trash" size={14} stroke={1.9} /> Eliminar</button>} />
        </div>
      )}

      {mode === "ready" && <EditarReady owner push={push} onDelete={() => setConfirmDel(true)} />}

      {/* delete dialog */}
      {confirmDel && (
        <div className="dialog-backdrop" onClick={() => setConfirmDel(false)}>
          <div className="dialog" onClick={e => e.stopPropagation()} role="alertdialog" aria-modal="true">
            <h2 style={{ fontSize: 19, fontWeight: 600, letterSpacing: "-0.02em", margin: "0 0 8px" }}>¿Eliminar este trabajo?</h2>
            <p style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", lineHeight: 1.6, margin: "0 0 22px" }}>
              El trabajo irá a la papelera, donde podés restaurarlo durante 180 días. Después de ese plazo se elimina de forma permanente.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button className="btn btn--ghost" onClick={() => setConfirmDel(false)}>Cancelar</button>
              <button className="btn btn--destructive" onClick={() => { setConfirmDel(false); push("Trabajo movido a la papelera"); navigate("mis-trabajos"); }}>Eliminar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { Editar, EditarReady, RestoreField });
