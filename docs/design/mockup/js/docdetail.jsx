/* ============================================================
   BUSCASAM — C6 · Document detail (reading view, light)
   + coautor invite (minimal / banner) · versions · owner Editar
   ============================================================ */

function FileRow({ name, meta, primary }) {
  return (
    <div className="file-row">
      <div className="file-row__icon"><Icon name="file-text" size={18} stroke={1.8} /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
        {meta && <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 1 }}>{meta}</div>}
      </div>
      <button className={"btn btn--sm " + (primary ? "btn--primary" : "btn--outline")}>
        <Icon name="download" size={14} stroke={2} /> Descargar
      </button>
    </div>
  );
}

const DOC_VIEWS = [["doc", "Documento"], ["banner", "Con banner"], ["invite", "Invitación"], ["invite-error", "Inv. · error"]];

function DocDetail({ id, navigate, onReport, push, isGuest }) {
  const [phase, setPhase] = useState("loading");
  const [view, setView] = useState("doc"); // doc | banner | invite | invite-error
  const doc = DATA.docs.find(d => d.id === id);
  useEffect(() => { setPhase("loading"); setView("doc"); const t = setTimeout(() => setPhase(doc ? "ready" : "notfound"), 500); return () => clearTimeout(t); }, [id]);
  const vis = doc && VIS_BADGE[doc.visibility];
  const owner = !isGuest && doc && doc.authors.includes(DATA.user.name);
  const related = doc ? DATA.docs.filter(d => d.id !== doc.id && d.escuela === doc.escuela && (isGuest ? d.visibility === "publico" : d.visibility !== "privado")).slice(0, 3) : [];

  const isInvite = !isGuest && (view === "invite" || view === "invite-error");
  const guestBlocked = isGuest && doc && doc.visibility !== "publico";

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "28px 24px 90px" }}>
      <button className="btn btn--ghost btn--sm" onClick={() => navigate("buscar")} style={{ marginBottom: 16, marginLeft: -8, color: "var(--fg-muted)" }}>
        <Icon name="chevron-left" size={15} /> Volver a buscar
      </button>

      {phase === "ready" && !isGuest && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--fg-subtle)" }}>demo · vista</span>
          <div className="segmented">
            {DOC_VIEWS.map(([v, l]) => (
              <button key={v} className={view === v ? "is-active" : ""} onClick={() => setView(v)}>{l}</button>
            ))}
          </div>
        </div>
      )}

      {phase === "loading" && (
        <div className="doc-grid">
          <div>
            <Sk w="85%" h={30} mb={14} /><Sk w="50%" h={13} mb={28} />
            <Sk w="40%" h={16} mb={16} />
            <Sk w="100%" h={12} mb={8} /><Sk w="100%" h={12} mb={8} /><Sk w="92%" h={12} mb={8} /><Sk w="96%" h={12} />
          </div>
          <div><div className="card"><Sk w="55%" h={14} mb={16} /><Sk w="100%" h={42} /></div></div>
        </div>
      )}

      {phase === "notfound" && (
        <Empty icon="file-x" title="Este trabajo no existe o no está disponible"
          text="Puede que haya sido eliminado, o que no tengas permiso para verlo."
          action={<button className="btn btn--primary btn--sm" onClick={() => navigate("buscar")}>Volver a buscar</button>} />
      )}

      {/* guest hitting a privado doc looks identical to not-found (privacy) */}
      {phase === "ready" && guestBlocked && doc.visibility === "privado" && (
        <Empty icon="file-x" title="Este trabajo no existe o no está disponible"
          text="Puede que haya sido eliminado, o que no tengas permiso para verlo."
          action={<button className="btn btn--primary btn--sm" onClick={() => navigate("buscar")}>Volver a buscar</button>} />
      )}

      {/* guest hitting an interno doc — invite to sign in */}
      {phase === "ready" && guestBlocked && doc.visibility === "interno" && (
        <div style={{ minHeight: "calc(100dvh - var(--header-h) - 120px)", display: "grid", placeItems: "center", padding: "24px" }}>
          <div className="card rise" style={{ maxWidth: 440, width: "100%", padding: 28, textAlign: "center", boxShadow: "var(--shadow-card-hover)" }}>
            <div style={{ width: 48, height: 48, margin: "0 auto 16px", borderRadius: "var(--r-base)", background: "var(--status-blue-bg)", color: "var(--status-blue-fg)", display: "grid", placeItems: "center" }}>
              <Icon name="layers" size={22} stroke={1.8} />
            </div>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--fg-muted)", marginBottom: 8 }}>Trabajo interno</div>
            <h1 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", lineHeight: 1.3, margin: "0 0 8px" }}>Este trabajo es solo para la comunidad UNSAM</h1>
            <p style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", lineHeight: 1.5, margin: "0 0 22px" }}>
              Iniciá sesión con tu cuenta institucional para ver «{doc.title}».
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
              <button className="btn btn--primary" onClick={() => navigate("login")}><GoogleG size={17} mono /> Iniciar sesión con UNSAM</button>
              <button className="btn btn--ghost" onClick={() => navigate("buscar")}>Volver a buscar</button>
            </div>
          </div>
        </div>
      )}

      {phase === "ready" && doc && isInvite && (
        <CoautorInvite variant="minimal"
          invite={{ inviter: DATA.invite.inviter, title: doc.title }}
          initialPhase={view === "invite-error" ? "error" : "idle"}
          onResolve={() => setView("doc")} push={push} />
      )}

      {phase === "ready" && doc && !isInvite && !guestBlocked && (
        <div className="doc-grid rise">
          {/* main */}
          <main>
            {view === "banner" && (
              <CoautorInvite variant="banner"
                invite={{ inviter: DATA.invite.inviter, title: doc.title }}
                onResolve={() => setView("doc")} push={push} />
            )}

            <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.18, margin: "0 0 10px" }}>{doc.title}</h1>
            <div style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", marginBottom: 26 }}>{doc.authors.join(", ")}</div>

            <dl className="meta-dl">
              <dt>Área</dt><dd>{doc.escuela} › {doc.carrera} › {doc.materia}</dd>
              <dt>Tipo</dt><dd>{doc.tipo}</dd>
              <dt>Fecha</dt><dd>{doc.year}</dd>
              {vis && <><dt>Visibilidad</dt><dd><span className={"badge badge--" + vis.tone}>{vis.label}</span></dd></>}
            </dl>

            <hr className="sep" style={{ margin: "24px 0" }} />

            <h2 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", margin: "0 0 12px" }}>Resumen</h2>
            <p style={{ fontSize: "var(--text-body)", lineHeight: "var(--lh-read)", color: "var(--neutral-700)", margin: 0 }}>{doc.abstract}</p>

            <h2 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", margin: "28px 0 12px" }}>Palabras clave</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {doc.keywords.map(k => <span key={k} className="badge badge--neutral" style={{ height: 26, fontSize: "var(--text-meta)" }}>{k}</span>)}
            </div>

            {owner && (
              <div style={{ marginTop: 28 }}>
                <VersionsPanel />
              </div>
            )}

            {related.length > 0 && (
              <>
                <hr className="sep" style={{ margin: "32px 0 24px" }} />
                <h2 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", margin: "0 0 14px" }}>Trabajos relacionados</h2>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {related.map((d, i) => <ResultCard key={d.id} doc={d} query="" onOpen={(rid) => navigate("docs", { id: rid })} i={i} />)}
                </div>
              </>
            )}
          </main>

          {/* aside */}
          <aside className="doc-aside">
            {owner && (
              <button className="btn btn--primary btn--block" onClick={() => navigate("editar", { id: doc.id })}>
                <Icon name="file-text" size={15} stroke={1.9} /> Editar
              </button>
            )}

            <div className="panel">
              <div className="panel__head"><span className="panel__title" style={{ fontSize: "var(--text-sm)", whiteSpace: "nowrap" }}>Archivo principal</span></div>
              <div style={{ padding: 12 }}>
                <FileRow name={doc.id + ".pdf"} meta="PDF · 4,2 MB" primary />
              </div>
            </div>

            <div className="panel">
              <div className="panel__head"><span className="panel__title" style={{ fontSize: "var(--text-sm)", whiteSpace: "nowrap" }}>Adjuntos</span></div>
              <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                <FileRow name="dataset.csv" meta="CSV · 880 KB" />
                <FileRow name="figuras.zip" meta="ZIP · 12,1 MB" />
              </div>
            </div>

            {!owner && !isGuest && (
              <button className="btn btn--ghost btn--sm" onClick={onReport} style={{ color: "var(--fg-muted)", alignSelf: "flex-start" }}>
                <Icon name="alert-triangle" size={14} stroke={1.9} /> Reportar
              </button>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { DocDetail });
