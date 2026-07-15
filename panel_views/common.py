from __future__ import annotations

import base64
import html
from pathlib import Path

import pandas as pd
import streamlit as st

from services.metrics import format_date, format_duration
from services.planilha_service import normalize_display_name


def render_prod_hora_card(
    title: str,
    value: str,
    operador: str | None = None,
    color: str | None = None,
) -> None:
    name_html = f'<span class="kpi-name">- {operador}</span>' if operador else ""
    color_style = f"color: {color};" if color else ""
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value" style="{color_style}">
                {value}{name_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_prod_hora_kpis(df: pd.DataFrame, *, show_info: bool = True) -> None:
    prod_cols = {"operador", "duracao_horas", "quantidade_produzida"}
    if not prod_cols.issubset(df.columns):
        if show_info:
            st.info("Sem dados de duracao/operador para calcular prod. por hora.")
        return

    op_df = df.dropna(subset=["operador", "duracao_horas", "quantidade_produzida"]).copy()
    if op_df.empty:
        if show_info:
            st.info("Sem dados de duracao/operador para calcular prod. por hora.")
        return

    op_df = op_df[op_df["duracao_horas"] > 0]
    op_df["prod_hora_apont"] = op_df["quantidade_produzida"] / op_df["duracao_horas"]
    op_df["prod_hora_apont"] = pd.to_numeric(op_df["prod_hora_apont"], errors="coerce")
    op_df = op_df.dropna(subset=["prod_hora_apont"])
    if op_df.empty:
        if show_info:
            st.info("Sem dados suficientes para calcular produtividade por operador/hora.")
        return

    op_df = op_df.sort_values("prod_hora_apont", ascending=False).reset_index(drop=True)
    top_row = op_df.iloc[0]
    bottom_row = op_df.iloc[-1]
    mean_prod_hora = op_df["prod_hora_apont"].mean()
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    with metric_col1:
        render_prod_hora_card(
            "Maior prod/hora (apontamento)",
            f"{top_row['prod_hora_apont']:,.2f}".replace(",", "."),
            top_row["operador"],
            "#2ecc71",
        )
    with metric_col2:
        render_prod_hora_card(
            "Media prod/hora (apontamentos)",
            f"{mean_prod_hora:,.2f}".replace(",", "."),
        )
    with metric_col3:
        render_prod_hora_card(
            "Pior prod/hora (apontamento)",
            f"{bottom_row['prod_hora_apont']:,.2f}".replace(",", "."),
            bottom_row["operador"],
            "#e74c3c",
        )


@st.cache_data(show_spinner=False)
def _build_display_image_map_cached(
    images_dir_str: str,
    directory_mtime_ns: int | None,
) -> dict[str, Path]:
    del directory_mtime_ns
    images_dir = Path(images_dir_str)
    if not images_dir.exists():
        return {}
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    images: dict[str, Path] = {}
    for path in images_dir.iterdir():
        if path.is_file() and path.suffix.lower() in allowed:
            key = normalize_display_name(path.stem)
            if key:
                images[key] = path
    return images


def build_display_image_map(images_dir: Path) -> dict[str, Path]:
    try:
        directory_mtime_ns = images_dir.stat().st_mtime_ns
    except OSError:
        directory_mtime_ns = None
    return _build_display_image_map_cached(
        str(images_dir.resolve()),
        directory_mtime_ns,
    )


def render_panel_card(
    title: str,
    value: str,
    subtitle: str | None = None,
    value_extra: str | None = None,
    card_class: str | None = None,
    value_is_html: bool = False,
) -> None:
    st.markdown(
        build_panel_card_html(
            title,
            value,
            subtitle=subtitle,
            value_extra=value_extra,
            card_class=card_class,
            value_is_html=value_is_html,
        ),
        unsafe_allow_html=True,
    )


def build_panel_card_html(
    title: str,
    value: str,
    subtitle: str | None = None,
    value_extra: str | None = None,
    card_class: str | None = None,
    value_is_html: bool = False,
) -> str:
    subtitle_html = f'<div class="panel-sub">{subtitle}</div>' if subtitle else ""
    if value_is_html:
        value_html = value
    elif value_extra:
        value_html = (
            '<div class="panel-value panel-value-inline">'
            f'<span class="panel-value-main">{value}</span>'
            f'<span class="panel-value-extra">{value_extra}</span>'
            "</div>"
        )
    else:
        value_html = f'<div class="panel-value">{value}</div>'
    panel_classes = ["panel-card"]
    if card_class:
        panel_classes.append(card_class)
    panel_class_attr = " ".join(panel_classes)
    return (
        f'<div class="{panel_class_attr}" style="margin-bottom: 12px;">'
        f'<div class="panel-title">{title}</div>'
        f"{value_html}"
        f"{subtitle_html}"
        "</div>"
    )


def build_time_estimate_html(
    best_hours: float | None,
    avg_hours: float | None,
    worst_hours: float | None,
    best_finish,
    avg_finish,
    worst_finish,
) -> str:
    scenarios = [
        ("Melhor", format_duration(best_hours), format_date(best_finish), "#2ecc71"),
        ("Media", format_duration(avg_hours), format_date(avg_finish), "#f5f7f8"),
        ("Pior", format_duration(worst_hours), format_date(worst_finish), "#e74c3c"),
    ]
    items = []
    for label, duration, finish_date, color in scenarios:
        items.append(
            '<div class="panel-time-item" '
            f'style="color:{color};">'
            f'<span class="panel-time-label">{label}</span>'
            f'<span class="panel-time-duration">{duration}</span>'
            f'<span class="panel-time-date">{finish_date}</span>'
            "</div>"
        )
    return f'<div class="panel-time-grid">{"".join(items)}</div>'


@st.cache_data(show_spinner=False)
def _load_image_as_data_uri_cached(
    path_str: str,
    file_mtime_ns: int,
    file_size: int,
) -> str | None:
    del file_mtime_ns, file_size
    path = Path(path_str)
    if not path.exists():
        return None
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "jpg":
        suffix = "jpeg"
    if suffix not in {"png", "jpeg", "webp", "gif"}:
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{suffix};base64,{encoded}"


def load_image_as_data_uri(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return _load_image_as_data_uri_cached(
        str(path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
    )


def render_dashboard_top_card(title: str, value: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="prod-top-card">
            <div class="prod-top-title">{title}</div>
            <div class="prod-top-value">{value}</div>
            <div class="prod-top-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_ranking_card(ranking_df: pd.DataFrame, label_col: str, format_int) -> None:
    if ranking_df.empty:
        st.info("Sem dados para ranking no periodo selecionado.")
        return
    for pos, (_, row) in enumerate(ranking_df.iterrows(), start=1):
        safe_label = html.escape(str(row[label_col]))
        st.markdown(
            f"""
            <div class="prod-rank-item">
                <div class="prod-rank-pos">{pos}</div>
                <div class="prod-rank-name" title="{safe_label}">{safe_label}</div>
                <div class="prod-rank-value">{format_int(row["quantidade_produzida"])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
