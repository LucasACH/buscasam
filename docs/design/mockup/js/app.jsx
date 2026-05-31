/* ============================================================
   BUSCASAM — App shell + router
   ============================================================ */

function ReportPopover({ onClose, push }) {
  const reasons = ["Spam", "Contenido inadecuado", "Plagio", "Error en el contenido"];
  const [reason, setReason] = useState(null);
  const [sent, setSent] = useState(false);
  return (
    <div className="popover pop-anim" style={{ position: "absolute", width: 288, right: 0, top: "calc(100% + 8px)", zIndex: 60, padding: 14 }}>
      {sent ? (
        <div style={{ textAlign: "center", padding: "12px 4px" }}>
          <div style={{ width: 38, height: 38, margin: "0 auto 10px", borderRadius: "50%", background: "var(--status-green-bg)", color: "var(--status-green-fg)", display: "grid", placeItems: "center" }}>
            <Icon name="check" size={20} stroke={2.5} />
          </div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>Recibimos tu reporte</div>
          <div style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", marginTop: 3 }}>Gracias.</div>
        </div>
      ) : (
        <>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, marginBottom: 12 }}>¿Por qué reportás este documento?</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 12 }}>
            {reasons.map(r => (
              <label key={r} style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 6px", borderRadius: "var(--r-sm)", cursor: "pointer", fontSize: "var(--text-sm)" }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--neutral-100)"}
                onMouseLeave={e => e.currentTarget.style.background = "none"}>
                <span style={{ width: 16, height: 16, borderRadius: "50%", flex: "none", border: "1.5px solid " + (reason === r ? "var(--primary)" : "var(--border-strong)"), display: "grid", placeItems: "center" }}>
                  {reason === r && <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--primary)" }} />}
                </span>
                <input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} style={{ display: "none" }} />
                {r}
              </label>
            ))}
          </div>
          <button className="btn btn--primary btn--sm btn--block" disabled={!reason} onClick={() => setSent(true)}>Enviar</button>
        </>
      )}
    </div>
  );
}

