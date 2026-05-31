/* ============================================================
   BUSCASAM — Mis trabajos (list / entry hub)
   ============================================================ */

function WorkRow({ w, navigate }) {
  return (
    <div className="item item--link" onClick={() => navigate("editar", { id: w.id })}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 500, color: "var(--fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{w.title}</div>
        <div style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", marginTop: 3 }}>
          {w.status === "publicado" && <>Publicado el {w.date}</>}
          {w.status === "oculto" && <>Publicado el {w.date}</>}
          {w.status === "borrador" && <>Editado {w.edited}</>}
          {w.status === "procesando" && <>Subido {w.edited}</>}
        </div>
      </div>
      <StatusPill status={w.status} />
      <Icon name="chevron-right" size={16} style={{ color: "var(--fg-subtle)", flex: "none" }} />
    </div>
  );
}

function WorkSection({ title, items, navigate, loading, emptyCta }) {
  return (
    <section style={{ marginBottom: 36 }}>
      <h2 style={{ fontSize: "var(--text-h2)", fontWeight: 600, letterSpacing: "-0.02em", margin: "0 0 12px" }}>{title}</h2>
      {loading ? (
        <div className="panel"><div className="list--divided">
          {[0,1].map(i => (
            <div key={i} className="item"><div style={{ flex: 1 }}><Sk w="55%" h={13} mb={7} /><Sk w="30%" h={10} /></div><Sk w={80} h={22} r="999px" /></div>
          ))}
        </div></div>
      ) : items.length === 0 ? (
        <div className="panel">
          <Empty icon="file-text" title="Todavía no hay nada acá"
            text="Aún no subiste ningún trabajo — empezá con Nuevo trabajo."
            action={emptyCta} />
        </div>
      ) : (
        <div className="panel"><div className="list--divided">
          {items.map(w => <WorkRow key={w.id} w={w} navigate={navigate} />)}
        </div></div>
      )}
    </section>
  );
}

function MisTrabajos({ navigate }) {
  const [loading, setLoading] = useState(true);
  useEffect(() => { const t = setTimeout(() => setLoading(false), 500); return () => clearTimeout(t); }, []);
  const nuevoCta = <button className="btn btn--primary btn--sm" onClick={() => navigate("nuevo")}><Icon name="plus" size={15} stroke={2.2} /> Nuevo trabajo</button>;

  return (
    <div className="rise" style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "32px 24px 90px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 32, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", margin: 0 }}>Mis trabajos</h1>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn btn--secondary" onClick={() => navigate("papelera")}><Icon name="trash" size={15} stroke={1.9} /> Papelera</button>
          <button className="btn btn--primary" onClick={() => navigate("nuevo")}><Icon name="plus" size={16} stroke={2.2} /> Nuevo trabajo</button>
        </div>
      </div>

      <WorkSection title="Borradores" items={DATA.myWorks.borradores} navigate={navigate} loading={loading} emptyCta={nuevoCta} />
      <WorkSection title="Publicados" items={DATA.myWorks.publicados} navigate={navigate} loading={loading} emptyCta={nuevoCta} />
    </div>
  );
}

Object.assign(window, { MisTrabajos });
