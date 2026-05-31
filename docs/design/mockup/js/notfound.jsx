/* ============================================================
   BUSCASAM — C16 · Not found / 404
   Page-level and document-level. A missing doc and an
   unauthorized doc render IDENTICALLY (privacy).
   ============================================================ */

function NotFound({ kind = "page", navigate }) {
  const isDoc = kind === "doc";
  return (
    <div className="rise" style={{
      minHeight: "calc(100dvh - var(--header-h))",
      display: "grid", placeItems: "center", padding: "40px 24px",
    }}>
      <div style={{ maxWidth: 420, width: "100%" }}>
        <Empty
          icon={isDoc ? "file-x" : "search-x"}
          title={isDoc ? "Este trabajo no existe o no está disponible" : "No encontramos esta página"}
          text={isDoc
            ? "Puede que haya sido eliminado, o que no tengas permiso para verlo."
            : "El enlace puede estar roto o la página puede haberse movido."}
          action={
            <button className="btn btn--primary btn--sm" onClick={() => navigate("buscar")}>
              <Icon name="search" size={15} stroke={2} /> Volver a buscar
            </button>
          }
        />
      </div>
    </div>
  );
}

Object.assign(window, { NotFound });
