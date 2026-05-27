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

export type DocDetail = {
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
