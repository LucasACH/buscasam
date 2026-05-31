"""Build `fixtures/unsam_areas.json` from the scraped UNSAM oferta académica.

Source: `data/unsam_oferta.json` (scraped from
https://www.unsam.edu.ar/oferta/carreras/). Emits a flat, tree-ordered list of
`{area_path, display_name}` rows for the `areas` reference table, where
`area_path` is a four-level ltree:

    escuela_<code>.area_<slug>.carrera_<slug>.materia_<slug>

Run after re-scraping:

    uv run scripts/build_unsam_areas.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT.parent / "data" / "unsam_oferta.json"
OUT = ROOT / "src" / "buscasam" / "fixtures" / "unsam_areas.json"


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "x"


def _unique(label: str, seen: set[str]) -> str:
    candidate, n = label, 2
    while candidate in seen:
        candidate, n = f"{label}_{n}", n + 1
    seen.add(candidate)
    return candidate


def build() -> list[dict[str, str]]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    def emit(path: str, name: str) -> None:
        if path not in seen_paths:
            seen_paths.add(path)
            rows.append({"area_path": path, "display_name": name})

    for esc in data["escuelas"]:
        esc_path = f"escuela_{slug(esc['escuela_codigo'])}"
        emit(esc_path, esc["escuela_nombre"])
        for area in esc["areas"]:
            area_path = f"{esc_path}.area_{slug(area['area_slug'])}"
            emit(area_path, area["area_nombre"])
            carrera_labels: set[str] = set()
            for carrera in area["carreras"]:
                label = _unique(f"carrera_{slug(carrera['slug'])}", carrera_labels)
                carrera_path = f"{area_path}.{label}"
                emit(carrera_path, carrera["nombre"])
                materia_labels: set[str] = set()
                for materia in carrera["materias"]:
                    m_label = _unique(f"materia_{slug(materia)}", materia_labels)
                    emit(f"{carrera_path}.{m_label}", materia)
    return rows


def main() -> None:
    if not SOURCE.exists():
        sys.exit(f"{SOURCE} missing — run the scraper first.")
    rows = build()
    OUT.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    levels = {1: 0, 2: 0, 3: 0, 4: 0}
    for r in rows:
        levels[r["area_path"].count(".") + 1] += 1
    print(f"wrote {len(rows)} rows to {OUT}")
    print(
        f"  escuelas={levels[1]} areas={levels[2]} "
        f"carreras={levels[3]} materias={levels[4]}"
    )


if __name__ == "__main__":
    main()
