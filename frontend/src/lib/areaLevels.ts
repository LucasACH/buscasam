// Per-tipo minimum area_path specificity, mirroring the backend rule in
// core/documents/area_rules.py (docs/SPEC.md §Documentos). The leaf segment's
// prefix (escuela_/area_/carrera_/materia_) encodes the level — the Área
// level is optional in the tree, so depth counting would misclassify.

export type AreaLevel = "escuela" | "area" | "carrera" | "materia";

const LEVEL_RANK: Record<AreaLevel, number> = {
  escuela: 0,
  area: 1,
  carrera: 2,
  materia: 3,
};

export const MIN_AREA_LEVEL: Record<string, AreaLevel> = {
  tesis: "carrera",
  paper: "area",
  trabajo_practico: "materia",
  proyecto_investigacion: "area",
  monografia: "carrera",
  ponencia_poster: "area",
  apunte_resumen: "materia",
  informe_catedra: "materia",
};

export function areaLevelOf(area_path: string): AreaLevel | null {
  const prefix = area_path.split(".").pop()!.split("_", 1)[0];
  return prefix in LEVEL_RANK ? (prefix as AreaLevel) : null;
}

export function isAtLeast(level: AreaLevel, min: AreaLevel): boolean {
  return LEVEL_RANK[level] >= LEVEL_RANK[min];
}

export function areaPathAllowed(tipo: string, area_path: string): boolean {
  const level = areaLevelOf(area_path);
  return level !== null && isAtLeast(level, MIN_AREA_LEVEL[tipo]);
}
