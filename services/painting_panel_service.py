from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from services.planilha_service import normalize_display_name


@dataclass(frozen=True)
class PaintingPanelSummary:
    display: str | None
    processo: str | None
    cor: str | None
    codigo_pintura: str | None
    lote_text: str
    total_enviado: float
    total_retorno: float
    pendente_enviar: float | None
    pendente_retornar: float | None
    registros: int
    planilha_name: str | None
    warning: str | None


def extract_painting_multiplier(value: object) -> int | None:
    """Retorna os quatro ultimos digitos numericos do codigo de pintura."""
    if value is None or pd.isna(value):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits:
        return None
    try:
        return int(digits[-4:])
    except ValueError:
        return None


def extract_painting_color(processo: object) -> str | None:
    """Extrai a cor do processo sem depender de ENVIO ou RETORNO."""
    if processo is None or pd.isna(processo):
        return None
    text = str(processo).strip()
    if not text:
        return None
    parts = [part.strip() for part in text.replace("–", "-").split("-") if part.strip()]
    color = parts[-1] if parts else text
    normalized = normalize_display_name(color)
    if normalized in {"envio", "retorno"}:
        return None
    return color


def _clean_optional_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _painting_direction(processo: object) -> str | None:
    key = normalize_display_name(processo or "")
    tokens = set(key.split("_"))
    if "envio" in tokens:
        return "envio"
    if "retorno" in tokens:
        return "retorno"
    return None


@st.cache_data(show_spinner=False)
def load_painting_planilha(path_str: str, mtime: float | None) -> pd.DataFrame:
    del mtime
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    try:
        raw = pd.read_excel(path, engine="openpyxl")
    except Exception:
        return pd.DataFrame()
    if raw.empty:
        return pd.DataFrame()

    columns = {normalize_display_name(column): column for column in raw.columns}
    required = {
        "acabado": "display_nome",
        "processo": "processo_nome",
        "qnt": "qnt_por_produto",
    }
    if not set(required).issubset(columns):
        return pd.DataFrame()

    plan = pd.DataFrame(
        {
            target: raw[columns[source]]
            for source, target in required.items()
        }
    )
    plan["display_nome"] = plan["display_nome"].astype("string").str.strip()
    plan["processo_nome"] = plan["processo_nome"].astype("string").str.strip()
    plan["display_key"] = plan["display_nome"].apply(normalize_display_name)
    plan["processo_key"] = plan["processo_nome"].apply(normalize_display_name)
    plan["cor"] = plan["processo_nome"].apply(extract_painting_color)
    plan["cor_key"] = plan["cor"].apply(normalize_display_name)
    plan["qnt_por_produto"] = pd.to_numeric(plan["qnt_por_produto"], errors="coerce")
    return plan.dropna(subset=["qnt_por_produto"])


