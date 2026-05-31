/* ============================================================
   BUSCASAM — C14 · Moderación queue  +  C15 · Moderación inspect
   Docente-only. Queue optimized for fast triage; inspect has a
   clearly-separated action zone (actions notify the author).
   ============================================================ */

const REASON_TONE = { Plagio: "red", "Contenido inadecuado": "amber", Spam: "neutral", "Error en el contenido": "amber" };

/* ---------- C14 — Queue ---------- */
function ReportRow({ report, onOpen }) {
  const doc = DATA.docs.find(d => d.id === report.docId) || {};
  const high = report.count >= 5;
  return (
    <div className="item item--link" onClick={() => onOpen(report.id)} style={{ alignItems: "flex-start", gap: 14 }}>
      <span style={{
        flex: "none", minWidth: 40, height: 40, padding: "0 9px", borderRadius: "var(--r-base)",
        display: "grid", placeItems: "center", marginTop: 1,
        background: high ? "var(--status-red-bg)" : "var(--neutral-100)",
        color: high ? "var(--status-red-fg)" : "var(--fg-muted)",
        border: "1px solid " + (high ? "#fca5a5" : "var(--border)"),
      }}>
        <span style={{ fontSize: 16, fontWeight: 700, lineHeight: 1, fontFamily: "var(--font-mono)" }}>{report.count}</span>
      </span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--fg)", lineHeight: 1.35, letterSpacing: "-0.01em", marginBottom: 6, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{doc.title}</div>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "6px 8px", fontSize: "var(--text-meta)", color: "var(--fg-muted)" }}>
          {report.reasons.map(r => <span key={r} className={"badge badge--" + (REASON_TONE[r] || "neutral")}>{r}</span>)}
          <span style={{ color: "var(--fg-subtle)" }}>·</span>
          <span style={{ fontWeight: high ? 600 : 400, color: high ? "var(--status-red-fg)" : "var(--fg-muted)" }}>{report.count} {report.count === 1 ? "reporte" : "reportes"}</span>
          <span style={{ color: "var(--fg-subtle)" }}>·</span>
          <span>Último reporte el {report.last}</span>
        </div>
      </div>

      <Icon name="chevron-right" size={16} style={{ color: "var(--fg-subtle)", flex: "none", marginTop: 12 }} />
    </div>
  );
}

function ModeracionQueue({ navigate }) {
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState([]);
  useEffect(() => {
    const t = setTimeout(() => {
      setReports([...DATA.reports].sort((a, b) => b.count - a.count));
      setLoading(false);
    }, 520);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="rise" style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "32px 24px 90px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", margin: "0 0 6px" }}>Moderación</h1>
        <p style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", margin: 0, lineHeight: 1.5 }}>
          Trabajos reportados por la comunidad. Revisá cada caso antes de actuar.
        </p>
      </div>

      {loading ? (
        <div className="panel"><div className="list--divided">
          {[0, 1, 2].map(i => (
            <div key={i} className="item" style={{ alignItems: "flex-start" }}>
              <Sk w={40} h={40} r="var(--r-base)" />
              <div style={{ flex: 1 }}><Sk w="80%" h={13} mb={9} /><Sk w="50%" h={10} /></div>
            </div>
          ))}
        </div></div>
      ) : reports.length === 0 ? (
        <div className="panel">
          <Empty icon="shield-check" title="No hay reportes pendientes"
            text="Cuando la comunidad reporte un trabajo, vas a verlo acá para revisarlo." />
        </div>
      ) : (
        <div className="panel"><div className="list--divided">
          {reports.map(r => <ReportRow key={r.id} report={r} onOpen={(id) => navigate("moderacion-inspect", { reportId: id })} />)}
        </div></div>
      )}
    </div>
  );
}

