from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from filters import FilterContext
from panel_views.common import render_prod_hora_kpis
from services.metrics import (
    apply_bar_labels,
    compute_prod_rate,
    format_float,
    format_int,
    format_percent,
    resolve_last_update_metric,
)
from services.planilha_service import (
    build_expected_by_process,
    build_remaining_by_process,
    validate_planilha_configuration,
)


def render_kpis(df: pd.DataFrame, filter_context: FilterContext) -> None:
    total_registros = len(df)
    total_produzida = df["quantidade_produzida"].sum() if "quantidade_produzida" in df else 0
    pecas_mortas = df["pecas_mortas"].sum() if "pecas_mortas" in df else 0
    update_title, update_value = resolve_last_update_metric(df, filter_context)

    processo_total_label = None
    processo_total = None
    if {"processo", "quantidade_produzida"}.issubset(df.columns):
        processos = pd.Series(df["processo"]).dropna().unique()
        if len(processos) == 1:
            processo_total_label = f"Total do processo ({processos[0]})"
        elif len(processos) > 1:
            processo_total_label = "Total processos selecionados"
        else:
            processo_total_label = "Total do processo"
        processo_total = df["quantidade_produzida"].sum()

    if processo_total_label:
        col1, col2, col3, col4, col5 = st.columns(5)
    else:
        col1, col2, col3, col4 = st.columns(4)
    col1.metric("Registros", f"{total_registros:,}".replace(",", "."))
    col2.metric(update_title, update_value)
    col3.metric("Producao total", f"{total_produzida:,.0f}".replace(",", "."))
    col4.metric("Pecas mortas", f"{pecas_mortas:,.0f}".replace(",", "."))
    if processo_total_label:
        col5.metric(processo_total_label, f"{processo_total:,.0f}".replace(",", "."))


