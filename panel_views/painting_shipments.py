from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from panel_views.common import build_panel_card_html, load_image_as_data_uri
from services.metrics import format_int
from services.painting_panel_service import (
    compute_painting_panel_summary,
    find_painting_image,
)


CHART_COLOR_SEQUENCE = ["#28d7de", "#60d394", "#f5b942", "#ef6f6c", "#9b7ede"]


def _clean_group_values(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    return cleaned.fillna("Nao informado").replace(
        {"": "Nao informado", "<NA>": "Nao informado", "None": "Nao informado"}
    )


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        .painting-header {
            background:
                radial-gradient(circle at 12% 50%, rgba(36,223,255,.18), transparent 28%),
                linear-gradient(110deg, #061826 0%, #0a3440 52%, #061622 100%);
            border: 1px solid rgba(71,218,229,.45);
            border-radius: 14px;
            text-align: center;
            color: #fff;
            font-size: clamp(1.45rem, 2.2vw, 2.2rem);
            font-weight: 850;
            letter-spacing: .08em;
            padding: 12px 16px;
            margin-bottom: 14px;
            box-shadow: inset 0 0 28px rgba(36,223,255,.05);
        }
        .painting-context {
            color: rgba(225,239,242,.72);
            font-size: .86rem;
            margin: 0 0 8px 2px;
        }
        .painting-photo-shell {
            width: 100%;
            height: min(68vh, 780px);
            min-height: 480px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            padding: 18px;
            border: 1px solid rgba(137,212,218,.32);
            border-radius: 16px;
            background:
                radial-gradient(circle at 40% 42%, rgba(21,98,111,.23), transparent 48%),
                linear-gradient(150deg, rgba(3,22,36,.92), rgba(1,11,22,.94));
        }
        .painting-photo-shell img {
            display: block;
            max-width: 100%;
            max-height: 100%;
            width: auto;
            height: auto;
            object-fit: contain;
            filter: drop-shadow(0 24px 32px rgba(0,0,0,.45));
        }
        .painting-photo-empty {
            color: rgba(235,245,247,.6);
            text-align: center;
            font-size: 1.05rem;
        }
        .painting-card-stack {
            height: min(68vh, 780px);
            min-height: 480px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .painting-card-stack .panel-card {
            flex: 1 1 0;
            min-height: 0;
            margin: 0 !important;
            display: flex;
            flex-direction: column;
            justify-content: center;
            border: 1px solid rgba(137,212,218,.32);
            border-radius: 14px;
            background: rgba(5,34,43,.86);
            padding: clamp(.7rem, 1vw, 1rem);
        }
        .painting-card-stack .panel-title {
            color: #d7e7ea;
            font-size: clamp(.72rem, .9vw, .9rem);
            font-weight: 750;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .35rem;
        }
        .painting-card-stack .panel-value {
            color: #fff;
            font-size: clamp(1.15rem, 1.7vw, 1.8rem);
            font-weight: 800;
            line-height: 1.1;
            overflow-wrap: anywhere;
        }
        .painting-card-stack .panel-sub {
            color: rgba(222,238,241,.72);
            font-size: .8rem;
            margin-top: .35rem;
        }
        .painting-card-stack .painting-card-accent {
            border-color: rgba(36,223,255,.58);
            box-shadow: inset 3px 0 0 #24dfff;
        }
        .painting-card-stack .painting-card-good .panel-value { color: #36df8b; }
        div[data-testid="stTabs"] button[role="tab"] {
            min-height: 44px;
            font-size: .95rem;
            font-weight: 750;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #24dfff;
        }
        @media (max-width: 900px) {
            .painting-photo-shell, .painting-card-stack {
                height: auto;
                min-height: 420px;
            }
        }
        </style>
        <div class="painting-header">REMESSAS PINTURA</div>
        """,
        unsafe_allow_html=True,
    )


def _render_panel(frame: pd.DataFrame) -> None:
    root = Path(__file__).resolve().parent.parent
    summary = compute_painting_panel_summary(
        frame,
        planilhas_dir=root / "planilhas_pintura",
    )
    image_path = find_painting_image(
        root / "FOTOS PINTURA",
        summary.display,
        summary.processo,
    )

    if summary.warning:
        st.warning(summary.warning)

    context_parts = [part for part in (summary.display, summary.processo) if part]
    if summary.planilha_name:
        context_parts.append(f"Planilha vinculada: {summary.planilha_name}")
    st.markdown(
        f'<div class="painting-context">{html.escape("  |  ".join(context_parts))}</div>',
        unsafe_allow_html=True,
    )

    total_text = format_int(summary.total_esperado) if summary.total_esperado is not None else "Sem meta"
    remaining_text = format_int(summary.a_produzir) if summary.a_produzir is not None else "Sem meta"
    if summary.a_produzir is not None and summary.a_produzir <= 0:
        remaining_text = "Concluido"
    qnt_sub = (
        f"QNT planilha: {format_int(summary.qnt_planilha)}"
        if summary.qnt_planilha is not None
        else None
    )

    col_image, col_info = st.columns([3, 2])
    with col_image:
        image_uri = load_image_as_data_uri(image_path) if image_path else None
        if image_uri:
            st.markdown(
                f'<div class="painting-photo-shell"><img src="{image_uri}" '
                f'alt="Display {html.escape(summary.cor or "pintado")}"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="painting-photo-shell"><div class="painting-photo-empty">'
                'Foto nao encontrada para o display e a cor deste processo.'
                '</div></div>',
                unsafe_allow_html=True,
            )

    with col_info:
        cards = [
            build_panel_card_html("COR / PROCESSO", summary.cor or "N/A", summary.processo),
            build_panel_card_html("CODIGO PINTURA", summary.codigo_pintura or "N/A", f"Lote: {summary.lote_text}"),
            build_panel_card_html("TOTAL ESPERADO", total_text, qnt_sub, card_class="painting-card-accent"),
            build_panel_card_html("TOTAL APONTADO", format_int(summary.total_apontado)),
            build_panel_card_html("A PRODUZIR", remaining_text, card_class="painting-card-good"),
            build_panel_card_html("REGISTROS", format_int(summary.registros)),
        ]
        st.markdown(
            f'<div class="painting-card-stack">{"".join(cards)}</div>',
            unsafe_allow_html=True,
        )


def _render_details(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    chart_frame = frame.copy()
    chart_frame["quantidade"] = pd.to_numeric(chart_frame.get("quantidade"), errors="coerce").fillna(0)
    for column in ("processo", "codigo_pintura", "display"):
        chart_frame[column] = _clean_group_values(chart_frame[column])
    chart_frame["data_grafico"] = pd.to_datetime(
        chart_frame.get("data_producao"), errors="coerce"
    )

    chart_cols = st.columns(3)
    with chart_cols[0]:
        st.markdown("**Quantidade por processo / cor**")
        process_data = (
            chart_frame.groupby(["processo", "codigo_pintura"], dropna=False)["quantidade"]
            .sum()
            .reset_index()
        )
        fig_process = px.bar(
            process_data,
            x="processo",
            y="quantidade",
            color="codigo_pintura",
            labels={
                "processo": "Processo",
                "quantidade": "Quantidade",
                "codigo_pintura": "Codigo pintura",
            },
            color_discrete_sequence=CHART_COLOR_SEQUENCE,
        )
        fig_process.update_layout(height=350, margin=dict(l=8, r=8, t=10, b=10))
        st.plotly_chart(fig_process, width="stretch", config={"displayModeBar": False})

    with chart_cols[1]:
        st.markdown("**Quantidade por display**")
        display_data = (
            chart_frame.groupby("display", dropna=False)["quantidade"]
            .sum()
            .sort_values()
            .tail(12)
            .reset_index()
        )
        fig_display = px.bar(
            display_data,
            x="quantidade",
            y="display",
            orientation="h",
            labels={"display": "Display", "quantidade": "Quantidade"},
            color_discrete_sequence=[CHART_COLOR_SEQUENCE[1]],
        )
        fig_display.update_layout(height=350, margin=dict(l=8, r=8, t=10, b=10))
        st.plotly_chart(fig_display, width="stretch", config={"displayModeBar": False})

    with chart_cols[2]:
        st.markdown("**Evolucao por data**")
        evolution = (
            chart_frame.dropna(subset=["data_grafico"])
            .groupby("data_grafico")["quantidade"]
            .sum()
            .reset_index()
            .sort_values("data_grafico")
        )
        if evolution.empty:
            st.info("Sem datas validas para exibir a evolucao.")
        else:
            evolution["data_label"] = evolution["data_grafico"].dt.strftime("%d/%m/%Y")
            fig_evolution = px.line(
                evolution,
                x="data_label",
                y="quantidade",
                markers=True,
                labels={"data_label": "Data", "quantidade": "Quantidade"},
                color_discrete_sequence=[CHART_COLOR_SEQUENCE[0]],
            )
            fig_evolution.update_layout(height=350, margin=dict(l=8, r=8, t=10, b=10))
            st.plotly_chart(fig_evolution, width="stretch", config={"displayModeBar": False})

    st.markdown("### Lancamentos detalhados")
    visible_columns = [
        "id", "data_producao", "hora_lancamento", "cliente", "display",
        "numero_display", "codigo_pintura", "maquinario", "processo",
        "quantidade", "quantidade_total", "timestamp",
    ]
    details = frame[[column for column in visible_columns if column in frame.columns]].copy()
    details = details.rename(
        columns={
            "data_producao": "Data",
            "hora_lancamento": "Hora",
            "cliente": "Cliente",
            "display": "Display",
            "numero_display": "Codigo display",
            "codigo_pintura": "Codigo pintura",
            "maquinario": "Ferramental",
            "processo": "Processo",
            "quantidade": "Quantidade",
            "quantidade_total": "Quantidade total",
            "timestamp": "Lancado em",
        }
    )
    st.dataframe(details, hide_index=True, width="stretch")


def render_painting_shipments(frame: pd.DataFrame) -> None:
    """Renderiza o painel de remessas de pintura no padrao do Painel Display."""
    _render_styles()
    if frame.empty:
        st.info("Nenhum lancamento de pintura encontrado para os filtros selecionados.")
        return
    panel_tab, data_tab = st.tabs(["Painel", "Dados e graficos"])
    with panel_tab:
        _render_panel(frame)
    with data_tab:
        _render_details(frame)