/* ---------- C15 — Inspect ---------- */
function ModeracionInspect({ reportId, navigate, push }) {
  const [phase, setPhase] = useState("loading"); // loading | ready | notfound
  const [motivo, setMotivo] = useState("");
  const [pending, setPending] = useState(null); // null | 'hide' | 'show' | 'dismiss'

  const report = DATA.reports.find(r => r.id === reportId);
  const doc = report && DATA.docs.find(d => d.id === report.docId);

  useEffect(() => {
    setPhase("loading"); setMotivo(""); setPending(null);
    const t = setTimeout(() => setPhase(doc ? "ready" : "notfound"), 480);
    return () => clearTimeout(t);
  }, [reportId]);

  const act = (kind, toast) => {
    setPending(kind);
    setTimeout(() => { push(toast); navigate("moderacion"); }, 850);
  };

  return (
    <div className="rise" style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "28px 24px 90px" }}>
      <button className="btn btn--ghost btn--sm" onClick={() => navigate("moderacion")} style={{ marginBottom: 18, marginLeft: -8, color: "var(--fg-muted)" }}>
        <Icon name="chevron-left" size={15} /> Volver a Moderación
      </button>

      {phase === "loading" && (
        <div>
          <Sk w="80%" h={30} mb={14} /><Sk w="45%" h={13} mb={28} />
          <Sk w="100%" h={120} mb={20} /><Sk w="100%" h={120} />
        </div>
      )}

      {phase === "notfound" && (
        <Empty icon="file-x" title="No se pudo cargar el reporte"
          text="El reporte puede haber sido resuelto por otro moderador o ya no está disponible."
          action={<button className="btn btn--primary btn--sm" onClick={() => navigate("moderacion")}>Volver a Moderación</button>} />
      )}

      {phase === "ready" && doc && (
        <div>
          {/* triage banner */}
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14, fontSize: "var(--text-meta)", color: "var(--status-amber-fg)", fontWeight: 500 }}>
            <Icon name="flag" size={14} stroke={2} />
            {report.count} {report.count === 1 ? "reporte" : "reportes"} · último el {report.last}
          </div>

          <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.2, margin: "0 0 8px" }}>{doc.title}</h1>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", marginBottom: 26 }}>{doc.authors.join(", ")}</div>

          <dl className="meta-dl">
            <dt>Tipo</dt><dd>{doc.tipo}</dd>
            <dt>Área</dt><dd>{doc.escuela} › {doc.carrera} › {doc.materia}</dd>
            <dt>Autores</dt><dd>{doc.authors.join(", ")}</dd>
            <dt>Palabras clave</dt><dd>{doc.keywords.join(", ")}</dd>
            <dt>Reportado por</dt>
            <dd>
              <span style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {report.reasons.map(r => <span key={r} className={"badge badge--" + (REASON_TONE[r] || "neutral")}>{r}</span>)}
              </span>
            </dd>
          </dl>

          <h2 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", margin: "26px 0 10px" }}>Resumen</h2>
          <p style={{ fontSize: "var(--text-body)", lineHeight: "var(--lh-read)", color: "var(--neutral-700)", margin: "0 0 20px" }}>{doc.abstract}</p>

          <div className="file-row" style={{ maxWidth: 360 }}>
            <div className="file-row__icon"><Icon name="file-text" size={18} stroke={1.8} /></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 500 }}>{doc.id}.pdf</div>
              <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 1 }}>PDF · 4,2 MB</div>
            </div>
            <button className="btn btn--outline btn--sm"><Icon name="download" size={14} stroke={2} /> Descargar</button>
          </div>

          {/* ---- action zone ---- */}
          <hr className="sep" style={{ margin: "32px 0 24px" }} />

          <div style={{ background: "var(--neutral-50)", border: "1px solid var(--border)", borderRadius: "var(--r-lg)", padding: 20 }}>
            <h2 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", margin: "0 0 6px" }}>Resolver reporte</h2>
            <p style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", margin: "0 0 16px", lineHeight: 1.5 }}>
              Se le notificará al autor con el motivo que escribas a continuación.
            </p>

            <div className="field" style={{ gap: 8, marginBottom: 18 }}>
              <label className="label" htmlFor="mod-motivo">Motivo</label>
              <textarea id="mod-motivo" className="textarea" rows={3} value={motivo} disabled={!!pending}
                onChange={e => setMotivo(e.target.value)}
                placeholder="Explicá brevemente la decisión (visible para el autor)…" />
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn btn--destructive btn--sm" disabled={!!pending}
                onClick={() => act("hide", "Trabajo ocultado · se notificó al autor")}>
                {pending === "hide" ? <Spinner size={14} /> : <Icon name="eye-off" size={14} stroke={1.9} />} Ocultar
              </button>
              <button className="btn btn--outline btn--sm" disabled={!!pending}
                onClick={() => act("show", "Trabajo visible · se notificó al autor")}>
                {pending === "show" ? <Spinner size={14} /> : <Icon name="eye" size={14} stroke={1.9} />} Mostrar
              </button>
              <button className="btn btn--ghost btn--sm" disabled={!!pending}
                onClick={() => act("dismiss", "Reporte descartado")}>
                {pending === "dismiss" ? <Spinner size={14} /> : null} Descartar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { ModeracionQueue, ModeracionInspect, ReportRow });
