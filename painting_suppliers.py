"""Painting supplier names and brand marks shared by the operational views."""

import base64
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path


LOGO_DIR = Path(__file__).resolve().parent / "assets" / "logos"
LOGO_FILES = {"Aquapint": "aquapint.png", "Multipint": "multipint.png"}
SUPPLIER_NAMES = {"AQUAPINT": "Aquapint", "MULTIPINT": "Multipint", "SCHUNCK": "SCHUNCK"}

SUPPLIER_CSS = """
  .painting-suppliers {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 3px 5px;
    margin: 2px 0 2px 5px;
    max-width: 100%;
    vertical-align: middle;
  }
  .painting-supplier-logo {
    display: inline-block;
    background: white center / contain no-repeat;
    border-radius: 3px;
    flex: 0 0 auto;
    height: 22px;
  }
  .painting-supplier-aquapint { width: 37px; }
  .painting-supplier-multipint { width: 49px; }
  .painting-supplier-text { font-size: 10px; font-weight: 800; }
"""


def painting_supplier(value: object) -> str | None:
    return SUPPLIER_NAMES.get(str(value or "").strip().upper())


def painting_suppliers(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(sorted({name for value in values if (name := painting_supplier(value))}))


def supplier_logo_path(name: str) -> Path | None:
    filename = LOGO_FILES.get(name)
    return LOGO_DIR / filename if filename else None


@lru_cache(maxsize=len(LOGO_FILES))
def _supplier_logo_uri(name: str) -> str | None:
    path = supplier_logo_path(name)
    if path is None:
        return None
    try:
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{payload}"


def supplier_logo_css(suppliers: Iterable[str]) -> str:
    return "".join(
        f'.painting-supplier-{name.lower()}{{background-image:url("{uri}");}}'
        for name in painting_suppliers(suppliers)
        if (uri := _supplier_logo_uri(name))
    )


def supplier_labels_html(suppliers: tuple[str, ...]) -> str:
    if not suppliers:
        return ""
    labels = [
        (
            f'<span class="painting-supplier-logo painting-supplier-{name.lower()}" '
            f'role="img" aria-label="{name}"></span>'
            if _supplier_logo_uri(name)
            else f'<span class="painting-supplier-text">{name}</span>'
        )
        for name in suppliers
    ]
    return '<span class="painting-suppliers">' + "".join(labels) + '</span>'
