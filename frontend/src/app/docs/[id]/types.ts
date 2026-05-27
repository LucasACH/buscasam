export type AuthorDisplay = {
  display_name: string;
  user_id: number | null;
};

export type MainFile = {
  original_filename: string;
  size_bytes: number;
  mime: string;
};

export type Attachment = {
  id: number;
  original_filename: string;
  size_bytes: number;
  mime: string | null;
};

export type DetailVersion = {
  n: number;
  original_filename: string;
  mime: string;
  size_bytes: number;
  indexed_at: string | null;
  is_current: boolean;
};

type DetailFields = {
  doc_id: number;
  titulo: string;
  autores: AuthorDisplay[];
  area_path: string;
  tipo: string;
  fecha: string | null;
  visibility: string;
  abstract: string;
  palabras_clave: string[];
  archivo_principal: MainFile;
  adjuntos: Attachment[];
  // Omitted from the API JSON for non-managers (no-leak contract).
  versions?: DetailVersion[];
  manageable: boolean;
};

// GET /api/docs/{id} is a union discriminated on `view` (ADR-0010 §6):
// a normal reader detail, the same detail with a pending-invitation banner, or
// the minimal pre-acceptance block for a pending invitee on a privado doc.
export type DetailDoc = DetailFields & { view: "detail" };

export type DetailWithInvitationDoc = DetailFields & {
  view: "detail_with_invitation";
  invitation: { inviter_display_name: string };
};

export type MinimalInviteDoc = {
  view: "minimal";
  doc_id: number;
  titulo: string;
  inviter_display_name: string;
};

export type DocDetail = DetailDoc | DetailWithInvitationDoc | MinimalInviteDoc;
