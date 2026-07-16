from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from panel_views.common import render_dashboard_ranking_card, render_dashboard_top_card
from services.operational_efficiency import (
    OperationalEfficiencyResult,
    build_effective_standard_catalog,
    calculate_efficiency_period_change,
    calculate_operational_efficiency,
)
from services.metrics import (
    build_dashboard_gauge,
    compute_dashboard_metrics,
    format_hours,
    format_int,
    format_period_delta,
    format_period_label,
    format_percent,
)


def aggregate_selected_period(
    df: pd.DataFrame,
    dimension: str | None,
    metric: str,
    *,
    limit: int | None = None,
) -> pd.DataFrame:
    """Aggregate every row that survived the sidebar period and field filters."""
    if not dimension or dimension not in df.columns or metric not in df.columns:
        return pd.DataFrame(columns=[dimension or "dimension", metric])

    work = df[[dimension, metric]].copy()
    labels = work[dimension].astype("string").str.strip()
    invalid_labels = labels.str.lower().isin(["", "none", "nan", "<na>"])
    work[dimension] = labels.mask(invalid_labels, "Nao informado").fillna(
        "Nao informado"
    )
    work[metric] = pd.to_numeric(work[metric], errors="coerce").fillna(0)
    summary = (
        work.groupby(dimension, dropna=False)[metric]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    if limit is not None:
        summary = summary.head(max(int(limit), 0)).reset_index(drop=True)
    return summary


def format_dashboard_scope(df: pd.DataFrame) -> str:
    record_text = f"{format_int(len(df))} registros"
    if "data_producao" not in df.columns:
        return record_text

    dates = pd.to_datetime(df["data_producao"], errors="coerce").dropna()
    if dates.empty:
        return record_text

    start = dates.min().strftime("%d/%m/%Y")
    end = dates.max().strftime("%d/%m/%Y")
    if start == end:
        return f"Periodo analisado: {start} | {record_text}"
    return f"Periodo analisado: {start} a {end} | {record_text}"


def format_reliable_period_delta(
    current: float | None,
    previous: float | None,
) -> str:
    if current is None or previous is None:
        return "Sem base comparativa confiavel"
    return format_period_delta(current, previous)


def format_efficiency_coverage(result: OperationalEfficiencyResult) -> str:
    if result.coverage_hours is None:
        return "Cobertura: N/A"
    return f"Cobertura: {result.coverage_hours * 100:.1f}% das horas".replace(
        ".", ","
    )


def format_efficiency_period_delta(
    current: OperationalEfficiencyResult,
    previous: OperationalEfficiencyResult | None,
) -> str:
    if previous is None:
        return "Sem base comparativa confiavel"
    change = calculate_efficiency_period_change(current, previous)
    if change is None:
        return "Sem base comparativa confiavel"
    sign = "+" if change >= 0 else ""
    return f"{sign}{change * 100:.1f}% vs mes anterior"


def render_production_dashboard(
    df: pd.DataFrame,
    reference_df: pd.DataFrame | None = None,
) -> None:
    st.markdown(
        """
        <style>
        .prod-header {
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
        .prod-top-card {
            background: linear-gradient(180deg, rgba(24, 56, 87, 0.95), rgba(13, 36, 63, 0.95));
            border: 1px solid rgba(192, 214, 238, 0.45);
            border-radius: 14px;
            padding: 12px;
            min-height: 130px;
        }
        .prod-top-title {
            font-size: 0.95rem;
            font-weight: 600;
            color: #d7e4f3;
            margin-bottom: 8px;
        }
        .prod-top-value {
            font-size: clamp(1.35rem, 1.8vw, 2rem);
            font-weight: 700;
            line-height: 1.2;
            color: #f7fbff;
            white-space: nowrap;
        }
        .prod-top-sub {
            margin-top: 8px;
            font-size: 0.82rem;
            color: #b8cae0;
        }
        .prod-meta-card {
            background: linear-gradient(180deg, rgba(25, 52, 75, 0.95), rgba(15, 30, 48, 0.95));
            border: 1px solid rgba(192, 214, 238, 0.4);
            border-radius: 14px;
            padding: 12px;
            min-height: 230px;
        }
        .prod-meta-title {
            font-size: 0.95rem;
            font-weight: 700;
            color: #d7e4f3;
            margin-bottom: 8px;
        }
        .prod-meta-value {
            font-size: clamp(1.35rem, 1.7vw, 1.9rem);
            font-weight: 700;
            line-height: 1.2;
            white-space: nowrap;
        }
        .prod-meta-sub {
            margin-top: 6px;
            font-size: 0.88rem;
            color: #bdd0e5;
        }
        .efficiency-info-row {
            display: flex;
            align-items: center;
            justify-content: center;
            flex-wrap: nowrap;
            gap: 6px 14px;
            width: 100%;
            overflow-x: auto;
            margin: 2px 0 14px;
            padding: 7px 12px;
            border: 1px solid rgba(182, 205, 227, 0.24);
            border-radius: 8px;
            background: rgba(18, 40, 66, 0.35);
            color: #bdd0e5;
            font-size: clamp(0.68rem, 0.75vw, 0.78rem);
            line-height: 1.25;
        }
        .efficiency-info-row span {
            white-space: nowrap;
        }
        .efficiency-info-row strong {
            color: #f5f7f8;
        }
        .prod-rank-item {
            display: grid;
            grid-template-columns: 36px 1fr auto;
            gap: 10px;
            align-items: center;
            border: 1px solid rgba(182, 205, 227, 0.33);
            border-radius: 10px;
            padding: 9px 10px;
            margin-bottom: 8px;
            background: rgba(18, 40, 66, 0.55);
        }
        .prod-rank-pos {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background: linear-gradient(180deg, #f1c40f, #d68910);
            color: #10233b;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
        }
        .prod-rank-name {
            font-weight: 600;
            color: #eef5ff;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .prod-rank-value {
            font-weight: 700;
            color: #cce2ff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="prod-header">DASHBOARD DE PRODUCAO</div>', unsafe_allow_html=True)
    if df.empty:
        st.info("Nenhum dado apos os filtros.")
        return
    st.caption(format_dashboard_scope(df))

    standard_catalog = build_effective_standard_catalog(
        reference_df if reference_df is not None else df,
        df,
    )
    efficiency_result = calculate_operational_efficiency(df, standard_catalog)
    metrics = compute_dashboard_metrics(df, efficiency_result)

    previous_metrics = None
    previous_efficiency_result = None
    current_period_metrics = metrics
    current_efficiency_result = efficiency_result
    current_period = None
    data_series = (
        pd.to_datetime(df["data_producao"], errors="coerce")
        if "data_producao" in df.columns
        else pd.Series(dtype="datetime64[ns]")
    )
    periods = data_series.dt.to_period("M") if not data_series.empty else pd.Series(dtype="period[M]")
    available_periods = sorted(periods.dropna().unique()) if not periods.empty else []
    if available_periods:
        current_period = available_periods[-1]
        current_df = df[periods == current_period]
        current_efficiency_result = calculate_operational_efficiency(
            current_df, standard_catalog
        )
        current_period_metrics = compute_dashboard_metrics(
            current_df, current_efficiency_result
        )
        if len(available_periods) > 1:
            previous_period = available_periods[-2]
            previous_df = df[periods == previous_period]
            previous_efficiency_result = calculate_operational_efficiency(
                previous_df, standard_catalog
            )
            previous_metrics = compute_dashboard_metrics(
                previous_df, previous_efficiency_result
            )

    comparison_prefix = (
        f"{format_period_label(current_period)}: " if current_period is not None else ""
    )
    top_cards = [
        (
            "Producao",
            format_int(metrics["produced"]),
            comparison_prefix + format_period_delta(
                current_period_metrics["produced"],
                previous_metrics["produced"] if previous_metrics else None,
            ),
        ),
        (
            "Horas Ativas",
            format_hours(metrics["active_hours"]),
            comparison_prefix + format_period_delta(
                current_period_metrics["active_hours"],
                previous_metrics["active_hours"] if previous_metrics else None,
            ),
        ),
        (
            "Horas Inativas",
            format_hours(metrics["inactive_hours"]),
            comparison_prefix + format_period_delta(
                current_period_metrics["inactive_hours"],
                previous_metrics["inactive_hours"] if previous_metrics else None,
            ),
        ),
        (
            "Refugo (Pecas)",
            format_int(metrics["scrap"]),
            comparison_prefix + format_period_delta(
                current_period_metrics["scrap"],
                previous_metrics["scrap"] if previous_metrics else None,
            ),
        ),
        (
            "OEE",
            format_percent(metrics["oee"], 2),
            comparison_prefix + format_reliable_period_delta(
                current_period_metrics["oee"],
                previous_metrics["oee"] if previous_metrics else None,
            ),
        ),
    ]

    top_cols = st.columns(5)
    for idx, card in enumerate(top_cards):
        with top_cols[idx]:
            render_dashboard_top_card(card[0], card[1], card[2])

    efficiency_month_delta = format_efficiency_period_delta(
        current_efficiency_result,
        previous_efficiency_result,
    )
    gauge_cols = st.columns(5)
    with gauge_cols[0]:
        st.plotly_chart(
            build_dashboard_gauge("Produtividade", metrics["productivity"]),
            width="stretch",
            config={"displayModeBar": False},
        )
    with gauge_cols[1]:
        st.plotly_chart(
            build_dashboard_gauge(
                "Eficiencia operacional",
                metrics["efficiency_operational"],
                allow_above_100=True,
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
    with gauge_cols[2]:
        st.plotly_chart(
            build_dashboard_gauge("Qualidade", metrics["quality"]),
            width="stretch",
            config={"displayModeBar": False},
        )
    with gauge_cols[3]:
        st.plotly_chart(
            build_dashboard_gauge("Refugo", metrics["scrap_rate"], inverse=True),
            width="stretch",
            config={"displayModeBar": False},
        )
    with gauge_cols[4]:
        target_value = metrics["target_total"]
        planned_text = format_int(target_value) if target_value is not None else "Sem meta"
        produced_text = format_int(metrics["produced"])
        st.markdown(
            f"""
            <div class="prod-meta-card">
                <div class="prod-meta-title">Producao acumulada</div>
                <div class="prod-meta-value">{produced_text}</div>
                <div class="prod-meta-sub">Meta planejada: {planned_text}</div>
                <div class="prod-meta-sub">Refugo: {format_int(metrics["scrap"])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if target_value is not None and target_value > 0:
            progress_percent = max((metrics["produced"] / target_value) * 100, 0)
            st.progress(int(min(progress_percent, 100)))
            st.caption(f"{progress_percent:.0f}% da meta atingida")
        else:
            st.info("Meta indisponivel (coluna quantidade_total vazia).")

    st.markdown(
        f"""
        <div class="efficiency-info-row" title="A eficiencia compara o tempo padrao necessario para produzir a quantidade apontada com o tempo real utilizado. A referencia e a taxa media ponderada do melhor operador de cada display, maquinario e processo.">
            <span><strong>{format_efficiency_coverage(efficiency_result)}</strong></span>
            <span>{comparison_prefix}{efficiency_month_delta.replace(" vs mes anterior", "")}</span>
            <span>Padrao: melhor operador por processo</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not efficiency_result.has_registered_standards:
        st.info(
            "Eficiencia operacional: N/A. Nenhum padrao produtivo foi cadastrado."
        )
    elif not efficiency_result.coverage_sufficient:
        coverage_text = (
            f"{efficiency_result.coverage_hours * 100:.1f}%".replace(".", ",")
            if efficiency_result.coverage_hours is not None
            else "0,0%"
        )
        st.warning(
            "Eficiencia operacional: N/A. "
            f"Cobertura insuficiente: {coverage_text} das horas possuem padrao."
        )
    elif efficiency_result.covered_records < efficiency_result.total_valid_records:
        st.warning("Existem apontamentos sem padrao cadastrado.")

    if efficiency_result.duplicate_standard_count > 0:
        st.warning(
            f"Foram encontradas {efficiency_result.duplicate_standard_count} "
            "combinacoes com padrao duplicado."
        )

    if not efficiency_result.missing_report.empty:
        with st.expander("Ver processos sem padrao de eficiencia"):
            report = efficiency_result.missing_report.rename(
                columns={
                    "display": "Display",
                    "maquinario": "Maquinario",
                    "processo": "Processo",
                    "motivo": "Motivo",
                    "apontamentos_sem_padrao": "Apontamentos sem padrao",
                    "horas_sem_padrao": "Horas sem padrao",
                    "producao_sem_padrao": "Quantidade processada sem padrao",
                }
            )
            st.dataframe(report, width="stretch", hide_index=True)

    available_standards = standard_catalog[
        standard_catalog["standard_rate_pph"].notna()
    ].copy()
    if not available_standards.empty:
        with st.expander("Ver referencias de eficiencia por processo"):
            def _catalog_label(*columns: str) -> pd.Series:
                result = pd.Series(pd.NA, index=available_standards.index)
                for column in columns:
                    if column in available_standards.columns:
                        result = result.fillna(available_standards[column])
                return result

            standards_view = pd.DataFrame(
                {
                    "Display": _catalog_label("display", "display_key"),
                    "Maquinario": _catalog_label(
                        "maquinario_nome", "maquinario", "maquinario_key"
                    ),
                    "Processo": _catalog_label(
                        "processo_nome", "processo", "processo_key"
                    ),
                    "Operador referencia": _catalog_label("reference_operator"),
                    "Pecas por hora padrao": available_standards[
                        "standard_rate_pph"
                    ].round(2),
                    "Registros da referencia": _catalog_label("reference_records"),
                    "Horas da referencia": _catalog_label("reference_hours"),
                    "Origem": _catalog_label("standard_source"),
                }
            ).sort_values(["Display", "Maquinario", "Processo"])
            st.dataframe(standards_view, width="stretch", hide_index=True)

    dashboard_df = df.copy()
    qtd_series = (
        pd.to_numeric(dashboard_df["quantidade_produzida"], errors="coerce")
        if "quantidade_produzida" in dashboard_df.columns
        else pd.Series(0, index=dashboard_df.index, dtype="float64")
    )
    scrap_series = (
        pd.to_numeric(dashboard_df["pecas_mortas"], errors="coerce")
        if "pecas_mortas" in dashboard_df.columns
        else pd.Series(0, index=dashboard_df.index, dtype="float64")
    )
    dashboard_df["quantidade_produzida"] = qtd_series.fillna(0)
    dashboard_df["pecas_mortas"] = scrap_series.fillna(0)
    if "data_producao" in dashboard_df.columns:
        dashboard_df["data_dt"] = pd.to_datetime(
            dashboard_df["data_producao"], errors="coerce"
        )
        dashboard_df["periodo"] = dashboard_df["data_dt"].dt.to_period("M")
    else:
        dashboard_df["data_dt"] = pd.NaT
        dashboard_df["periodo"] = pd.Series(pd.NaT, index=dashboard_df.index)

    setor_col = (
        "maquinario"
        if "maquinario" in dashboard_df.columns
        else ("processo" if "processo" in dashboard_df.columns else None)
    )
    categoria_col = (
        "cliente"
        if "cliente" in dashboard_df.columns
        else ("processo" if "processo" in dashboard_df.columns else setor_col)
    )
    aplicacao_col = (
        "display"
        if "display" in dashboard_df.columns
        else ("processo" if "processo" in dashboard_df.columns else setor_col)
    )

    chart_row1 = st.columns(3)
    with chart_row1[0]:
        st.markdown("**Producao por setor no periodo**")
        if setor_col:
            prod_setor = aggregate_selected_period(
                dashboard_df,
                setor_col,
                "quantidade_produzida",
            )
            if prod_setor.empty:
                st.info("Sem dados para o periodo selecionado.")
            else:
                prod_setor = prod_setor.sort_values(
                    "quantidade_produzida", ascending=True
                )
                fig_setor = px.bar(
                    prod_setor,
                    x="quantidade_produzida",
                    y=setor_col,
                    orientation="h",
                    text="quantidade_produzida",
                )
                fig_setor.update_traces(texttemplate="%{text:.0f}", textposition="auto")
                fig_setor.update_layout(
                    height=max(320, 38 * len(prod_setor) + 90),
                    margin=dict(l=8, r=8, t=10, b=10),
                    xaxis_title="Qtd.",
                    yaxis_title="Setor",
                )
                st.plotly_chart(
                    fig_setor, width="stretch", config={"displayModeBar": False}
                )
        else:
            st.info("Coluna de setor nao encontrada.")

    with chart_row1[1]:
        st.markdown("**Share por categoria**")
        if categoria_col:
            share_cat = (
                dashboard_df.groupby(categoria_col)["quantidade_produzida"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            if share_cat.empty:
                st.info("Sem dados para a distribuicao.")
            else:
                top_share = share_cat.head(5).copy()
                if len(share_cat) > 5:
                    outros = share_cat.iloc[5:]["quantidade_produzida"].sum()
                    top_share = pd.concat(
                        [
                            top_share,
                            pd.DataFrame(
                                [{categoria_col: "Outros", "quantidade_produzida": outros}]
                            ),
                        ],
                        ignore_index=True,
                    )
                fig_share = px.pie(
                    top_share,
                    names=categoria_col,
                    values="quantidade_produzida",
                    hole=0.58,
                )
                fig_share.update_traces(textposition="outside", textinfo="percent+label")
                fig_share.update_layout(height=320, margin=dict(l=8, r=8, t=10, b=10))
                st.plotly_chart(
                    fig_share, width="stretch", config={"displayModeBar": False}
                )
        else:
            st.info("Coluna de categoria nao encontrada.")

    with chart_row1[2]:
        st.markdown("**Analise de producao**")
        monthly_base = dashboard_df.dropna(subset=["periodo"])
        if monthly_base.empty:
            st.info("Sem dados de data para analise mensal.")
        else:
            monthly_prod = (
                monthly_base.groupby("periodo")["quantidade_produzida"]
                .sum()
                .reset_index()
                .sort_values("periodo")
            )
            monthly_prod["rotulo"] = monthly_prod["periodo"].apply(format_period_label)
            monthly_prod["media_movel"] = (
                monthly_prod["quantidade_produzida"].rolling(3, min_periods=1).mean()
            )
            fig_analysis = go.Figure()
            fig_analysis.add_trace(
                go.Bar(
                    x=monthly_prod["rotulo"],
                    y=monthly_prod["quantidade_produzida"],
                    name="Producao",
                )
            )
            fig_analysis.add_trace(
                go.Scatter(
                    x=monthly_prod["rotulo"],
                    y=monthly_prod["media_movel"],
                    mode="lines+markers",
                    name="Media movel 3m",
                    line=dict(color="#ff6b6b", width=3),
                )
            )
            fig_analysis.update_layout(
                height=320,
                margin=dict(l=8, r=8, t=10, b=10),
                xaxis_title="Mes",
                yaxis_title="Qtd.",
            )
            st.plotly_chart(
                fig_analysis, width="stretch", config={"displayModeBar": False}
            )

    chart_row2 = st.columns(3)
    with chart_row2[0]:
        st.markdown("**Refugo por setor no periodo**")
        if setor_col:
            refugo_setor = aggregate_selected_period(
                dashboard_df,
                setor_col,
                "pecas_mortas",
            )
            if refugo_setor.empty:
                st.info("Sem dados de refugo para o periodo selecionado.")
            else:
                refugo_setor = refugo_setor.sort_values(
                    "pecas_mortas", ascending=True
                )
                fig_refugo = px.bar(
                    refugo_setor,
                    x="pecas_mortas",
                    y=setor_col,
                    orientation="h",
                    text="pecas_mortas",
                )
                fig_refugo.update_traces(texttemplate="%{text:.0f}", textposition="auto")
                fig_refugo.update_layout(
                    height=max(320, 38 * len(refugo_setor) + 90),
                    margin=dict(l=8, r=8, t=10, b=10),
                    xaxis_title="Refugo",
                    yaxis_title="Setor",
                )
                st.plotly_chart(
                    fig_refugo, width="stretch", config={"displayModeBar": False}
                )
        else:
            st.info("Coluna de setor nao encontrada.")

    with chart_row2[1]:
        st.markdown("**Ranking por setor no periodo**")
        if setor_col:
            ranking_setor = aggregate_selected_period(
                dashboard_df,
                setor_col,
                "quantidade_produzida",
                limit=3,
            )
            render_dashboard_ranking_card(ranking_setor, setor_col, format_int)
        else:
            st.info("Coluna de setor nao encontrada.")

    with chart_row2[2]:
        st.markdown("**Producao por aplicacao no periodo**")
        if aplicacao_col:
            prod_app = aggregate_selected_period(
                dashboard_df,
                aplicacao_col,
                "quantidade_produzida",
            )
            prod_app = prod_app.sort_values("quantidade_produzida", ascending=True)
            if prod_app.empty:
                st.info("Sem dados por aplicacao no periodo selecionado.")
            else:
                fig_app = px.bar(
                    prod_app,
                    x="quantidade_produzida",
                    y=aplicacao_col,
                    orientation="h",
                    text="quantidade_produzida",
                )
                fig_app.update_traces(texttemplate="%{text:.0f}", textposition="outside")
                fig_app.update_layout(
                    height=320,
                    margin=dict(l=8, r=8, t=10, b=10),
                    xaxis_title="Qtd.",
                    yaxis_title="Aplicacao",
                )
                st.plotly_chart(
                    fig_app, width="stretch", config={"displayModeBar": False}
                )
        else:
            st.info("Coluna de aplicacao nao encontrada.")