function App() {
  const [auth, setAuth] = useState(false);
  const [loginError, setLoginError] = useState(false);
  const [route, setRoute] = useState("login"); // login | buscar | docs
  const [searched, setSearched] = useState(false);
  const [searchInit, setSearchInit] = useState({ query: "", tipos: [] });
  const [docId, setDocId] = useState(null);
  const [reportId, setReportId] = useState(null);
  const [role, setRole] = useState(DATA.user.role); // Estudiante | Docente (demo)
  const [editarMode, setEditarMode] = useState("ready");
  const [notifs, setNotifs] = useState(DATA.notifications);
  const [notifState] = useState("list");
  const [reportOpen, setReportOpen] = useState(false);
  const { toasts, push } = useToasts();

  const navigate = (r, params = {}) => {
    if (r === "buscar") { setSearched(false); setSearchInit({ query: "", tipos: [] }); }
    if (r === "docs") setDocId(params.id);
    if (r === "moderacion-inspect") setReportId(params.reportId);
    if (r === "editar") setEditarMode(params.mode || "ready");
    setReportOpen(false);
    setRoute(r);
    window.scrollTo(0, 0);
  };

  const doSearch = (query, extra = {}) => {
    setSearchInit({ query, tipos: extra.tipos || [] });
    setSearched(true);
    setRoute("buscar");
  };

  const onLogin = () => { setLoginError(false); setAuth(true); setRole("Estudiante"); setRoute("buscar"); setSearched(false); };
  const onGuest = () => { setLoginError(false); setAuth(true); setRole("Invitado"); setRoute("buscar"); setSearched(false); };
  const onLogout = () => { setAuth(false); setRoute("login"); };

  const markRead = (id) => setNotifs(ns => ns.map(n => n.id === id ? { ...n, read: true } : n));
  const markAll = () => setNotifs(ns => ns.map(n => ({ ...n, read: true })));
  const onInvite = (id, action) => {
    markRead(id);
    push(action === "accept" ? "Invitación aceptada" : "Invitación rechazada", action === "accept" ? "success" : "default");
  };

  if (!auth || route === "login") {
    return (
      <>
        <Login error={loginError} navigate={navigate} onLogin={onLogin} onGuest={onGuest} />
        {/* prototype state helper */}
        <button onClick={() => setLoginError(e => !e)} style={protoToggle}>
          demo · {loginError ? "ocultar" : "ver"} estado de error
        </button>
        <ToastHost toasts={toasts} />
      </>
    );
  }

  const user = { ...DATA.user, role };
  const isGuest = role === "Invitado";
  const RESTRICTED = ["mis-trabajos", "nuevo", "editar", "papelera", "moderacion", "moderacion-inspect"];
  const knownRoutes = ["buscar", "docs", ...RESTRICTED];
  const unknown = !knownRoutes.includes(route);

  const switchRole = (r) => {
    setRole(r);
    if (r === "Invitado" && RESTRICTED.includes(route)) { navigate("buscar"); return; }
    if (r !== "Docente" && (route === "moderacion" || route === "moderacion-inspect")) navigate("buscar");
  };

  return (
    <>
      <Header auth={auth} user={user} isGuest={isGuest} route={route} notifs={notifs} navigate={navigate}
        onLogout={onLogout} notifState={notifState} onMarkRead={markRead} onMarkAll={markAll} onInvite={onInvite} />

      {route === "buscar" && !searched && <Landing navigate={navigate} onSearch={doSearch} />}
      {route === "buscar" && searched && <Results initial={searchInit} isGuest={isGuest} onOpen={(id) => navigate("docs", { id })} />}
      {route === "docs" && (
        <div style={{ position: "relative" }}>
          <DocDetail id={docId} navigate={navigate} push={push} isGuest={isGuest} onReport={() => setReportOpen(o => !o)} />
          {reportOpen && (
            <div style={{ position: "fixed", inset: 0, zIndex: 55 }} onClick={() => setReportOpen(false)}>
              <div style={{ position: "absolute", right: "max(24px, calc(50vw - 480px + 24px))", top: 150 }} onClick={e => e.stopPropagation()}>
                <div style={{ position: "relative" }}>
                  <ReportPopover onClose={() => setReportOpen(false)} push={push} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      {route === "mis-trabajos" && !isGuest && <MisTrabajos navigate={navigate} />}
      {route === "nuevo" && !isGuest && <Nuevo navigate={navigate} push={push} />}
      {route === "editar" && !isGuest && <Editar navigate={navigate} push={push} startMode={editarMode} />}
      {route === "papelera" && !isGuest && <Papelera navigate={navigate} push={push} />}
      {route === "moderacion" && !isGuest && <ModeracionQueue navigate={navigate} />}
      {route === "moderacion-inspect" && !isGuest && <ModeracionInspect reportId={reportId} navigate={navigate} push={push} />}
      {isGuest && RESTRICTED.includes(route) && <GuestGate navigate={navigate} />}
      {unknown && <NotFound kind="page" navigate={navigate} />}

      {/* prototype demo controls */}
      <div style={demoBar}>
        <span style={{ color: "var(--fg-subtle)" }}>demo</span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span style={{ color: "var(--fg-muted)" }}>rol</span>
        <div className="segmented" style={{ transform: "scale(0.9)" }}>
          {["Invitado", "Estudiante", "Docente"].map(r => (
            <button key={r} className={role === r ? "is-active" : ""} onClick={() => switchRole(r)}>{r}</button>
          ))}
        </div>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <button onClick={() => navigate("404")} style={demoLink}>ver 404</button>
      </div>

      <ToastHost toasts={toasts} />
    </>
  );
}

function GuestGate({ navigate }) {
  return (
    <div style={{ minHeight: "calc(100dvh - var(--header-h))", display: "grid", placeItems: "center", padding: "40px 24px" }}>
      <div style={{ maxWidth: 420, width: "100%" }}>
        <Empty icon="lock" title="Iniciá sesión para continuar"
          text="Esta sección es para la comunidad UNSAM. Ingresá con tu cuenta institucional para subir, editar y gestionar tus trabajos."
          action={<button className="btn btn--primary btn--sm" onClick={() => navigate("login")}><GoogleG size={15} mono /> Iniciar sesión con UNSAM</button>} />
      </div>
    </div>
  );
}

const demoBar = {
  position: "fixed", bottom: 14, left: "50%", transform: "translateX(-50%)",
  display: "flex", alignItems: "center", gap: 10, zIndex: 90,
  background: "rgba(255,255,255,0.92)", backdropFilter: "blur(8px)",
  border: "1px solid var(--border)", borderRadius: 999, padding: "5px 12px",
  fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-subtle)",
  boxShadow: "var(--shadow-pop)",
};
const demoLink = {
  background: "none", border: "none", cursor: "pointer", padding: 0,
  fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-muted)",
};

const protoToggle = {
  position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)",
  background: "var(--neutral-100)", border: "1px solid var(--border)", borderRadius: 999,
  padding: "5px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-subtle)",
  cursor: "pointer", zIndex: 90,
};

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
