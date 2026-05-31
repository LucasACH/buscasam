/* ============================================================
   BUSCASAM — Nuevo trabajo (create form)
   ============================================================ */

function FormField({ label, required, hint, error, children }) {
  return (
    <div className={"field" + (error ? " field--invalid" : "")} style={{ gap: 8 }}>
      {label && <label className="label">{label}{required && <span className="req">*</span>}</label>}
      {hint && <span className="field__hint" style={{ marginTop: -2 }}>{hint}</span>}
      {children}
      {error && <span className="field__error"><Icon name="alert-triangle" size={13} stroke={2.4} />{error}</span>}
    </div>
  );
}

function ExternalCoautores({ rows, onChange, errors }) {
  const update = (i, k, v) => onChange(rows.map((r, idx) => idx === i ? { ...r, [k]: v } : r));
  const remove = (i) => onChange(rows.filter((_, idx) => idx !== i));
  const add = () => onChange([...rows, { nombre: "", apellido: "", email: "" }]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {rows.map((r, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          <input className="input" placeholder="Nombre" value={r.nombre} onChange={e => update(i, "nombre", e.target.value)} style={{ flex: 1 }} />
          <input className="input" placeholder="Apellido" value={r.apellido} onChange={e => update(i, "apellido", e.target.value)} style={{ flex: 1 }} />
          <input className={"input" + (errors && errors[i] ? " input--invalid" : "")} placeholder="Email" value={r.email} onChange={e => update(i, "email", e.target.value)} style={{ flex: 1.4 }} />
          <button className="btn btn--ghost btn--icon" aria-label="Quitar coautor" onClick={() => remove(i)} style={{ flex: "none" }}><Icon name="x" size={16} /></button>
        </div>
      ))}
      <button className="btn btn--outline btn--sm" onClick={add} style={{ alignSelf: "flex-start" }}><Icon name="plus" size={14} stroke={2.2} /> Agregar coautor externo</button>
    </div>
  );
}

function Nuevo({ navigate, push }) {
  const [titulo, setTitulo] = useState("");
  const [area, setArea] = useState(null);
  const [tipo, setTipo] = useState("");
  const [vis, setVis] = useState("publico");
  const [ext, setExt] = useState([]);
  const [coautores, setCoautores] = useState([]);
  const [file, setFile] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const submit = () => {
    const e = {};
    if (!titulo.trim()) e.titulo = "Ingresá un título.";
    if (!area || !area.materia) e.area = "Elegí una Materia.";
    if (!tipo) e.tipo = "Elegí un tipo.";
    if (!file) e.file = "Subí el archivo principal.";
    const extErr = ext.map(r => r.email && !/^\S+@\S+\.\S+$/.test(r.email));
    if (extErr.some(Boolean)) e.ext = extErr;
    setErrors(e);
    if (Object.keys(e).length) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    setSubmitting(true);
    setTimeout(() => { setSubmitting(false); push("Trabajo subido — procesando", "success"); navigate("editar", { id: "new", mode: "indexing" }); }, 1300);
  };

  const formError = Object.keys(errors).length > 0;

  return (
    <div className="rise" style={{ maxWidth: 640, margin: "0 auto", padding: "32px 24px 90px" }}>
      <button className="btn btn--ghost btn--sm" onClick={() => navigate("mis-trabajos")} style={{ marginBottom: 16, marginLeft: -8, color: "var(--fg-muted)" }}>
        <Icon name="chevron-left" size={15} /> Mis trabajos
      </button>
      <h1 style={{ fontSize: "var(--text-h1)", fontWeight: 600, letterSpacing: "-0.03em", margin: "0 0 28px" }}>Nuevo trabajo</h1>

      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        <FormField label="Título" required error={errors.titulo}>
          <input className="input" value={titulo} onChange={e => setTitulo(e.target.value)} placeholder="Título del trabajo" />
        </FormField>

        <FormField label="Área" required error={errors.area} hint="Elegí hasta la Materia.">
          <Popover width={300} trigger={({ toggle }) => (
            <button type="button" className={"btn btn--outline" + (errors.area ? " input--invalid" : "")} onClick={toggle}
              style={{ justifyContent: "space-between", height: 40, fontWeight: 400, borderColor: errors.area ? "var(--danger)" : undefined }}>
              <span style={{ color: area ? "var(--fg)" : "var(--fg-subtle)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {area ? `${area.escuelaShort} › ${area.carrera} › ${area.materia}` : "Seleccioná Escuela › Carrera › Materia"}
              </span>
              <Icon name="chevron-down" size={15} style={{ color: "var(--fg-muted)", flex: "none" }} />
            </button>
          )}>
            {({ close }) => <AreaCascader value={area} onChange={setArea} close={close} />}
          </Popover>
        </FormField>

        <FormField label="Tipo" required error={errors.tipo}>
          <select className="native-select" value={tipo} onChange={e => setTipo(e.target.value)}>
            <option value="">Elegí un tipo</option>
            {DATA.tipos.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </FormField>

        <FormField label="Visibilidad">
          <VisibilityCards value={vis} onChange={setVis} />
        </FormField>

        <FormField label="Coautores externos" hint="Personas sin cuenta UNSAM. Opcional.">
          <ExternalCoautores rows={ext} onChange={setExt} errors={errors.ext} />
        </FormField>

        <FormField label="Coautores" hint="Buscá personas con cuenta UNSAM para invitar.">
          <CoautorPicker selected={coautores} onChange={setCoautores} />
        </FormField>

        <FormField label="Archivo principal" required error={errors.file}>
          <Dropzone accept=".pdf,.docx,.odt" file={file} onFile={setFile} onClear={() => setFile(null)}
            hint="PDF, DOCX u ODT · hasta 50 MB" label="Arrastrá tu archivo o hacé clic para elegir" />
        </FormField>

        <hr className="sep" style={{ margin: "2px 0" }} />

        {formError && (
          <div role="alert" style={{ display: "flex", gap: 10, background: "var(--danger-tint)", border: "1px solid #fecaca", borderRadius: "var(--r-base)", padding: "12px 14px" }}>
            <Icon name="alert-triangle" size={16} stroke={2} style={{ color: "var(--danger)", flex: "none", marginTop: 1 }} />
            <span style={{ fontSize: "var(--text-meta)", color: "#7f1d1d", lineHeight: 1.5 }}>Revisá los campos marcados antes de subir el trabajo.</span>
          </div>
        )}

        <button className="btn btn--primary btn--lg" onClick={submit} disabled={submitting} style={{ alignSelf: "flex-start", minWidth: 180 }}>
          {submitting ? <><Spinner size={16} /> Subiendo…</> : "Subir trabajo"}
        </button>
      </div>
    </div>
  );
}

Object.assign(window, { Nuevo, FormField });
