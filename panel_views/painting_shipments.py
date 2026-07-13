from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st


CHART_COLOR_SEQUENCE = ["#4da3ff", "#60d394", "#f5b942", "#ef6f6c", "#9b7ede"]


def _format_quantity(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _clean_group_values(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    return cleaned.fillna("Nao informado").replace(
        {"": "Nao informado", "<NA>": "Nao informado", "None": "Nao informado"}
    )


def _render_empty_charts() -> None:
    for column in st.columns(3):
        with column:
            st.info("Sem dados para exibir neste gráfico.")


def render_painting_shipments(frame: pd.DataFrame) -> None:
    """Renderiza indicadores, graficos e detalhes dos lancamentos de pintura."""
    st.markdown(
        """
        <style>
        .painting-header {
            background: linear-gradient(90deg, #17395c 0%, #2f4f74 45%, #17395c 100%);
            border: 1px solid rgba(200, 216, 236, 0.35);
            border-radius: 10px;
            text-align: center;
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            padding: 10px 12px;
            margin-bottom: 10px;
        }
        </style>
        <div class="painting-header">REMESSAS PINTURA</div>
        """,
        unsafe_allow_html=True,
    )

    quantity = pd.to_numeric(
        frame.get("quantidade", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0)
    total = pd.to_numeric(
        frame.get("quantidade_total", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0)
    metric_cols = st.columns(3)
    metric_values = [
        ("Quantidade lançada", _format_quantity(quantity.sum())),
        ("Quantidade total", _format_quantity(total.sum())),
        ("Remessas / apontamentos", _format_quantity(len(frame))),
    ]
    for column, (label, value) in zip(metric_cols, metric_values):
        with column:
            st.markdown(
                f"""
                <div style="background:rgba(12,41,47,.75);border-radius:12px;
                            padding:12px;min-height:96px;">
                    <div style="color:#d7e4f3;font-size:.95rem;font-weight:600;">
                        {label}
                    </div>
                    <div style="color:#f7fbff;font-size:2rem;font-weight:700;
                                line-height:1.2;margin-top:8px;">
                        {value}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if frame.empty:
        st.info("Nenhum lancamento de pintura encontrado para os filtros selecionados.")
        _render_empty_charts()
        st.markdown("### Lançamentos detalhados")
        st.dataframe(frame, hide_index=True, width="stretch")
        return

    chart_frame = frame.copy()
    chart_frame["quantidade"] = quantity
    for column in ("processo", "codigo_pintura", "display"):
        chart_frame[column] = _clean_group_values(chart_frame[column])
    chart_frame["data_grafico"] = pd.to_datetime(
        chart_frame["data_producao"], errors="coerce"
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
                "codigo_pintura": "Cor / código",
            },
            color_discrete_sequence=CHART_COLOR_SEQUENCE,
        )
        fig_process.update_layout(height=360, margin=dict(l=8, r=8, t=10, b=10))
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
            color_discrete_sequence=[CHART_COLOR_SEQUENCE[0]],
        )
        fig_display.update_layout(height=360, margin=dict(l=8, r=8, t=10, b=10))
        st.plotly_chart(fig_display, width="stretch", config={"displayModeBar": False})

    with chart_cols[2]:
        st.markdown("**Evolução por data**")
        evolution = (
            chart_frame.dropna(subset=["data_grafico"])
            .groupby("data_grafico")["quantidade"]
            .sum()
            .reset_index()
            .sort_values("data_grafico")
        )
        if evolution.empty:
            st.info("Sem datas válidas para exibir a evolução.")
        else:
            evolution["data_label"] = evolution["data_grafico"].dt.strftime("%d/%m/%Y")
            fig_evolution = px.line(
                evolution,
                x="data_label",
                y="quantidade",
                markers=True,
                labels={"data_label": "Data", "quantidade": "Quantidade"},
                color_discrete_sequence=[CHART_COLOR_SEQUENCE[1]],
            )
            fig_evolution.update_layout(height=360, margin=dict(l=8, r=8, t=10, b=10))
            st.plotly_chart(fig_evolution, width="stretch", config={"displayModeBar": False})

    st.markdown("### Lançamentos detalhados")
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
            "numero_display": "Código display",
            "codigo_pintura": "Código pintura",
            "maquinario": "Ferramental",
            "processo": "Processo",
            "quantidade": "Quantidade",
            "quantidade_total": "Quantidade total",
            "timestamp": "Lancado em",
        }
    )
    st.dataframe(details, hide_index=True, width="stretch")
