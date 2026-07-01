from __future__ import annotations

import html
import textwrap
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from filters import FilterContext
from panel_views.common import (
    build_display_image_map,
    build_panel_card_html,
    build_time_estimate_html,
    load_image_as_data_uri,
    render_panel_card,
)
from services.display_panel_service import compute_display_panel_summary
from services.metrics import (
    format_duration,
    format_float,
    format_int,
    format_percent,
    is_positive_finite,
)
from services.planilha_service import normalize_display_name


def _html_text(value: object, fallback: str = "N/A") -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return html.escape(text if text else fallback)


def _first_text(values: list[str] | None, fallback: str = "N/A") -> str:
    if not values:
        return fallback
    return str(values[0]).strip() or fallback


def _selected_or_unique_text(
    selected: list[str] | None,
    df: pd.DataFrame,
    column: str,
    fallback: str = "N/A",
) -> str:
    selected_text = _first_text(selected, "")
    if selected_text:
        return selected_text
    if column not in df:
        return fallback
    values = [str(value).strip() for value in df[column].dropna().unique()]
    values = [value for value in values if value]
    if len(values) == 1:
        return values[0]
    return fallback


def _format_tv_decimal(value: float | int | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _format_tv_percent(value: float | None, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{_format_tv_decimal(float(value) * 100, decimals)}%"


def _format_tv_duration(hours: float | None) -> str:
    if not is_positive_finite(hours):
        return "N/A"
    total_minutes = int(round(float(hours) * 60))
    hour_value, minute_value = divmod(total_minutes, 60)
    return f"{hour_value}h{minute_value:02d}"


def _compute_prod_hora_summary(df: pd.DataFrame) -> dict[str, object] | None:
    prod_cols = {"operador", "duracao_horas", "quantidade_produzida"}
    if not prod_cols.issubset(df.columns):
        return None

    op_df = df.dropna(subset=["operador", "duracao_horas", "quantidade_produzida"]).copy()
    if op_df.empty:
        return None

    op_df = op_df[op_df["duracao_horas"] > 0]
    if op_df.empty:
        return None

    op_df["prod_hora_apont"] = pd.to_numeric(
        op_df["quantidade_produzida"] / op_df["duracao_horas"],
        errors="coerce",
    )
    op_df = op_df.dropna(subset=["prod_hora_apont"])
    if op_df.empty:
        return None

    op_df = op_df.sort_values("prod_hora_apont", ascending=False).reset_index(drop=True)
    top_row = op_df.iloc[0]
    bottom_row = op_df.iloc[-1]
    return {
        "best_value": float(top_row["prod_hora_apont"]),
        "best_operator": str(top_row["operador"]),
        "avg_value": float(op_df["prod_hora_apont"].mean()),
        "worst_value": float(bottom_row["prod_hora_apont"]),
        "worst_operator": str(bottom_row["operador"]),
    }


def _build_tv_time_card(summary) -> str:
    if summary.remaining is not None and summary.remaining <= 0:
        values = [
            ("Melhor cenário", "Concluído", "good"),
            ("Cenário médio", "Concluído", "neutral"),
            ("Pior cenário", "Concluído", "bad"),
        ]
    elif summary.time_estimate is not None:
        values = [
            (
                "Melhor cenário",
                _format_tv_duration(summary.time_estimate.best_hours),
                "good",
            ),
            (
                "Cenário médio",
                _format_tv_duration(summary.time_estimate.avg_hours),
                "neutral",
            ),
            (
                "Pior cenário",
                _format_tv_duration(summary.time_estimate.worst_hours),
                "bad",
            ),
        ]
    else:
        values = [
            ("Melhor cenário", "N/A", "good"),
            ("Cenário médio", "N/A", "neutral"),
            ("Pior cenário", "N/A", "bad"),
        ]

    items = "".join(
        f"""
        <div class="tv-time-item tv-time-{style}">
            <div class="tv-time-label">{label}</div>
            <div class="tv-time-value">{html.escape(value)}</div>
        </div>
        """
        for label, value, style in values
    )
    return f"""
    <div class="tv-card tv-time-card">
        <div class="tv-card-title">TEMPO RESTANTE</div>
        <div class="tv-time-grid">{items}</div>
    </div>
    """


def _build_tv_prod_card(
    title: str,
    value: str,
    subtitle: str,
    variant: str,
) -> str:
    return f"""
    <div class="tv-card tv-footer-card tv-footer-{variant}">
        <div class="tv-footer-mark" aria-hidden="true"></div>
        <div>
            <div class="tv-footer-title">{title}</div>
            <div class="tv-footer-value">{html.escape(value)}</div>
            <div class="tv-footer-sub">{html.escape(subtitle)}</div>
        </div>
    </div>
    """


def _render_tv_dashboard(
    *,
    df: pd.DataFrame,
    summary,
    filter_context: FilterContext,
    image_path: Path | None,
) -> None:
    display_name = _selected_or_unique_text(summary.display_selected, df, "display")
    numero_text = _selected_or_unique_text(summary.numero_selected, df, "numero_display")
    maquinario_text = _selected_or_unique_text(
        filter_context.maquinario_selected,
        df,
        "maquinario",
    )
    processo_text = _selected_or_unique_text(
        filter_context.processo_selected,
        df,
        "processo",
    )
    planilha_text = summary.planilha_name or "N/A"

    target_total = summary.target_total
    produced = summary.total_produzido
    progress_ratio = produced / target_total if target_total and target_total > 0 else None
    progress_width = 0 if progress_ratio is None else max(0, min(progress_ratio, 1)) * 100
    percent_text = _format_tv_percent(progress_ratio)
    total_text = format_int(target_total) if target_total is not None else "Sem meta"
    produced_text = format_int(produced)
    remaining_text = "Sem meta"
    remaining_unit_html = ""
    if summary.remaining is not None:
        remaining_text = "Concluído" if summary.remaining <= 0 else format_int(summary.remaining)
        if summary.remaining > 0:
            remaining_unit_html = '<span class="tv-number-sub">peças</span>'

    image_uri = load_image_as_data_uri(image_path) if image_path else None
    image_html = (
        f'<img src="{image_uri}" alt="Imagem do display">'
        if image_uri
        else '<div class="tv-image-empty">Imagem do display nao encontrada</div>'
    )

    prod_summary = _compute_prod_hora_summary(df)
    if prod_summary:
        footer_cards = [
            _build_tv_prod_card(
                "Melhor prod/hora",
                _format_tv_decimal(prod_summary["best_value"]),
                str(prod_summary["best_operator"]),
                "good",
            ),
            _build_tv_prod_card(
                "Média prod/hora",
                _format_tv_decimal(prod_summary["avg_value"]),
                "Apontamentos",
                "neutral",
            ),
            _build_tv_prod_card(
                "Pior prod/hora",
                _format_tv_decimal(prod_summary["worst_value"]),
                str(prod_summary["worst_operator"]),
                "bad",
            ),
        ]
    else:
        footer_cards = [
            _build_tv_prod_card("Melhor prod/hora", "N/A", "Sem dados", "good"),
            _build_tv_prod_card("Média prod/hora", "N/A", "Apontamentos", "neutral"),
            _build_tv_prod_card("Pior prod/hora", "N/A", "Sem dados", "bad"),
        ]

    time_card_html = _build_tv_time_card(summary)
    footer_html = "".join(footer_cards)

    st.markdown(
        """
        <style>
        .dashboard-heading,
        .section-divider,
        section.main h2 {
            display: none !important;
        }
        section.main > div:first-child {
            padding: 0 !important;
        }
        .block-container {
            max-width: 100% !important;
            padding: 0 !important;
        }
        iframe {
            display: block;
            width: 100% !important;
            height: calc(100vh - 2px) !important;
            border: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    panel_html = textwrap.dedent(
        f"""
        <!doctype html>
        <html lang="pt-BR">
        <head>
        <meta charset="utf-8">
        <style>
        :root {{
            background:
                radial-gradient(circle at 22% 38%, rgba(11, 88, 97, 0.22), transparent 34%),
                linear-gradient(135deg, #020914 0%, #061522 48%, #02070f 100%);
            color: #f5f7f8;
        }}
        * {{
            box-sizing: border-box;
        }}
        html,
        body {{
            width: 100%;
            height: 100%;
            margin: 0;
            overflow: hidden;
            background:
                radial-gradient(circle at 22% 38%, rgba(11, 88, 97, 0.22), transparent 34%),
                linear-gradient(135deg, #020914 0%, #061522 48%, #02070f 100%);
        }}
        .tv-dashboard {{
            box-sizing: border-box;
            width: 100%;
            height: 100vh;
            min-height: 620px;
            display: grid;
            grid-template-rows: auto minmax(0, 1fr) auto;
            gap: clamp(0.55rem, 0.95vh, 0.9rem);
            overflow: hidden;
            padding: clamp(0.65rem, 1.15vw, 1.2rem);
            font-family: "Segoe UI", Arial, sans-serif;
        }}
        .tv-header {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(280px, 26vw);
            gap: 1.5rem;
            align-items: end;
            padding-bottom: clamp(0.6rem, 1vh, 0.9rem);
            border-bottom: 1px solid rgba(199, 225, 229, 0.17);
        }}
        .tv-kicker {{
            color: rgba(245, 247, 248, 0.92);
            font-size: clamp(1rem, 1.15vw, 1.45rem);
            font-weight: 800;
            margin-bottom: 0.18rem;
        }}
        .tv-title {{
            color: #ffffff;
            font-size: clamp(2.25rem, 3.5vw, 4.25rem);
            line-height: 0.98;
            font-weight: 900;
            letter-spacing: 0;
            text-transform: uppercase;
            text-shadow: 0 4px 18px rgba(0, 0, 0, 0.36);
        }}
        .tv-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem 0.8rem;
            margin-top: 0.7rem;
            color: rgba(245, 247, 248, 0.94);
            font-size: clamp(0.88rem, 1.02vw, 1.38rem);
            line-height: 1.2;
            font-weight: 600;
        }}
        .tv-meta span + span::before {{
            content: "|";
            color: rgba(245, 247, 248, 0.55);
            margin-right: 0.8rem;
        }}
        .tv-sheet {{
            justify-self: end;
            color: rgba(226, 235, 238, 0.66);
            font-size: clamp(0.78rem, 0.95vw, 1.1rem);
            line-height: 1.45;
            text-align: left;
            padding-bottom: 0.18rem;
        }}
        .tv-sheet strong {{
            display: block;
            color: rgba(226, 235, 238, 0.52);
            font-size: 0.92em;
            font-weight: 600;
            margin-bottom: 0.22rem;
        }}
        .tv-main {{
            min-height: 0;
            display: grid;
            grid-template-columns: minmax(360px, 41%) minmax(520px, 59%);
            gap: clamp(0.9rem, 1.85vw, 2rem);
            align-items: stretch;
        }}
        .tv-product {{
            min-height: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0.2rem 0 0.1rem;
            overflow: hidden;
        }}
        .tv-product img {{
            display: block;
            max-width: 96%;
            max-height: 100%;
            width: auto;
            height: auto;
            object-fit: contain;
            filter: drop-shadow(0 26px 38px rgba(0, 0, 0, 0.45));
        }}
        .tv-image-empty {{
            color: rgba(245, 247, 248, 0.55);
            font-size: 1.25rem;
        }}
        .tv-indicators {{
            min-height: 0;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr)) minmax(130px, 0.34fr);
            grid-template-rows: minmax(148px, 1.2fr) minmax(106px, 0.72fr) minmax(118px, 0.8fr);
            gap: clamp(0.55rem, 0.85vw, 0.8rem);
            align-content: center;
        }}
        .tv-card {{
            min-width: 0;
            border: 1px solid rgba(137, 212, 218, 0.32);
            border-radius: 16px;
            background:
                radial-gradient(circle at 12% 12%, rgba(38, 128, 133, 0.2), transparent 38%),
                linear-gradient(150deg, rgba(4, 46, 58, 0.94), rgba(3, 31, 43, 0.88));
            box-shadow: inset 0 0 22px rgba(36, 194, 202, 0.04), 0 18px 42px rgba(0, 0, 0, 0.18);
            padding: clamp(0.85rem, 1.12vw, 1.35rem);
        }}
        .tv-card-title {{
            color: rgba(245, 247, 248, 0.9);
            font-size: clamp(0.86rem, 1vw, 1.22rem);
            font-weight: 700;
            line-height: 1.1;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }}
        .tv-production-card {{
            grid-column: 1 / -1;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .tv-production-line {{
            display: flex;
            align-items: baseline;
            gap: clamp(0.7rem, 1.3vw, 1.4rem);
            margin-top: 0.1rem;
        }}
        .tv-production-value {{
            color: #f8fbfd;
            font-size: clamp(3.55rem, 5.35vw, 7.1rem);
            line-height: 0.9;
            font-weight: 900;
            text-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
        }}
        .tv-production-total {{
            color: rgba(245, 247, 248, 0.86);
            font-size: clamp(1.35rem, 1.75vw, 2.25rem);
            font-weight: 700;
        }}
        .tv-progress-text {{
            margin-top: 0.65rem;
            color: #26df72;
            font-size: clamp(1.2rem, 1.7vw, 2.1rem);
            font-weight: 800;
        }}
        .tv-progress-track {{
            height: clamp(15px, 1.5vw, 24px);
            border-radius: 999px;
            background: rgba(49, 113, 134, 0.42);
            overflow: hidden;
            margin-top: 0.4rem;
        }}
        .tv-progress-fill {{
            width: {progress_width:.3f}%;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #25db72, #21c966);
            box-shadow: 0 0 24px rgba(37, 219, 114, 0.28);
        }}
        .tv-number-card {{
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .tv-number-value {{
            color: #f8fbfd;
            font-size: clamp(2.75rem, 3.65vw, 5.15rem);
            line-height: 0.9;
            font-weight: 900;
            margin-top: 0.28rem;
        }}
        .tv-number-sub {{
            color: rgba(245, 247, 248, 0.86);
            font-size: clamp(1rem, 1.35vw, 1.7rem);
            font-weight: 600;
            margin-left: 0.25rem;
        }}
        .tv-time-card {{
            grid-column: 1 / 3;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .tv-time-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0;
            align-items: center;
        }}
        .tv-time-item {{
            min-width: 0;
            padding: 0 1rem;
            border-left: 1px solid rgba(245, 247, 248, 0.3);
        }}
        .tv-time-item:first-child {{
            padding-left: 0;
            border-left: 0;
        }}
        .tv-time-label {{
            font-size: clamp(0.88rem, 1vw, 1.24rem);
            line-height: 1.1;
            font-weight: 600;
            color: rgba(245, 247, 248, 0.82);
        }}
        .tv-time-value {{
            font-size: clamp(2.05rem, 2.85vw, 4rem);
            line-height: 0.98;
            font-weight: 900;
            margin-top: 0.25rem;
        }}
        .tv-time-good .tv-time-label,
        .tv-time-good .tv-time-value,
        .tv-footer-good .tv-footer-value,
        .tv-footer-good .tv-footer-sub {{
            color: #29df74;
        }}
        .tv-time-bad .tv-time-label,
        .tv-time-bad .tv-time-value,
        .tv-footer-bad .tv-footer-value,
        .tv-footer-bad .tv-footer-sub {{
            color: #ff483f;
        }}
        .tv-register-card {{
            grid-column: 3 / 4;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .tv-register-card .tv-number-value {{
            font-size: clamp(2.8rem, 3.6vw, 4.85rem);
        }}
        .tv-footer {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: clamp(0.8rem, 1.5vw, 1.45rem);
        }}
        .tv-footer-card {{
            display: grid;
            grid-template-columns: clamp(58px, 5.1vw, 94px) minmax(0, 1fr);
            align-items: center;
            gap: clamp(0.75rem, 1.35vw, 1.45rem);
            min-height: clamp(82px, 9.5vh, 124px);
            padding: clamp(0.7rem, 0.95vw, 1.08rem);
            border-radius: 14px;
        }}
        .tv-footer-mark {{
            width: clamp(58px, 5.1vw, 94px);
            aspect-ratio: 1;
            border-radius: 50%;
            border: 1px solid currentColor;
            opacity: 0.95;
            position: relative;
        }}
        .tv-footer-good .tv-footer-mark {{
            color: #29df74;
        }}
        .tv-footer-neutral .tv-footer-mark {{
            color: rgba(245, 247, 248, 0.74);
        }}
        .tv-footer-bad .tv-footer-mark {{
            color: #ff483f;
        }}
        .tv-footer-mark::before {{
            content: "";
            position: absolute;
            inset: 31%;
            border: 4px solid currentColor;
            border-left: 0;
            border-bottom: 0;
            transform: rotate(-45deg);
        }}
        .tv-footer-bad .tv-footer-mark::before {{
            transform: rotate(135deg);
        }}
        .tv-footer-neutral .tv-footer-mark::before {{
            inset: 25%;
            border-radius: 50%;
            border: 3px solid currentColor;
            transform: none;
        }}
        .tv-footer-title {{
            color: rgba(245, 247, 248, 0.86);
            font-size: clamp(0.95rem, 1.15vw, 1.42rem);
            line-height: 1.08;
            font-weight: 600;
        }}
        .tv-footer-value {{
            color: #f8fbfd;
            font-size: clamp(2.1rem, 3vw, 4.35rem);
            line-height: 0.95;
            font-weight: 900;
            margin-top: 0.18rem;
        }}
        .tv-footer-sub {{
            color: rgba(245, 247, 248, 0.78);
            font-size: clamp(0.8rem, 1vw, 1.25rem);
            line-height: 1.05;
            font-weight: 800;
            text-transform: uppercase;
            overflow-wrap: anywhere;
            margin-top: 0.2rem;
        }}
        @media (max-width: 1100px) {{
            .tv-dashboard {{
                height: auto;
                min-height: 100vh;
                overflow: visible;
            }}
            .tv-header,
            .tv-main,
            .tv-footer {{
                grid-template-columns: 1fr;
            }}
            .tv-sheet {{
                justify-self: start;
            }}
            .tv-indicators {{
                grid-template-columns: 1fr;
                grid-template-rows: none;
            }}
            .tv-production-card,
            .tv-time-card,
            .tv-register-card {{
                grid-column: auto;
            }}
            .tv-product {{
                min-height: 46vh;
            }}
        }}
        </style>
        </head>
        <body>
        <div class="tv-dashboard">
            <header class="tv-header">
                <div>
                    <div class="tv-kicker">Painel TV</div>
                    <div class="tv-title">{_html_text(display_name)}</div>
                    <div class="tv-meta">
                        <span>Número: {_html_text(numero_text)}</span>
                        <span>Maquinário: {_html_text(maquinario_text)}</span>
                        <span>Processo: {_html_text(processo_text)}</span>
                    </div>
                </div>
                <div class="tv-sheet">
                    <strong>Planilha vinculada:</strong>
                    {_html_text(planilha_text)}
                </div>
            </header>
            <main class="tv-main">
                <section class="tv-product">
                    {image_html}
                </section>
                <section class="tv-indicators">
                    <div class="tv-card tv-production-card">
                        <div class="tv-card-title">PRODUÇÃO</div>
                        <div class="tv-production-line">
                            <div class="tv-production-value">{html.escape(produced_text)}</div>
                            <div class="tv-production-total">de {html.escape(total_text)}</div>
                        </div>
                        <div class="tv-progress-text">{html.escape(percent_text)} concluído</div>
                        <div class="tv-progress-track">
                            <div class="tv-progress-fill"></div>
                        </div>
                    </div>
                    <div class="tv-card tv-number-card">
                        <div class="tv-card-title">A PRODUZIR</div>
                        <div>
                            <span class="tv-number-value">{html.escape(remaining_text)}</span>
                            {remaining_unit_html}
                        </div>
                    </div>
                    <div class="tv-card tv-number-card">
                        <div class="tv-card-title">DISPLAYS</div>
                        <div class="tv-number-value">{_html_text(summary.lote_text)}</div>
                    </div>
                    {time_card_html}
                    <div class="tv-card tv-register-card">
                        <div class="tv-card-title">REGISTROS</div>
                        <div class="tv-number-value">{html.escape(format_int(summary.registros))}</div>
                    </div>
                </section>
            </main>
            <footer class="tv-footer">
                {footer_html}
            </footer>
        </div>
        </body>
        </html>
        """,
    ).strip()
    components.html(panel_html, height=900, scrolling=False)


def render_display_panel(
    df: pd.DataFrame,
    filter_context: FilterContext,
    display_selected_override: list[str] | None = None,
    numero_selected_override: list[str] | None = None,
    layout: str = "default",
) -> None:
    if df.empty:
        return

    if layout != "tv":
        st.markdown(
            """
            <style>
            :root {
                --display-panel-shared-height: min(78vh, 980px);
            }
            .display-photo-shell {
                height: var(--display-panel-shared-height);
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }
            .display-photo-shell img {
                width: 100%;
                height: 100%;
                object-fit: contain;
                object-position: center;
                display: block;
            }
            .display-panel-stack {
                height: var(--display-panel-shared-height);
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .display-panel-stack .panel-card {
                flex: 1 1 0;
                min-height: 84px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                overflow: hidden;
                margin-bottom: 0 !important;
            }
            .display-panel-stack .panel-card-emphasis {
                flex: 1.7 1 0;
                justify-content: flex-start;
            }
            .display-panel-stack .panel-card-compact {
                flex: 0.78 1 0;
            }
            .display-panel-stack .panel-card-a-produzir {
                flex: 1.05 1 0;
            }
            .display-panel-stack .panel-title {
                font-size: clamp(0.72rem, 0.22vw + 0.66rem, 0.84rem);
                line-height: 1.2;
                margin-bottom: 0.35rem;
            }
            .display-panel-stack .panel-value {
                font-size: clamp(0.98rem, 0.6vw + 0.8rem, 1.55rem);
                line-height: 1.15;
            }
            .display-panel-stack .panel-sub {
                font-size: clamp(0.72rem, 0.2vw + 0.66rem, 0.84rem);
                line-height: 1.2;
                margin-top: 0.45rem;
            }
            .display-panel-stack .panel-time-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.7rem;
                width: 100%;
            }
            .display-panel-stack .panel-time-item {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 0.18rem;
                align-items: flex-start;
            }
            .display-panel-stack .panel-time-label {
                font-size: clamp(0.8rem, 0.24vw + 0.72rem, 0.92rem);
                font-weight: 700;
                line-height: 1.15;
            }
            .display-panel-stack .panel-time-duration {
                font-size: clamp(0.98rem, 0.56vw + 0.84rem, 1.45rem);
                font-weight: 700;
                line-height: 1.08;
                overflow-wrap: anywhere;
            }
            .display-panel-stack .panel-time-date {
                font-size: clamp(0.82rem, 0.22vw + 0.74rem, 0.96rem);
                font-weight: 600;
                line-height: 1.15;
                overflow-wrap: anywhere;
            }
            @media (max-width: 1450px) {
                :root {
                    --display-panel-shared-height: min(80vh, 1040px);
                }
                .display-panel-stack .panel-time-grid {
                    grid-template-columns: 1fr;
                    gap: 0.55rem;
                }
                .display-panel-stack .panel-card-emphasis {
                    flex: 2.2 1 0;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    operator_count_key = "display_panel_operator_count"
    if layout != "tv":
        operator_count = int(
            st.number_input(
                "Numero de operadores no processo",
                min_value=1,
                max_value=20,
                value=int(st.session_state.get(operator_count_key, 1) or 1),
                step=1,
                key=operator_count_key,
            )
        )
    else:
        operator_count = int(st.session_state.get(operator_count_key, 1) or 1)

    summary = compute_display_panel_summary(
        df,
        filter_context,
        operator_count=operator_count,
        display_selected_override=display_selected_override,
        numero_selected_override=numero_selected_override,
    )
    display_selected = summary.display_selected

    if summary.planilha_warning:
        st.warning(summary.planilha_warning)

    images_dir = Path(__file__).resolve().parent.parent / "FOTOS DISPLAY"
    image_map = build_display_image_map(images_dir)
    image_path = None
    if display_selected:
        key = normalize_display_name(display_selected[0])
        image_path = image_map.get(key)

    if layout == "tv":
        _render_tv_dashboard(
            df=df,
            summary=summary,
            filter_context=filter_context,
            image_path=image_path,
        )
        return

    total_lote_text = (
        format_int(summary.target_total)
        if summary.target_total is not None
        else "Sem meta"
    )

    remaining_text = "Sem meta"
    remaining_sub = None
    if summary.remaining is not None:
        remaining_text = (
            "Concluido"
            if summary.remaining <= 0
            else format_int(summary.remaining)
        )
    if summary.qnt_planilha is not None:
        remaining_sub = f"QNT planilha: {format_int(summary.qnt_planilha)}"

    tempo_value = "Sem meta"
    tempo_subtitle = None
    if summary.remaining is not None:
        if summary.remaining <= 0:
            tempo_value = "Concluido"
        elif summary.time_estimate is not None:
            tempo_subtitle = summary.time_estimate.subtitle
            tempo_value = build_time_estimate_html(
                summary.time_estimate.best_hours,
                summary.time_estimate.avg_hours,
                summary.time_estimate.worst_hours,
                summary.time_estimate.best_finish,
                summary.time_estimate.avg_finish,
                summary.time_estimate.worst_finish,
            )

    col_img, col_info = st.columns([3, 2])
    with col_img:
        if display_selected:
            if image_path:
                if layout == "tv":
                    st.image(str(image_path), width="stretch")
                else:
                    image_uri = load_image_as_data_uri(image_path)
                    if image_uri:
                        st.markdown(
                            f"""
                            <div class="display-photo-shell">
                                <img src="{image_uri}" alt="Imagem do display">
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info("Imagem do display nao encontrada.")
            else:
                st.info("Imagem do display nao encontrada.")
        else:
            st.info("Selecione um display para ver a imagem.")

    with col_info:
        cards_html: list[str] = []
        if summary.planilha_name:
            st.caption(f"Planilha vinculada: {summary.planilha_name}")
        if layout == "tv":
            left_col, right_col = st.columns(2)
            with left_col:
                render_panel_card("DISPLAYS", summary.lote_text)
                render_panel_card("Total do lote", total_lote_text)
                render_panel_card("A produzir", remaining_text, remaining_sub)
            with right_col:
                render_panel_card("Total produzido", format_int(summary.total_produzido))
                render_panel_card("Tempo restante", tempo_value)
                render_panel_card("Registros", format_int(summary.registros))
        else:
            cards_html.extend(
                [
                    build_panel_card_html("DISPLAYS", summary.lote_text),
                    build_panel_card_html("Total do lote", total_lote_text),
                    build_panel_card_html(
                        "Total produzido",
                        format_int(summary.total_produzido),
                    ),
                    build_panel_card_html(
                        "A produzir",
                        remaining_text,
                        remaining_sub,
                        card_class="panel-card-a-produzir",
                    ),
                    build_panel_card_html(
                        "Tempo restante",
                        tempo_value,
                        tempo_subtitle,
                        card_class="panel-card-emphasis",
                        value_is_html=True,
                    ),
                    build_panel_card_html(
                        "Registros",
                        format_int(summary.registros),
                        card_class="panel-card-compact",
                    ),
                ]
            )

        if summary.operator_comparison is not None:
            comparison = summary.operator_comparison
            subtitle = (
                f"{format_percent(comparison.percent, 1)} do total"
                if comparison.percent is not None
                else None
            )
            if layout == "tv":
                render_panel_card(
                    f"Operador: {comparison.label}",
                    format_int(comparison.operator_total),
                    subtitle,
                )
            else:
                cards_html.append(
                    build_panel_card_html(
                        f"Operador: {comparison.label}",
                        format_int(comparison.operator_total),
                        subtitle,
                    )
                )

            ratio_text = (
                format_percent(comparison.ratio, 0)
                if comparison.ratio is not None
                else "N/A"
            )
            subtitle_rate = (
                "Operador: "
                f"{format_float(comparison.rate_operator)}"
                f" | Tempo: {format_duration(comparison.operator_hours)}"
                " | Processo: "
                f"{format_float(comparison.rate_process)}"
                f" | Tempo: {format_duration(comparison.process_hours)}"
                if comparison.rate_operator is not None
                or comparison.rate_process is not None
                or comparison.operator_hours
                or comparison.process_hours
                else None
            )
            if layout == "tv":
                render_panel_card("Media do operador vs processo", ratio_text, subtitle_rate)
            else:
                cards_html.append(
                    build_panel_card_html(
                        "Media do operador vs processo",
                        ratio_text,
                        subtitle_rate,
                    )
                )

        if layout != "tv":
            st.markdown(
                f'<div class="display-panel-stack">{"".join(cards_html)}</div>',
                unsafe_allow_html=True,
            )


def render_tv_panel(df: pd.DataFrame, filter_context: FilterContext) -> None:
    st.markdown(
        """
        <style>
        section.main > div:first-child {
            padding: 8px 10px;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }
        .stApp h1 {
            display: none;
        }
        .panel-card {
            padding: 10px 12px;
            margin-bottom: 8px !important;
        }
        .panel-title {
            font-size: 0.7rem;
        }
        .panel-value {
            font-size: 1.35rem;
            margin-top: 4px;
        }
        .panel-sub {
            font-size: 0.8rem;
        }
        .kpi-card {
            padding: 10px 12px;
        }
        .kpi-title {
            font-size: 0.75rem;
        }
        .kpi-value {
            font-size: 1.6rem;
        }
        .stImage img {
            max-height: 62vh;
            object-fit: contain;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if df.empty:
        st.info("Nenhum dado apos os filtros.")
        return

    display_selected = filter_context.display_selected
    numero_selected = filter_context.numero_display_selected
    if not display_selected or not numero_selected:
        st.info("Selecione o Display/Peca e o Numero display no filtro lateral.")
        return

    combo_cols = [c for c in ["display", "numero_display", "maquinario", "processo"] if c in df.columns]
    combos_df = df[combo_cols].dropna().drop_duplicates()
    sort_cols = [c for c in ["display", "numero_display", "maquinario", "processo"] if c in combos_df.columns]
    if sort_cols:
        combos_df = combos_df.sort_values(sort_cols)
    combos = list(combos_df.itertuples(index=False, name=None))
    if not combos:
        st.info("Sem dados de maquinario/processo para exibir.")
        return

    with st.sidebar:
        st.header("Painel TV")
        auto_rotate = st.checkbox("Rotacao automatica", value=True, key="tv_auto")
        interval = st.number_input(
            "Intervalo (seg)",
            min_value=3,
            max_value=60,
            value=8,
            step=1,
            key="tv_interval",
        )
        labels = [" | ".join(str(val) for val in combo) for combo in combos]
        manual_label = None
        if not auto_rotate:
            manual_label = st.selectbox(
                "Maquinario / Processo",
                labels,
                index=0,
                key="tv_combo_manual",
            )

    index = st.session_state.get("tv_index", 0) % len(combos)
    if not auto_rotate and manual_label is not None:
        try:
            index = labels.index(manual_label)
        except ValueError:
            index = 0

    combo = combos[index]
    display_val = combo[combo_cols.index("display")] if "display" in combo_cols else None
    numero_val = combo[combo_cols.index("numero_display")] if "numero_display" in combo_cols else None
    maquinario = combo[combo_cols.index("maquinario")] if "maquinario" in combo_cols else None
    processo = combo[combo_cols.index("processo")] if "processo" in combo_cols else None

    df_cycle = df
    if display_val is not None and "display" in df_cycle:
        df_cycle = df_cycle[df_cycle["display"] == display_val]
    if numero_val is not None and "numero_display" in df_cycle:
        df_cycle = df_cycle[df_cycle["numero_display"] == numero_val]
    if maquinario is not None and "maquinario" in df_cycle:
        df_cycle = df_cycle[df_cycle["maquinario"] == maquinario]
    if processo is not None and "processo" in df_cycle:
        df_cycle = df_cycle[df_cycle["processo"] == processo]

    base_no_operator_cycle = filter_context.filtered_no_operator
    if not base_no_operator_cycle.empty:
        if display_val is not None and "display" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["display"] == display_val
            ]
        if numero_val is not None and "numero_display" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["numero_display"] == numero_val
            ]
        if maquinario is not None and "maquinario" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["maquinario"] == maquinario
            ]
        if processo is not None and "processo" in base_no_operator_cycle:
            base_no_operator_cycle = base_no_operator_cycle[
                base_no_operator_cycle["processo"] == processo
            ]
    else:
        base_no_operator_cycle = df_cycle

    display_override = [str(display_val)] if display_val is not None else None
    numero_override = [str(numero_val)] if numero_val is not None else None
    cycle_context = filter_context.with_overrides(
        display_selected=display_override or [],
        numero_display_selected=numero_override or [],
        maquinario_selected=[str(maquinario)] if maquinario is not None else [],
        processo_selected=[str(processo)] if processo is not None else [],
        filtered_no_operator=base_no_operator_cycle,
    )
    render_display_panel(
        df_cycle,
        cycle_context,
        display_selected_override=display_override,
        numero_selected_override=numero_override,
        layout="tv",
    )

    if auto_rotate and len(combos) > 1:
        st.session_state["tv_index"] = (index + 1) % len(combos)
        time.sleep(int(interval))
        st.rerun()