def load_painting_plans(planilhas_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    if not planilhas_dir.exists():
        return pd.DataFrame(), []
    frames: list[pd.DataFrame] = []
    names: list[str] = []
    for path in sorted(planilhas_dir.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = None
        frame = load_painting_planilha(str(path), mtime)
        if not frame.empty:
            frame = frame.copy()
            frame["planilha_name"] = path.name
            frames.append(frame)
            names.append(path.name)
    if not frames:
        return pd.DataFrame(), []
    return pd.concat(frames, ignore_index=True), names


def compute_painting_panel_summary(
    frame: pd.DataFrame,
    *,
    planilhas_dir: Path,
) -> PaintingPanelSummary:
    if frame.empty:
        return PaintingPanelSummary(
            None, None, None, None, "N/A", 0, 0, None,
            None, 0, None, None,
        )

    focus = frame.iloc[0]
    display = _clean_optional_text(focus.get("display"))
    processo = _clean_optional_text(focus.get("processo"))
    codigo = _clean_optional_text(focus.get("codigo_pintura"))
    cor = extract_painting_color(processo)

    plan, _names = load_painting_plans(planilhas_dir)
    if plan.empty:
        warning = "Planilha de pintura nao encontrada ou sem linhas validas."
        return PaintingPanelSummary(
            display, processo, cor, codigo, "N/A", 0, 0, None,
            None, len(frame), None, warning,
        )

    work = frame.copy()
    for column in ("display", "processo", "codigo_pintura"):
        work[column] = work.get(column, pd.Series(index=work.index, dtype="string")).astype("string").str.strip()
    work["quantidade_num"] = pd.to_numeric(work.get("quantidade"), errors="coerce").fillna(0)
    work["display_key"] = work["display"].apply(normalize_display_name)
    work["cor_key"] = work["processo"].apply(
        lambda value: normalize_display_name(extract_painting_color(value) or "")
    )
    work["codigo_key"] = work["codigo_pintura"].apply(normalize_display_name)
    work["direcao"] = work["processo"].apply(_painting_direction)

    display_key = normalize_display_name(display or "")
    color_key = normalize_display_name(cor or "")
    code_key = normalize_display_name(codigo or "")
    focus_rows = work[
        (work["display_key"] == display_key)
        & (work["cor_key"] == color_key)
        & (work["codigo_key"] == code_key)
    ]
    total_enviado = float(
        focus_rows.loc[focus_rows["direcao"] == "envio", "quantidade_num"].sum()
    )
    total_retorno = float(
        focus_rows.loc[focus_rows["direcao"] == "retorno", "quantidade_num"].sum()
    )

    plan_focus = plan[
        (plan["display_key"] == display_key) & (plan["cor_key"] == color_key)
    ].copy()
    plan_focus["direcao"] = plan_focus["processo_nome"].apply(_painting_direction)
    multiplier = extract_painting_multiplier(codigo)

    def expected_for(direction: str) -> float | None:
        if multiplier is None:
            return None
        rows = plan_focus[plan_focus["direcao"] == direction]
        if rows.empty:
            return None
        qnt = pd.to_numeric(rows["qnt_por_produto"], errors="coerce").fillna(0).sum()
        return float(math.floor((float(qnt) * multiplier) + 0.5))

    expected_envio = expected_for("envio")
    expected_retorno = expected_for("retorno")
    pendente_enviar = (
        max(expected_envio - total_enviado, 0.0) if expected_envio is not None else None
    )
    pendente_retornar = (
        max(expected_retorno - total_retorno, 0.0) if expected_retorno is not None else None
    )
    matched_names = set(plan_focus["planilha_name"].dropna().astype(str))
    planilha_name = ", ".join(sorted(matched_names)) or None
    lote_text = f"{multiplier:04d}" if multiplier is not None else "N/A"
    warning = None
    if multiplier is None:
        warning = "Codigo de pintura sem os quatro digitos do lote."
    elif plan_focus.empty:
        warning = "Cor ou display sem processo correspondente na planilha de pintura."
    return PaintingPanelSummary(
        display=display,
        processo=processo,
        cor=cor,
        codigo_pintura=codigo,
        lote_text=lote_text,
        total_enviado=total_enviado,
        total_retorno=total_retorno,
        pendente_enviar=pendente_enviar,
        pendente_retornar=pendente_retornar,
        registros=len(frame),
        planilha_name=planilha_name,
        warning=warning,
    )


def find_painting_image(
    images_dir: Path,
    display: str | None,
    processo: str | None,
) -> Path | None:
    if not images_dir.exists() or not processo:
        return None
    color_key = normalize_display_name(extract_painting_color(processo) or "")
    if not color_key:
        return None

    ignored = {"display", "rack"}
    display_tokens = {
        token for token in normalize_display_name(display or "").split("_")
        if token and token not in ignored
    }
    best: tuple[int, Path] | None = None
    for path in images_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        key = normalize_display_name(path.stem)
        key_tokens = set(key.split("_"))
        if color_key not in key_tokens and not key.endswith(color_key):
            continue
        overlap = len(display_tokens & key_tokens)
        score = overlap * 10 + (5 if display_tokens and display_tokens.issubset(key_tokens) else 0)
        candidate = (score, path)
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best[1] if best else None
