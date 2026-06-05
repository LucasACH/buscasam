"""Per-tipo minimum area_path specificity (docs/SPEC.md §Documentos).

Course-bound work (trabajo práctico, apunte/resumen, informe de cátedra)
must name a materia; tesis and monografía belong to at least a carrera;
research output (paper, proyecto de investigación, ponencia/póster) to at
least an área. Deeper than the minimum is always allowed; an escuela alone
never is. The leaf segment's prefix (escuela_/area_/carrera_/materia_)
encodes the level — the área level is optional in the tree, so depth
counting would misclassify."""

from __future__ import annotations

_LEVEL_RANK = {"escuela": 0, "area": 1, "carrera": 2, "materia": 3}

MIN_AREA_LEVEL = {
    "tesis": "carrera",
    "paper": "area",
    "trabajo_practico": "materia",
    "proyecto_investigacion": "area",
    "monografia": "carrera",
    "ponencia_poster": "area",
    "apunte_resumen": "materia",
    "informe_catedra": "materia",
}


def area_level(area_path: str) -> str | None:
    """Level encoded in the leaf segment's prefix; None if unrecognized."""
    prefix = area_path.rsplit(".", 1)[-1].split("_", 1)[0]
    return prefix if prefix in _LEVEL_RANK else None


def area_path_allowed(document_type: str, area_path: str) -> bool:
    level = area_level(area_path)
    return (
        level is not None
        and _LEVEL_RANK[level] >= _LEVEL_RANK[MIN_AREA_LEVEL[document_type]]
    )
