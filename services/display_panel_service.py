from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from filters import FilterContext
from services.metrics import calc_finish_date, compute_prod_rate, is_positive_finite
from services.planilha_service import (
    extract_lote_from_numero_display,
    find_planilha_for_display,
    get_lote_multiplier,
    load_planilha_processes,
    normalize_process_name,
)


@dataclass(slots=True)
class TimeEstimateSummary:
    best_hours: float | None
    avg_hours: float | None
    worst_hours: float | None
    best_finish: object | None
    avg_finish: object | None
    worst_finish: object | None
    subtitle: str


@dataclass(slots=True)
class OperatorComparisonSummary:
    label: str
    total_base: float | None
    operator_total: float | None
    percent: float | None
    rate_operator: float | None
    rate_process: float | None
    operator_hours: float | None
    process_hours: float | None
    ratio: float | None


@dataclass(slots=True)
class DisplayPanelSummary:
    display_selected: list[str]
    numero_selected: list[str]
    df_metrics: pd.DataFrame
    lote_values: list[str]
    lote_text: str
    last_date: object | None
    total_produzido: float
    registros: int
    planilha_name: str | None
    planilha_warning: str | None
    target_total: float | None
    qnt_planilha: float | None
    remaining: float | None
    time_estimate: TimeEstimateSummary | None
    operator_comparison: OperatorComparisonSummary | None


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


def _filter_by_operator_selection(
    df: pd.DataFrame, operator_selected: list[str]
) -> pd.DataFrame:
    if not operator_selected:
        return df
    selected = set(operator_selected)
    if "operadores_lista" in df.columns:
        return df[
            df["operadores_lista"].apply(
                lambda values: bool(selected.intersection(_operator_values(values)))
            )
        ]
    if "operador" in df.columns:
        return df[
            df["operador"].apply(
                lambda value: bool(selected.intersection(_operator_values(value)))
            )
        ]
    return df


def _compute_planilha_totals_by_process(
    df_metrics: pd.DataFrame,
    filtered_plan: pd.DataFrame,
    lote_multiplier: int,
) -> tuple[float | None, float | None, float | None]:
    if filtered_plan.empty or lote_multiplier <= 0:
        return None, None, None

    expected = (
        filtered_plan.groupby("processo_key", as_index=False)["qnt_por_produto"]
        .sum()
        .reset_index(drop=True)
    )
    qnt_sum = pd.to_numeric(expected["qnt_por_produto"], errors="coerce").sum()
    if pd.isna(qnt_sum) or qnt_sum <= 0:
        return None, None, None

    expected["total_esperado"] = (
        pd.to_numeric(expected["qnt_por_produto"], errors="coerce").fillna(0)
        * lote_multiplier
    )

    produced = pd.DataFrame(columns=["processo_key", "produzido"])
    if {"processo", "quantidade_produzida"}.issubset(df_metrics.columns):
        produced = df_metrics[["processo", "quantidade_produzida"]].copy()
        produced["processo_key"] = produced["processo"].apply(normalize_process_name)
        produced = produced[produced["processo_key"].astype("string").str.strip().ne("")]
        produced["produzido"] = pd.to_numeric(
            produced["quantidade_produzida"], errors="coerce"
        ).fillna(0)
        produced = (
            produced.groupby("processo_key", as_index=False)["produzido"]
            .sum()
            .reset_index(drop=True)
        )

    by_process = expected.merge(produced, on="processo_key", how="left")
    by_process["produzido"] = pd.to_numeric(
        by_process["produzido"], errors="coerce"
    ).fillna(0)
    by_process["pecas_faltantes"] = (
        by_process["total_esperado"] - by_process["produzido"]
    ).clip(lower=0)

    return (
        float(qnt_sum * lote_multiplier),
        float(qnt_sum),
        float(by_process["pecas_faltantes"].sum()),
    )


