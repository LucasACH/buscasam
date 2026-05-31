// Shared display labels for document type and visibility enums, used across
// search results, the detail page, and moderation.

export const TIPO_LABEL: Record<string, string> = {
  tesis: "Tesis",
  paper: "Paper",
  trabajo_practico: "Trabajo práctico",
  proyecto_investigacion: "Proyecto de investigación",
  monografia: "Monografía",
  ponencia_poster: "Ponencia / Póster",
  apunte_resumen: "Apunte / Resumen",
  informe_catedra: "Informe de cátedra",
};

export const VISIBILITY_LABEL: Record<string, string> = {
  interno: "Interno",
  privado: "Privado",
};
