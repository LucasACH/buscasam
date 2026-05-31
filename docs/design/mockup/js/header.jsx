/* ============================================================
   BUSCASAM — Global header + notifications panel
   ============================================================ */

const NOTIF_META = {
  coauthor_invite:  { icon: "user-plus",       text: (n) => <span><b>{n.inviter}</b> te invitó como coautor en «{n.doc}»</span> },
  document_hidden:  { icon: "eye-off",         text: (n) => <span>Tu documento «{n.doc}» fue ocultado. <span style={{color:"var(--fg-muted)"}}>Motivo: {n.reason}</span></span> },
  document_unhidden:{ icon: "rotate-ccw",      text: (n) => <span>Tu documento «{n.doc}» fue restaurado. <span style={{color:"var(--fg-muted)"}}>{n.reason}</span></span> },
  processing_failed:{ icon: "alert-triangle",  text: (n) => <span>Falló el procesamiento de «{n.doc}».</span> },
};

function NotificationRow({ n, onMarkRead, onInvite }) {
  const meta = NOTIF_META[n.kind];
  return (
    <div style={{
      display: "flex", gap: 11, padding: "13px 14px",
      borderBottom: "1px solid var(--border)",
      background: n.read ? "transparent" : "var(--primary-tint)",
      position: "relative",
    }}>
      {!n.read && <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "var(--primary)" }} />}
      <div style={{ color: "var(--fg-muted)", flex: "none", marginTop: 1 }}><Icon name={meta.icon} size={17} stroke={1.9} /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-meta)", lineHeight: 1.45, color: "var(--fg)" }}>{meta.text(n)}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 7 }}>
          <span style={{ fontSize: 11, color: "var(--fg-subtle)", whiteSpace: "nowrap" }}>{n.time}</span>
          {!n.read && (
            <button className="linkish" onClick={() => onMarkRead(n.id)}
              style={{ fontSize: 11, color: "var(--fg-muted)", background: "none", border: "none", cursor: "pointer", padding: 0, whiteSpace: "nowrap" }}>
              Marcar como leída
            </button>
          )}
        </div>
        {n.kind === "coauthor_invite" && !n.read && (
          <div style={{ display: "flex", gap: 6, marginTop: 9 }}>
            <button className="btn btn--primary btn--sm" onClick={() => onInvite(n.id, "accept")}>Aceptar</button>
            <button className="btn btn--ghost btn--sm" onClick={() => onInvite(n.id, "reject")}>Rechazar</button>
            <button className="btn btn--ghost btn--sm">Ver</button>
          </div>
        )}
      </div>
    </div>
  );
}

function NotificationPanel({ state, notifs, onMarkRead, onMarkAll, onInvite }) {
  const unread = notifs.filter(n => !n.read).length;
  return (
    <div style={{ width: 360, maxWidth: "92vw", margin: -8 }}>
      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontWeight: 600, fontSize: "var(--text-sm)", letterSpacing: "-0.01em" }}>Notificaciones</span>
        {unread > 0 && <Badge tone="blue">{unread} sin leer</Badge>}
      </div>

      <div className="scroll-area" style={{ maxHeight: 380, overflowY: "auto" }}>
        {state === "loading" && (
          <div>{[0,1,2].map(i => (
            <div key={i} style={{ display: "flex", gap: 11, padding: "13px 14px", borderBottom: "1px solid var(--border)" }}>
              <Sk w={18} h={18} r="50%" />
              <div style={{ flex: 1 }}><Sk w="90%" h={10} mb={7} /><Sk w="40%" h={9} /></div>
            </div>
          ))}</div>
        )}
        {state === "empty" && (
          <Empty icon="inbox" title="No tenés notificaciones" />
        )}
        {state === "list" && notifs.map(n => (
          <NotificationRow key={n.id} n={n} onMarkRead={onMarkRead} onInvite={onInvite} />
        ))}
      </div>

      {state === "list" && unread > 0 && (
        <div style={{ padding: 8, borderTop: "1px solid var(--border)" }}>
          <button className="btn btn--ghost btn--sm btn--block" onClick={onMarkAll}>Marcar todas como leídas</button>
        </div>
      )}
    </div>
  );
}

function NavLink({ active, children, onClick }) {
  return (
    <button onClick={onClick} style={{
      position: "relative", background: "none", border: "none", cursor: "pointer",
      fontFamily: "inherit", fontSize: "var(--text-sm)", letterSpacing: "-0.01em",
      fontWeight: active ? 600 : 500, color: active ? "var(--fg)" : "var(--fg-muted)",
      padding: "6px 2px", transition: "color var(--dur)",
    }} onMouseEnter={e => { if (!active) e.currentTarget.style.color = "var(--fg)"; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.color = "var(--fg-muted)"; }}>
      {children}
      {active && <span style={{ position: "absolute", left: 0, right: 0, bottom: -19, height: 2, background: "var(--primary)", borderRadius: 2 }} />}
    </button>
  );
}