def compute_display_panel_summary(
    df: pd.DataFrame,
    filter_context: FilterContext,
    *,
    operator_count: int,
    display_selected_override: list[str] | None = None,
    numero_selected_override: list[str] | None = None,
) -> DisplayPanelSummary:
    display_selected = (
        display_selected_override
        if display_selected_override is not None
        else filter_context.display_selected
    )
    if not display_selected and "display" in df:
        unique_displays = df["display"].dropna().unique()
        if len(unique_displays) == 1:
            display_selected = [str(unique_displays[0])]

    numero_selected = (
        numero_selected_override
        if numero_selected_override is not None
        else filter_context.numero_display_selected
    )

    df_metrics = df.copy()
    lote_values: list[str] = []
    if "numero_display" in df_metrics:
        df_metrics["lote"] = df_metrics["numero_display"].apply(
            extract_lote_from_numero_display
        )
        if numero_selected:
            selected_lotes = sorted(
                {
                    lote
                    for val in numero_selected
                    for lote in [extract_lote_from_numero_display(val)]
                    if lote
                }
            )
            if selected_lotes:
                df_metrics = df_metrics[df_metrics["lote"].isin(selected_lotes)]
        lote_values = sorted(
            val for val in df_metrics["lote"].dropna().unique() if str(val).strip()
        )

    last_date = None
    if "data_producao" in df_metrics:
        dates = pd.to_datetime(df_metrics["data_producao"], errors="coerce").dropna()
        if not dates.empty:
            last_date = dates.max().date()

    total_produzido = (
        df_metrics["quantidade_produzida"].sum()
        if "quantidade_produzida" in df_metrics
        else 0
    )
    registros = len(df_metrics)

    lote_text = "N/A"
    if lote_values:
        if len(lote_values) == 1:
            lote_text = lote_values[0]
        else:
            preview = ", ".join(lote_values[:3])
            suffix = f" (+{len(lote_values) - 3})" if len(lote_values) > 3 else ""
            lote_text = f"{preview}{suffix}"

    lote_multiplier = get_lote_multiplier(df_metrics)
    target_total = None
    qnt_planilha = None
    remaining_from_planilha = None
    planilha_warning = None
    planilha_path, planilha_name = find_planilha_for_display(display_selected)

    if planilha_path and lote_multiplier > 0:
        try:
            mtime = planilha_path.stat().st_mtime
        except FileNotFoundError:
            mtime = None
        planilha_df = load_planilha_processes(str(planilha_path), mtime)
        if not planilha_df.empty:
            process_keys = {
                normalize_process_name(proc)
                for proc in df_metrics.get("processo", pd.Series(dtype="object")).dropna().unique()
                if normalize_process_name(proc)
            }
            maquinario_keys = {
                normalize_process_name(maq)
                for maq in df_metrics.get("maquinario", pd.Series(dtype="object")).dropna().unique()
                if normalize_process_name(maq)
            }

            filtered_plan = planilha_df
            if process_keys:
                filtered_plan = filtered_plan[filtered_plan["processo_key"].isin(process_keys)]
            if maquinario_keys:
                filtered_plan = filtered_plan[
                    filtered_plan["maquinario_key"].isin(maquinario_keys)
                ]
            (
                target_total,
                qnt_planilha,
                remaining_from_planilha,
            ) = _compute_planilha_totals_by_process(
                df_metrics,
                filtered_plan,
                lote_multiplier,
            )
    elif display_selected and planilha_path is None:
        planilha_warning = "Planilha de processos nao encontrada para o display selecionado."

    if target_total is None and "quantidade_total" in df_metrics:
        target_series = pd.to_numeric(df_metrics["quantidade_total"], errors="coerce")
        df_metrics = df_metrics.assign(quantidade_total_num=target_series)
        if "lote" in df_metrics:
            grouped = df_metrics.dropna(subset=["lote", "quantidade_total_num"])
            if not grouped.empty:
                target_total = grouped.groupby("lote")["quantidade_total_num"].max().sum()
        if target_total is None:
            target_total = target_series.max()
        if pd.notna(target_total):
            target_total = float(target_total)
        else:
            target_total = None

    remaining = (
        remaining_from_planilha
        if remaining_from_planilha is not None
        else target_total - total_produzido
        if target_total is not None
        else None
    )

    rate = None
    if {"duracao_horas", "quantidade_produzida"}.issubset(df_metrics.columns):
        valid = df_metrics[df_metrics["duracao_horas"] > 0]
        if not valid.empty:
            total_hours = valid["duracao_horas"].sum()
            if total_hours > 0:
                rate = valid["quantidade_produzida"].sum() / total_hours

    time_estimate = None
    if remaining is not None and remaining > 0:
        best_rate = None
        avg_rate = None
        worst_rate = None
        if {"duracao_horas", "quantidade_produzida"}.issubset(df_metrics.columns):
            valid_rates = df_metrics[df_metrics["duracao_horas"] > 0].copy()
            if not valid_rates.empty:
                prod_hora = pd.to_numeric(
                    valid_rates["quantidade_produzida"] / valid_rates["duracao_horas"],
                    errors="coerce",
                ).dropna()
                if not prod_hora.empty:
                    best_rate = prod_hora.max()
                    avg_rate = prod_hora.mean()
                    worst_rate = prod_hora.min()
        if best_rate is None and is_positive_finite(rate):
            best_rate = rate
        if avg_rate is None and is_positive_finite(rate):
            avg_rate = rate
        if worst_rate is None and is_positive_finite(rate):
            worst_rate = rate
        best_rate = best_rate * operator_count if is_positive_finite(best_rate) else None
        avg_rate = avg_rate * operator_count if is_positive_finite(avg_rate) else None
        worst_rate = worst_rate * operator_count if is_positive_finite(worst_rate) else None
        best_hours = remaining / best_rate if is_positive_finite(best_rate) else None
        avg_hours = remaining / avg_rate if is_positive_finite(avg_rate) else None
        worst_hours = remaining / worst_rate if is_positive_finite(worst_rate) else None
        time_estimate = TimeEstimateSummary(
            best_hours=best_hours,
            avg_hours=avg_hours,
            worst_hours=worst_hours,
            best_finish=calc_finish_date(last_date, best_hours),
            avg_finish=calc_finish_date(last_date, avg_hours),
            worst_finish=calc_finish_date(last_date, worst_hours),
            subtitle=(
                f"Calculo com {operator_count} operador"
                f"{'es' if operator_count != 1 else ''}"
            ),
        )

    operator_comparison = None
    operator_selected = filter_context.operador_selected
    base_df = filter_context.filtered_no_operator
    if operator_selected and not base_df.empty:
        op_df = _filter_by_operator_selection(base_df, operator_selected)
        total_base = (
            base_df["quantidade_produzida"].sum()
            if "quantidade_produzida" in base_df
            else None
        )
        operator_total = (
            op_df["quantidade_produzida"].sum()
            if "quantidade_produzida" in op_df
            else None
        )
        percent = (
            operator_total / total_base
            if total_base and operator_total is not None
            else None
        )
        rate_operator = compute_prod_rate(op_df)
        rate_process = compute_prod_rate(base_df)
        ratio = None
        if is_positive_finite(rate_operator) and is_positive_finite(rate_process):
            ratio = rate_operator / rate_process
        operator_comparison = OperatorComparisonSummary(
            label=", ".join(operator_selected),
            total_base=total_base,
            operator_total=operator_total,
            percent=percent,
            rate_operator=rate_operator,
            rate_process=rate_process,
            operator_hours=op_df["duracao_horas"].sum() if "duracao_horas" in op_df else None,
            process_hours=base_df["duracao_horas"].sum() if "duracao_horas" in base_df else None,
            ratio=ratio,
        )

    return DisplayPanelSummary(
        display_selected=list(display_selected),
        numero_selected=list(numero_selected),
        df_metrics=df_metrics,
        lote_values=lote_values,
        lote_text=lote_text,
        last_date=last_date,
        total_produzido=float(total_produzido),
        registros=registros,
        planilha_name=planilha_name,
        planilha_warning=planilha_warning,
        target_total=target_total,
        qnt_planilha=qnt_planilha,
        remaining=remaining,
        time_estimate=time_estimate,
        operator_comparison=operator_comparison,
    )
