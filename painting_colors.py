from __future__ import annotations

import json
import re
from pathlib import Path


COLOR_REFERENCE_PATH = Path(__file__).resolve().parent / "app" / "data" / "painting-colors.json"
COLOR_REFERENCES = json.loads(COLOR_REFERENCE_PATH.read_text(encoding="utf-8"))
COLOR_BY_ABBREVIATION = {
    str(item["abbreviation"]).strip().upper(): str(item["color"]).strip().upper()
    for item in COLOR_REFERENCES
}


def painting_code_parts(code: object) -> tuple[str, str, str]:
    """Retorna sigla, cor cadastrada e lote extraídos do código de pintura."""
    value = str(code or "").strip().upper()
    match = re.match(r"^([A-Z]{2})(?=\s*[-–—:/.]|\s|\d|$)", value)
    abbreviation = match.group(1) if match else ""
    raw_lot = re.sub(r"^\s*[-–—:/.]?\s*", "", value[match.end() :]).strip() if match else value
    lot = (raw_lot.lstrip("0") or "0") if raw_lot.isdigit() else raw_lot
    color = COLOR_BY_ABBREVIATION.get(abbreviation)
    if color is None:
        color = f"COR NÃO CADASTRADA ({abbreviation})" if abbreviation else "SEM COR"
    return abbreviation, color, lot
