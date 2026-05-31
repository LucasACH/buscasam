"""Real UNSAM áreas reference tree (escuela.area.carrera.materia ltree).

The on-disk file `unsam_areas.json` is generated from the scraped oferta
académica — regenerate with `uv run scripts/build_unsam_areas.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

UNSAM_AREAS_FILE = Path(__file__).parent / "unsam_areas.json"


def load() -> list[dict[str, str]]:
    if not UNSAM_AREAS_FILE.exists():
        raise FileNotFoundError(
            f"{UNSAM_AREAS_FILE} missing — run "
            "`uv run scripts/build_unsam_areas.py`."
        )
    return json.loads(UNSAM_AREAS_FILE.read_text(encoding="utf-8"))
