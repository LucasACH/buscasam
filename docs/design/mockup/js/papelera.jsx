/* ============================================================
   BUSCASAM — C13 · Papelera
   Soft-deleted works, 180-day retention. Restore per row.
   States: loading · empty · list. Rows near purge warn subtly.
   ============================================================ */

function TrashRow({ item, onRestore }) {
  const near = item.daysLeft <= 7;
  return (
    <div className="item">
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 500, color: "var(--fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.title}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 4, fontSize: "var(--text-meta)", color: near ? "var(--status-amber-fg)" : "var(--fg-muted)" }}>
          <Icon name="clock" size={13} stroke={1.9} />
          <span>Se elimina en {item.daysLeft} {item.daysLeft === 1 ? "día" : "días"}</span>
          <span style={{ color: "var(--fg-subtle)" }}>·</span>
          <span style={{ color: "var(--fg-subtle)" }}>Eliminado el {item.deletedAt}</span>
        </div>
      </div>
      <button className="btn btn--outline btn--sm" onClick={() => onRestore(item.id)} style={{ flex: "none" }}>
        <Icon name="rotate-ccw" size={14} stroke={2} /> Restaurar
      </button>
    </div>
  );
}

function Papelera({ navigate, push }) {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  useEffect(() => {
    const t = setTimeout(() => { setItems(DATA.papelera); setLoading(false); }, 520);
    return () => clearTimeout(t);
  }, []);

  const restore = (id) => {
    setItems(list => list.filter(i => i.id !== id));
    push("Trabajo restaurado", "success");
  };

  return (
    <div className="rise" style={{ maxWidth: "var(--col-read)", margin: "0 auto", padding: "32px 24px 90px" }}>
      <button className="btn btn--ghost btn--sm" onClick={() => navigate("mis-trabajos")} style={{ marginBottom: 16, marginLeft: -8, color: "var(--fg-muted)" }}>
        <Icon name="chevron-left" size={15} /> Volver a Mis trabajos
      </button>

      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", margin: "0 0 6px" }}>Papelera</h1>
        <p style={{ fontSize: "var(--text-sm)", color: "var(--fg-muted)", margin: 0, lineHeight: 1.5 }}>
          Los trabajos eliminados se conservan 180 días antes de borrarse de forma permanente.
        </p>
      </div>

      {loading ? (
        <div className="panel"><div className="list--divided">
          {[0, 1, 2].map(i => (
            <div key={i} className="item"><div style={{ flex: 1 }}><Sk w="60%" h={13} mb={8} /><Sk w="38%" h={10} /></div><Sk w={104} h={32} r="var(--r-sm)" /></div>
          ))}
        </div></div>
      ) : items.length === 0 ? (
        <div className="panel">
          <Empty icon="trash" title="La papelera está vacía"
            text="Cuando elimines un trabajo, vas a poder restaurarlo desde acá durante 180 días."
            action={<button className="btn btn--primary btn--sm" onClick={() => navigate("mis-trabajos")}>Volver a Mis trabajos</button>} />
        </div>
      ) : (
        <div className="panel"><div className="list--divided">
          {items.map(it => <TrashRow key={it.id} item={it} onRestore={restore} />)}
        </div></div>
      )}
    </div>
  );
}

Object.assign(window, { Papelera });
