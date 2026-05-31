/* ============================================================
   BUSCASAM — C12 · Coautor invitation
   One component, two variants:
     • minimal — standalone centered card (the only thing an
       invitee sees on a privado doc they can't read yet)
     • banner  — strip above the doc metadata on /docs/{id}
   ============================================================ */

function InviteActions({ phase, onAccept, onReject, size }) {
  const pending = phase === "pending";
  const cls = size === "sm" ? " btn--sm" : "";
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <button className={"btn btn--primary" + cls} disabled={pending} onClick={onAccept}>
        {pending && phase === "pending" ? null : null}
        Aceptar
      </button>
      <button className={"btn btn--ghost" + cls} disabled={pending} onClick={onReject}>
        Rechazar
      </button>
    </div>
  );
}

function InviteError({ onRetry }) {
  return (
    <div role="alert" style={{
      display: "flex", alignItems: "flex-start", gap: 9, marginTop: 14,
      padding: "10px 12px", borderRadius: "var(--r-base)",
      background: "var(--danger-tint)", border: "1px solid #fca5a5",
    }}>
      <span style={{ color: "var(--danger)", flex: "none", marginTop: 1 }}><Icon name="alert-triangle" size={15} stroke={1.9} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-meta)", color: "var(--danger-hover)", lineHeight: 1.45 }}>
          No pudimos procesar tu respuesta. Revisá tu conexión e intentá de nuevo.
        </div>
        <button className="linkish" onClick={onRetry}
          style={{ marginTop: 6, fontSize: 11, fontWeight: 600, color: "var(--danger)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
          Reintentar
        </button>
      </div>
    </div>
  );
}

function CoautorInvite({ variant = "minimal", invite, initialPhase = "idle", onResolve, push }) {
  const [phase, setPhase] = useState(initialPhase); // idle | pending | error
  const inv = invite || DATA.invite;

  const act = (a) => {
    setPhase("pending");
    setTimeout(() => {
      if (push) push(a === "accept" ? "Invitación aceptada" : "Invitación rechazada", a === "accept" ? "success" : "default");
      if (onResolve) onResolve(a);
    }, 850);
  };
  const accept = () => act("accept");
  const reject = () => act("reject");
  const retry = () => setPhase("idle");

  const lead = <><b style={{ fontWeight: 600, color: "var(--fg)" }}>{inv.inviter}</b> te invitó como coautor en «{inv.title}».</>;

  /* ---------- banner ---------- */
  if (variant === "banner") {
    return (
      <div className="rise" style={{
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        padding: "14px 18px", marginBottom: 24, borderRadius: "var(--r-base)",
        background: "var(--primary-tint)", border: "1px solid var(--primary-tint-2)",
      }}>
        <span style={{
          width: 36, height: 36, flex: "none", borderRadius: "var(--r-base)",
          background: "var(--card)", color: "var(--primary)", display: "grid", placeItems: "center",
          border: "1px solid var(--primary-tint-2)",
        }}><Icon name="user-plus" size={18} stroke={1.9} /></span>
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--neutral-700)", lineHeight: 1.45 }}>{lead}</div>
          <div style={{ fontSize: 11, color: "var(--primary-hover)", marginTop: 2, fontWeight: 500 }}>¿Aceptar o rechazar?</div>
        </div>
        {phase === "error"
          ? <button className="btn btn--primary btn--sm" onClick={retry}>Reintentar</button>
          : <InviteActions phase={phase} onAccept={accept} onReject={reject} size="sm" />}
      </div>
    );
  }

  /* ---------- minimal (standalone) ---------- */
  return (
    <div style={{ minHeight: "calc(100dvh - var(--header-h))", display: "grid", placeItems: "center", padding: "40px 24px" }}>
      <div className="card rise" style={{ maxWidth: 440, width: "100%", padding: 28, textAlign: "center", boxShadow: "var(--shadow-card-hover)" }}>
        <div style={{
          width: 48, height: 48, margin: "0 auto 16px", borderRadius: "var(--r-base)",
          background: "var(--primary-tint)", color: "var(--primary)", display: "grid", placeItems: "center",
        }}><Icon name="user-plus" size={22} stroke={1.8} /></div>

        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--fg-muted)", marginBottom: 8 }}>
          Invitación a coautoría
        </div>
        <p style={{ fontSize: "var(--text-body)", lineHeight: 1.5, color: "var(--fg)", margin: "0 0 8px" }}>{lead}</p>
        <p style={{ fontSize: "var(--text-meta)", color: "var(--fg-muted)", lineHeight: 1.5, margin: "0 0 22px" }}>
          Si aceptás, vas a poder ver y editar este trabajo privado.
        </p>

        <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
          <button className="btn btn--primary" disabled={phase === "pending"} onClick={accept} style={{ minWidth: 118 }}>
            {phase === "pending" ? <Spinner size={15} /> : "Aceptar"}
          </button>
          <button className="btn btn--ghost" disabled={phase === "pending"} onClick={reject}>Rechazar</button>
        </div>

        {phase === "error" && <InviteError onRetry={retry} />}
      </div>
    </div>
  );
}

Object.assign(window, { CoautorInvite, InviteActions, InviteError });