def _operator_values(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    if ";" in text:
        return [part.strip() for part in text.split(";") if part.strip()]
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def _build_operator_contribution_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "operador" not in df.columns:
        return pd.DataFrame()

    op_df = df.copy()
    if "operadores_lista" in op_df.columns:
        op_df["operador"] = op_df["operadores_lista"].apply(_operator_values)
    else:
        op_df["operador"] = op_df["operador"].apply(_operator_values)

    op_df["operador_count"] = op_df["operador"].apply(len)
    op_df = op_df[op_df["operador_count"] > 0].copy()
    if op_df.empty:
        return pd.DataFrame()

    op_df = op_df.explode("operador").reset_index(drop=True)
    for col in ["quantidade_produzida", "pecas_mortas"]:
        if col in op_df.columns:
            op_df[col] = pd.to_numeric(op_df[col], errors="coerce").fillna(0)
            op_df[col] = op_df[col] / op_df["operador_count"]
    return op_df


def _build_apontamento_rate_frame(df: pd.DataFrame) -> pd.DataFrame:
    required = {"duracao_horas", "quantidade_produzida"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()

    rate_df = df.dropna(subset=["duracao_horas", "quantidade_produzida"]).copy()
    if rate_df.empty:
        return pd.DataFrame()

    rate_df["duracao_horas"] = pd.to_numeric(rate_df["duracao_horas"], errors="coerce")
    rate_df["quantidade_produzida"] = pd.to_numeric(
        rate_df["quantidade_produzida"], errors="coerce"
    )
    rate_df = rate_df.dropna(subset=["duracao_horas", "quantidade_produzida"])
    rate_df = rate_df[rate_df["duracao_horas"] > 0]
    if rate_df.empty:
        return pd.DataFrame()

    rate_df["prod_hora_apont"] = (
        rate_df["quantidade_produzida"] / rate_df["duracao_horas"]
    )
    rate_df["prod_hora_apont"] = pd.to_numeric(
        rate_df["prod_hora_apont"], errors="coerce"
    )
    return rate_df.dropna(subset=["prod_hora_apont"])


def _render_remaining_process_chart(df: pd.DataFrame, filter_context: FilterContext) -> None:
    maquinario_selected = filter_context.maquinario_selected
    processo_selected = filter_context.processo_selected
    comparing_many_processes = len(processo_selected) >= 2
    if not maquinario_selected or (
        processo_selected and not comparing_many_processes
    ):
        return

    st.markdown("**Faltante por processo (pecas e horas)**")
    remaining_df, warn_msg, planilha_name = build_remaining_by_process(
        df,
        filter_context,
        compute_prod_rate=compute_prod_rate,
    )
    if planilha_name:
        st.caption(f"Planilha vinculada: {planilha_name}")
    if warn_msg:
        st.info(warn_msg)
        return
    if remaining_df.empty:
        st.info("Sem dados para calcular faltante por processo.")
        return

    remaining_df = remaining_df.copy()
    remaining_df["status_conclusao"] = remaining_df["pecas_faltantes"].apply(
        lambda value: "Concluidos" if pd.notna(value) and float(value) <= 0 else "Nao concluidos"
    )

    status_filter = st.radio(
        "Status dos processos",
        ["Todos", "Concluidos", "Nao concluidos"],
        horizontal=True,
        key="remaining_process_status_filter",
    )

    filtered_remaining_df = remaining_df
    if status_filter != "Todos":
        filtered_remaining_df = filtered_remaining_df[
            filtered_remaining_df["status_conclusao"] == status_filter
        ].copy()

    if filtered_remaining_df.empty:
        st.info(f"Sem processos para a visualizacao '{status_filter}'.")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=filtered_remaining_df["processo"],
            y=filtered_remaining_df["pecas_faltantes"],
            name="Pecas faltantes",
            marker_color="#2EA3F2",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=filtered_remaining_df["processo"],
            y=filtered_remaining_df["horas_faltantes"],
            name="Horas faltantes",
            mode="lines+markers",
            yaxis="y2",
            line={"color": "#F39C12", "width": 3},
        )
    )
    fig.update_layout(
        title="Faltante para concluir por processo",
        xaxis={"title": "Processo"},
        yaxis={"title": "Pecas faltantes"},
        yaxis2={
            "title": "Horas faltantes",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        margin={"l": 40, "r": 50, "t": 60, "b": 40},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    table_df = filtered_remaining_df.copy()
    table_df["total_esperado"] = pd.to_numeric(
        table_df["total_esperado"], errors="coerce"
    ).fillna(0)
    table_df["produzido"] = pd.to_numeric(
        table_df["produzido"], errors="coerce"
    ).fillna(0)
    table_df["pecas_faltantes"] = pd.to_numeric(
        table_df["pecas_faltantes"], errors="coerce"
    ).fillna(0)
    table_df["media_prod_hora"] = pd.to_numeric(
        table_df["media_prod_hora"], errors="coerce"
    )
    table_df["horas_faltantes"] = pd.to_numeric(
        table_df["horas_faltantes"], errors="coerce"
    )

    table_display = pd.DataFrame(
        {
            "Processo": table_df["processo"],
            "Status": table_df["status_conclusao"],
            "Total esperado": table_df["total_esperado"].apply(format_int),
            "Total produzido": table_df["produzido"].apply(format_int),
            "Pecas faltantes": table_df["pecas_faltantes"].apply(format_int),
            "Media prod/h": table_df["media_prod_hora"].apply(format_float),
            "Horas faltantes": table_df["horas_faltantes"].apply(format_float),
        }
    )
    st.markdown("**Tabela numerica do faltante por processo**")
    st.dataframe(table_display, width="stretch", hide_index=True)


def _build_daily_operator_rate(df: pd.DataFrame) -> pd.DataFrame:
    required = {"data_producao", "operador", "duracao_horas", "quantidade_produzida"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    rate_df = _build_operator_contribution_frame(df)
    rate_df = rate_df.dropna(
        subset=["data_producao", "operador", "duracao_horas", "quantidade_produzida"]
    ).copy()
    if rate_df.empty:
        return pd.DataFrame()

    rate_df["operador"] = rate_df["operador"].astype(str).str.strip()
    rate_df = rate_df[rate_df["operador"] != ""]
    rate_df["duracao_horas"] = pd.to_numeric(rate_df["duracao_horas"], errors="coerce")
    rate_df["quantidade_produzida"] = pd.to_numeric(
        rate_df["quantidade_produzida"], errors="coerce"
    )
    rate_df = rate_df.dropna(subset=["duracao_horas", "quantidade_produzida"])
    rate_df = rate_df[rate_df["duracao_horas"] > 0]
    if rate_df.empty:
        return pd.DataFrame()

    daily_rate = (
        rate_df.groupby(["data_producao", "operador"], as_index=False)
        .agg(
            quantidade_produzida=("quantidade_produzida", "sum"),
            duracao_horas=("duracao_horas", "sum"),
        )
        .sort_values(["data_producao", "operador"])
    )
    daily_rate["media_prod_hora"] = (
        daily_rate["quantidade_produzida"] / daily_rate["duracao_horas"]
    )
    daily_rate["media_prod_hora"] = pd.to_numeric(
        daily_rate["media_prod_hora"], errors="coerce"
    )
    return daily_rate.dropna(subset=["media_prod_hora"])


def render_charts(df: pd.DataFrame, filter_context: FilterContext) -> None:
    if df.empty:
        st.info("Nenhum dado apos os filtros.")
        return

    col1, col2 = st.columns(2)

    if "data_producao" in df:
        producao_dia = (
            df.groupby("data_producao")["quantidade_produzida"]
            .sum()
            .reset_index()
            .sort_values("data_producao")
        )
        fig = px.bar(
            producao_dia,
            x="data_producao",
            y="quantidade_produzida",
            title="Producao por dia",
            labels={"data_producao": "Data", "quantidade_produzida": "Qtd. produzida"},
        )
        apply_bar_labels(fig)
        col1.plotly_chart(fig, width="stretch")

        if not producao_dia.empty:
            last_row = producao_dia.iloc[-1]
            prev_row = producao_dia.iloc[-2] if len(producao_dia) > 1 else None
            trend_col1, trend_col2 = st.columns(2)
            delta_prev = (
                last_row["quantidade_produzida"] - prev_row["quantidade_produzida"]
                if prev_row is not None
                else None
            )
            trend_col1.metric(
                f"Prod. {last_row['data_producao']}",
                f"{last_row['quantidade_produzida']:,.0f}".replace(",", "."),
                delta=(
                    f"{delta_prev:+,.0f}".replace(",", ".") if delta_prev is not None else "N/A"
                ),
            )
            trend_col2.empty()

        dates_series = pd.to_datetime(producao_dia["data_producao"])
        max_date = dates_series.max()
        if pd.notna(max_date):
            period_a_start = max_date - pd.Timedelta(days=6)
            period_b_start = period_a_start - pd.Timedelta(days=7)
            producao_dia = producao_dia.assign(data_producao_ts=dates_series)

            period_a = producao_dia[producao_dia["data_producao_ts"] >= period_a_start]
            period_b = producao_dia[
                (producao_dia["data_producao_ts"] >= period_b_start)
                & (producao_dia["data_producao_ts"] < period_a_start)
            ]

            chart_col1, chart_col2 = st.columns(2)
            if not period_a.empty:
                fig_period_a = px.bar(
                    period_a,
                    x="data_producao",
                    y="quantidade_produzida",
                    title="Periodo A (ultimos 7 dias)",
                    labels={
                        "data_producao": "Dia",
                        "quantidade_produzida": "Qtd. produzida",
                    },
                )
                apply_bar_labels(fig_period_a)
                chart_col1.plotly_chart(fig_period_a, width="stretch")
            if not period_b.empty:
                fig_period_b = px.bar(
                    period_b,
                    x="data_producao",
                    y="quantidade_produzida",
                    title="Periodo B (7 dias anteriores)",
                    labels={
                        "data_producao": "Dia",
                        "quantidade_produzida": "Qtd. produzida",
                    },
                )
                apply_bar_labels(fig_period_b)
                chart_col2.plotly_chart(fig_period_b, width="stretch")
            else:
                chart_col2.info("Sem dados no periodo B (7 dias anteriores).")

    prod_hora_dia = _build_daily_operator_rate(df)
    if not prod_hora_dia.empty:
        selected_operators = [
            operador
            for operador in filter_context.operador_selected
            if operador in set(prod_hora_dia["operador"])
        ]
        chart_data = prod_hora_dia
        if not selected_operators:
            total_operators = prod_hora_dia["operador"].nunique()
            top_operators = (
                prod_hora_dia.groupby("operador")["quantidade_produzida"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
                .index
            )
            chart_data = prod_hora_dia[prod_hora_dia["operador"].isin(top_operators)].copy()
            if total_operators > len(top_operators):
                st.caption(
                    "Grafico de media/hora exibindo os 10 operadores com maior producao "
                    "nos filtros atuais."
                )

        chart_data = chart_data.copy()
        chart_data["data_label"] = pd.to_datetime(
            chart_data["data_producao"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")
        chart_data["data_label"] = chart_data["data_label"].fillna(
            chart_data["data_producao"].astype(str)
        )
        chart_data["chart_slot"] = [
            f"{date_label} | {operator} | {idx}"
            for idx, (date_label, operator) in enumerate(
                zip(chart_data["data_label"], chart_data["operador"])
            )
        ]
        y_max = chart_data["media_prod_hora"].max()
        y_range = [0, float(y_max) * 1.18] if pd.notna(y_max) and y_max > 0 else None
        hours_max = chart_data["duracao_horas"].max()
        hours_range = (
            [0, float(hours_max) * 1.18]
            if pd.notna(hours_max) and hours_max > 0
            else None
        )
        slot_order = list(chart_data["chart_slot"])
        slot_labels = list(chart_data["data_label"])
        operators = list(dict.fromkeys(chart_data["operador"]))
        palette = [
            "#00E5FF",
            "#FFB000",
            "#FF4D8D",
            "#7CFF6B",
            "#B66DFF",
            "#FF6B35",
            "#4D96FF",
            "#FFD166",
            "#06D6A0",
            "#F15BB5",
        ]

        fig_prod_hora = go.Figure()
        for idx, operator in enumerate(operators):
            operator_data = chart_data[chart_data["operador"] == operator]
            operator_color = palette[idx % len(palette)]
            custom_data = operator_data[
                [
                    "operador",
                    "quantidade_produzida",
                    "duracao_horas",
                    "media_prod_hora",
                    "data_label",
                ]
            ].to_numpy()

            fig_prod_hora.add_trace(
                go.Bar(
                    x=operator_data["chart_slot"],
                    y=operator_data["media_prod_hora"],
                    name=operator,
                    marker_color=operator_color,
                    offsetgroup="media",
                    width=0.34,
                    legendgroup=operator,
                    text=operator_data["media_prod_hora"].map(lambda value: f"{value:.2f}"),
                    texttemplate="<b>%{text}</b>",
                    textposition="outside",
                    textfont={"color": "#F7FBFF", "size": 12},
                    cliponaxis=False,
                    customdata=custom_data,
                    hovertemplate=(
                        "Data=%{customdata[4]}<br>"
                        "Operador=%{customdata[0]}<br>"
                        "Media/hora=%{y:.2f}<br>"
                        "Qtd. produzida=%{customdata[1]:.0f}<br>"
                        "Horas apontadas=%{customdata[2]:.2f}<extra></extra>"
                    ),
                )
            )
            fig_prod_hora.add_trace(
                go.Bar(
                    x=operator_data["chart_slot"],
                    y=operator_data["duracao_horas"],
                    name="Horas apontadas",
                    marker={
                        "color": "rgba(203, 213, 225, 0.72)",
                        "line": {"color": operator_color, "width": 1.3},
                    },
                    offsetgroup="hours",
                    width=0.34,
                    legendgroup="Horas apontadas",
                    showlegend=idx == 0,
                    yaxis="y2",
                    text=operator_data["duracao_horas"].map(lambda value: f"{value:.2f}h"),
                    texttemplate="<b>%{text}</b>",
                    textposition="outside",
                    textfont={"color": "#E2E8F0", "size": 11},
                    cliponaxis=False,
                    customdata=custom_data,
                    hovertemplate=(
                        "Data=%{customdata[4]}<br>"
                        "Operador=%{customdata[0]}<br>"
                        "Horas apontadas=%{y:.2f}<br>"
                        "Qtd. produzida=%{customdata[1]:.0f}<br>"
                        "Media/hora=%{customdata[3]:.2f}<extra></extra>"
                    ),
                )
            )

        fig_prod_hora.update_layout(
            title="Variacao diaria da media/hora por operador",
            barmode="group",
            bargap=0.28,
            bargroupgap=0.22,
            uniformtext_minsize=9,
            uniformtext_mode="show",
            yaxis={"range": y_range, "title": "Media/hora"},
            yaxis2={
                "range": hours_range,
                "title": "Horas apontadas",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
            },
            xaxis={
                "title": "Data",
                "type": "category",
                "categoryorder": "array",
                "categoryarray": slot_order,
                "tickmode": "array",
                "tickvals": slot_order,
                "ticktext": slot_labels,
                "tickangle": -35,
                "automargin": True,
            },
            legend={"title": "Operador / medida"},
            margin={"t": 80, "r": 70},
        )
        st.plotly_chart(fig_prod_hora, width="stretch")

    if "maquinario" in df:
        prod_maquina = (
            df.groupby("maquinario")["quantidade_produzida"]
            .sum()
            .reset_index()
            .sort_values("quantidade_produzida", ascending=False)
        )
        fig = px.bar(
            prod_maquina,
            x="maquinario",
            y="quantidade_produzida",
            title="Producao por maquinario",
            labels={"maquinario": "Maquinario", "quantidade_produzida": "Qtd. produzida"},
        )
        apply_bar_labels(fig)
        col2.plotly_chart(fig, width="stretch")

    col3, col4 = st.columns(2)

    if "operador" in df:
        op_contrib = _build_operator_contribution_frame(df)
        prod_operador = (
            op_contrib.groupby("operador")["quantidade_produzida"]
            .sum()
            .reset_index()
            .sort_values("quantidade_produzida", ascending=False)
            if not op_contrib.empty
            else pd.DataFrame()
        )
        if not prod_operador.empty:
            fig = px.bar(
                prod_operador,
                x="operador",
                y="quantidade_produzida",
                title="Producao por operador",
                labels={"operador": "Operador", "quantidade_produzida": "Qtd. produzida"},
            )
            apply_bar_labels(fig)
            col3.plotly_chart(fig, width="stretch")

    if "display" in df:
        prod_display = (
            df.groupby("display")["quantidade_produzida"]
            .sum()
            .reset_index()
            .sort_values("quantidade_produzida", ascending=False)
            .head(10)
        )
        fig = px.bar(
            prod_display,
            x="display",
            y="quantidade_produzida",
            title="Top 10 displays/pecas",
            labels={"display": "Display/Peca", "quantidade_produzida": "Qtd. produzida"},
        )
        apply_bar_labels(fig)
        col4.plotly_chart(fig, width="stretch")

    _render_remaining_process_chart(df, filter_context)

    prod_cols = {"operador", "duracao_horas", "quantidade_produzida"}
    if prod_cols.issubset(df.columns):
        op_df = _build_operator_contribution_frame(df)
        op_df = op_df.dropna(subset=["operador", "duracao_horas", "quantidade_produzida"]).copy()
        if not op_df.empty:
            op_df = op_df[op_df["duracao_horas"] > 0]
            op_df["prod_hora_apont"] = op_df["quantidade_produzida"] / op_df["duracao_horas"]
            op_df["prod_hora_apont"] = pd.to_numeric(op_df["prod_hora_apont"], errors="coerce")
            op_df = op_df.dropna(subset=["prod_hora_apont"])
            if not op_df.empty:
                render_prod_hora_kpis(op_df, show_info=False)
                apontamento_df = _build_apontamento_rate_frame(df)
                table_cols = [
                    c
                    for c in [
                        "id",
                        "operador",
                        "processo",
                        "data_producao",
                        "quantidade_produzida",
                        "duracao_horas",
                        "prod_hora_apont",
                    ]
                    if c in apontamento_df.columns
                ]
                table = apontamento_df[table_cols].copy().sort_values(
                    "prod_hora_apont", ascending=False
                )
                table["prod_hora_apont"] = table["prod_hora_apont"].round(2)
                if "quantidade_produzida" in table:
                    table["quantidade_produzida"] = table["quantidade_produzida"].round(2)
                if "duracao_horas" in table:
                    table["duracao_horas"] = table["duracao_horas"].round(2)
                st.dataframe(table, hide_index=True, width="stretch")
            else:
                st.info("Sem dados suficientes para calcular produtividade por operador/hora.")
        else:
            st.info("Sem dados de duracao/operador para calcular prod. por hora.")


def render_filtered_table(df: pd.DataFrame, filter_context: FilterContext) -> None:
    st.subheader("Registros filtrados")
    if df.empty:
        st.info("Nenhum registro para exibir.")
        return

    left_col, right_col = st.columns([2, 1])
    with left_col:
        cols = [
            c
            for c in [
                "data_producao",
                "hora_inicio",
                "hora_conclusao",
                "maquinario",
                "operador",
                "display",
                "numero_display",
                "processo",
                "quantidade_produzida",
                "pecas_mortas",
                "observacoes",
            ]
            if c in df.columns
        ]
        table = df[cols]
        if "data_producao" in table:
            table = table.sort_values("data_producao", ascending=False)
        st.dataframe(table, width="stretch")
        st.download_button(
            "Baixar CSV filtrado",
            table.to_csv(index=False, sep=";").encode("utf-8"),
            file_name="registros_filtrados.csv",
            mime="text/csv",
        )

    with right_col:
        st.markdown("**Total esperado por processo**")
        expected_df, warn_msg, planilha_name = build_expected_by_process(
            df,
            filter_context,
            compute_prod_rate=compute_prod_rate,
        )
        if planilha_name:
            st.caption(f"Planilha vinculada: {planilha_name}")
        if warn_msg:
            st.info(warn_msg)
        if expected_df.empty:
            st.info("Sem dados para calcular o total esperado.")
        else:
            expected_df = expected_df.copy()
            if "qnt_por_produto" in expected_df:
                expected_df["qnt_por_produto"] = pd.to_numeric(
                    expected_df["qnt_por_produto"], errors="coerce"
                ).round(2)
            if "total_esperado" in expected_df:
                expected_df["total_esperado"] = pd.to_numeric(
                    expected_df["total_esperado"], errors="coerce"
                ).round(0)
            st.dataframe(expected_df, width="stretch", hide_index=True)


def render_data_quality(df: pd.DataFrame, quality: dict) -> None:
    st.subheader("Integridade dos dados")
    if df.empty:
        st.info("Nenhum dado carregado para verificar integridade.")
        return

    nulls = []
    null_map = quality.get("nulls", {}) if quality else {}
    for col, count in null_map.items():
        perc = (count / len(df) * 100) if len(df) else 0
        nulls.append({"coluna": col, "nulos": count, "%": round(perc, 2)})
    if nulls:
        st.markdown("**Nulos por coluna-chave**")
        st.dataframe(pd.DataFrame(nulls))

    warnings = quality.get("warnings", []) if quality else []
    fixes = quality.get("fixes", []) if quality else []
    planilha_issues = validate_planilha_configuration(df)
    if warnings:
        st.warning("Avisos:\n- " + "\n- ".join(warnings))
    if fixes:
        st.info("Ajustes aplicados automaticamente:\n- " + "\n- ".join(fixes))
    if planilha_issues:
        st.warning("Configuracao de planilhas:\n- " + "\n- ".join(planilha_issues))