function Header({ auth, user, route, notifs, navigate, onLogout, notifState, onMarkRead, onMarkAll, onInvite, isGuest }) {
  const unread = notifs.filter(n => !n.read).length;
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobOpen, setMobOpen] = useState(false);
  const isDocente = user && user.role === "Docente";

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 100, background: "rgba(255,255,255,0.85)",
      backdropFilter: "saturate(180%) blur(8px)", borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", height: "var(--header-h)", padding: "0 24px",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>

        <Wordmark onClick={() => navigate("buscar")} />

        {/* desktop right cluster */}
        {(!auth || isGuest) ? (
          <button className="btn btn--primary" onClick={() => navigate("login")}>
            <GoogleG size={17} mono /> Iniciar sesión con UNSAM
          </button>
        ) : (
          <>
            <div className="hdr-desk" style={{ display: "flex", alignItems: "center", gap: 22 }}>
              <NavLink active={route === "mis-trabajos"} onClick={() => navigate("mis-trabajos")}>Mis trabajos</NavLink>
              {isDocente && <NavLink active={route === "moderacion"} onClick={() => navigate("moderacion")}>Moderación</NavLink>}

              {/* bell */}
              <Popover width={360} align="right" trigger={({ toggle }) => (
                <button className="btn btn--ghost btn--icon" onClick={toggle} aria-label="Notificaciones" style={{ position: "relative" }}>
                  <Icon name="bell" size={19} stroke={1.8} />
                  {unread > 0 && (
                    <span style={{
                      position: "absolute", top: 4, right: 4, minWidth: 17, height: 17, padding: "0 4px",
                      background: "var(--primary)", color: "#fff", fontSize: 10, fontWeight: 700,
                      borderRadius: 999, display: "grid", placeItems: "center", border: "2px solid #fff",
                    }}>{unread > 9 ? "9+" : unread}</span>
                  )}
                </button>
              )}>
                {({ close }) => (
                  <NotificationPanel state={notifState} notifs={notifs}
                    onMarkRead={onMarkRead} onMarkAll={() => { onMarkAll(); }} onInvite={onInvite} />
                )}
              </Popover>

              {/* user menu */}
              <Popover width={284} align="right" trigger={({ toggle }) => (
                <button onClick={toggle} style={{ display: "flex", alignItems: "center", gap: 9, background: "none", border: "none", cursor: "pointer", padding: "4px 6px 4px 4px", borderRadius: "var(--r-base)", fontFamily: "inherit" }}
                  onMouseEnter={e => e.currentTarget.style.background = "var(--neutral-100)"}
                  onMouseLeave={e => e.currentTarget.style.background = "none"}>
                  <span className="avatar">{user.initials}</span>
                  <span style={{ textAlign: "left", lineHeight: 1.25 }}>
                    <span style={{ display: "block", fontSize: var13(), fontWeight: 600, whiteSpace: "nowrap" }}>{user.name}</span>
                    <span style={{ display: "block", fontSize: 11, color: "var(--fg-muted)", whiteSpace: "nowrap" }}>{user.role}</span>
                  </span>
                  <Icon name="chevron-down" size={15} style={{ color: "var(--fg-muted)" }} />
                </button>
              )}>
                {({ close }) => (
                  <div style={{ margin: -8 }}>
                    <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
                      <div style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>{user.name}</div>
                      <div style={{ fontSize: 11, color: "var(--fg-muted)", marginTop: 2 }}>{user.email}</div>
                    </div>
                    <div style={{ padding: 6 }}>
                      <button className="menu-item" onClick={() => { close(); onLogout(); }} style={menuItemStyle}>
                        <Icon name="log-out" size={16} stroke={1.9} /> Cerrar sesión
                      </button>
                    </div>
                  </div>
                )}
              </Popover>
            </div>

            {/* mobile cluster */}
            <div className="hdr-mob" style={{ display: "none", alignItems: "center", gap: 8 }}>
              <button className="btn btn--ghost btn--icon" aria-label="Notificaciones" style={{ position: "relative" }}>
                <Icon name="bell" size={19} stroke={1.8} />
                {unread > 0 && <span style={{ position: "absolute", top: 5, right: 5, width: 8, height: 8, background: "var(--primary)", borderRadius: 999, border: "2px solid #fff" }} />}
              </button>
              <span className="avatar">{user.initials}</span>
              <button className="btn btn--ghost btn--icon" onClick={() => setMobOpen(o => !o)} aria-label="Menú"><Icon name={mobOpen ? "x" : "menu"} size={20} /></button>
            </div>
          </>
        )}
      </div>

      {/* mobile menu sheet */}
      {auth && !isGuest && mobOpen && (
        <div className="hdr-mob" style={{ display: "block", borderTop: "1px solid var(--border)", padding: "8px 16px 14px", background: "#fff" }}>
          <button className="menu-item" style={menuItemStyle} onClick={() => { setMobOpen(false); navigate("mis-trabajos"); }}>Mis trabajos</button>
          {isDocente && <button className="menu-item" style={menuItemStyle} onClick={() => { setMobOpen(false); navigate("moderacion"); }}>Moderación</button>}
          <hr className="sep" style={{ margin: "8px 0" }} />
          <button className="menu-item" style={menuItemStyle} onClick={() => { setMobOpen(false); onLogout(); }}><Icon name="log-out" size={16} stroke={1.9} /> Cerrar sesión</button>
        </div>
      )}
    </header>
  );
}

const menuItemStyle = {
  display: "flex", alignItems: "center", gap: 10, width: "100%",
  padding: "9px 10px", border: "none", background: "none", cursor: "pointer",
  fontFamily: "inherit", fontSize: "var(--text-sm)", color: "var(--fg)",
  borderRadius: "var(--r-sm)", textAlign: "left", whiteSpace: "nowrap",
};
function var13() { return "14px"; }

Object.assign(window, { Header, NotificationPanel, NOTIF_META });
