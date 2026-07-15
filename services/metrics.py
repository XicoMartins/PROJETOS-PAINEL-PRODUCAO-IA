from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from filters import FilterContext
from services.planilha_service import (
    extract_lote_from_numero_display,
    find_planilha_for_display,
    get_lote_multiplier,
    load_planilha_processes,
    normalize_process_name,
)


def apply_bar_labels(fig: px.Figure) -> None:
    fig.update_traces(textposition="outside", texttemplate="<b>%{y:.0f}</b>")
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode="hide")


def format_int(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.0f}".replace(",", ".")


def format_float(value: float | int | None, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.{decimals}f}".replace(",", ".")


def format_percent(value: float | None, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%".replace(",", ".")


def is_positive_finite(value: float | int | None) -> bool:
    if value is None or pd.isna(value):
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return 0 < numeric < float("inf")


def format_duration(hours: float | None) -> str:
    if not is_positive_finite(hours):
        return "N/A"
    total_minutes = int(round(float(hours) * 60))
    h, m = divmod(total_minutes, 60)
    return f"{h}h {m:02d}m"


def format_hours(hours: float | None) -> str:
    if hours is None or pd.isna(hours):
        return "N/A"
    if hours <= 0:
        return "0h"
    rounded = round(float(hours), 1)
    if rounded.is_integer():
        return f"{int(rounded)}h"
    return f"{rounded:.1f}h".replace(".", ",")


def format_date(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        value = value.date()
    return value.strftime("%d/%m/%Y")


def format_datetime(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "N/A"
    return parsed.strftime("%d/%m/%Y %H:%M")


def resolve_last_update_metric(
    df: pd.DataFrame,
    filter_context: FilterContext,
) -> tuple[str, str]:
    base_df = filter_context.filtered_no_operator
    if base_df.empty:
        base_df = df
    if base_df.empty:
        return "Ultima atualizacao", "N/A"

    maquinario_selected = filter_context.maquinario_selected
    processo_selected = filter_context.processo_selected

    if processo_selected:
        title = "Ult. atualizacao processo"
    elif maquinario_selected:
        title = "Ult. atualizacao maquinario"
    else:
        title = "Ultima atualizacao"

    latest_date = None
    if "data_producao" in base_df.columns:
        latest_date = pd.to_datetime(base_df["data_producao"], errors="coerce")

    # A visao geral mostra apenas a data. Hora faz sentido somente quando o
    # usuario esta acompanhando a ultima execucao de maquina ou processo.
    if not maquinario_selected and not processo_selected and latest_date is not None:
        latest_value = latest_date.dropna().max()
        if pd.notna(latest_value):
            return title, format_date(latest_value)

    latest_datetime = None
    if latest_date is not None and latest_date.notna().any():
        time_source = None
        for col in ["hora_conclusao", "hora_inicio"]:
            if col not in base_df.columns:
                continue
            parsed_time = pd.to_datetime(
                base_df[col].astype("string").str.strip(),
                format="%H:%M",
                errors="coerce",
            )
            if parsed_time.notna().any():
                time_source = parsed_time
                break

        if time_source is not None:
            latest_datetime = latest_date + pd.to_timedelta(
                time_source.dt.hour.fillna(0).astype(int), unit="h"
            ) + pd.to_timedelta(
                time_source.dt.minute.fillna(0).astype(int), unit="m"
            )

    if latest_datetime is None and "timestamp" in base_df.columns:
        parsed_timestamp = pd.to_datetime(base_df["timestamp"], errors="coerce")
        if parsed_timestamp.notna().any():
            latest_datetime = parsed_timestamp

    if latest_datetime is not None:
        latest_value = latest_datetime.dropna().max()
        if pd.notna(latest_value):
            return title, format_datetime(latest_value)

    if latest_date is not None:
        latest_value = latest_date.dropna().max()
        if pd.notna(latest_value):
            return title, format_date(latest_value)

    if latest_datetime is not None:
        latest_value = latest_datetime.dropna().max()
        if pd.notna(latest_value):
            return title, format_datetime(latest_value)

    return title, "N/A"


def calc_finish_date(start_date, hours: float | None):
    if start_date is None or hours is None or pd.isna(hours):
        return None
    if hours <= 0:
        return start_date
    remaining = float(hours)
    current = start_date
    while remaining > 0:
        weekday = current.weekday()
        if weekday <= 3:
            day_hours = 9
        elif weekday == 4:
            day_hours = 8
        else:
            day_hours = 0
        if day_hours <= 0:
            current += timedelta(days=1)
            continue
        if remaining <= day_hours:
            return current
        remaining -= day_hours
        current += timedelta(days=1)
    return current


def compute_prod_rate(df: pd.DataFrame) -> float | None:
    if df.empty or "duracao_horas" not in df or "quantidade_produzida" not in df:
        return None
    valid = df[df["duracao_horas"] > 0]
    if valid.empty:
        return None
    total_hours = valid["duracao_horas"].sum()
    if not total_hours or pd.isna(total_hours):
        return None
    return valid["quantidade_produzida"].sum() / total_hours


def working_hours_for_weekday(weekday: int) -> int:
    if weekday <= 3:
        return 9
    if weekday == 4:
        return 8
    return 0


def estimate_capacity_hours(df: pd.DataFrame) -> float | None:
    if "data_producao" not in df.columns:
        return None

    dates = pd.to_datetime(df["data_producao"], errors="coerce").dt.date
    valid_dates = dates.dropna()
    if valid_dates.empty:
        return None

    all_days = pd.Index(sorted(valid_dates.unique()))
    machine_counts = pd.Series(1, index=all_days, dtype="int64")
    if "maquinario" in df.columns:
        machine_base = pd.DataFrame(
            {
                "data_producao": dates,
                "maquinario": (
                    df["maquinario"]
                    .astype("string")
                    .str.strip()
                    .replace(["", "none", "nan", "<na>"], pd.NA)
                ),
            }
        ).dropna(subset=["data_producao"])
        with_machine = machine_base.dropna(subset=["maquinario"])
        if not with_machine.empty:
            machine_counts = with_machine.groupby("data_producao")["maquinario"].nunique()
            machine_counts = machine_counts.reindex(all_days, fill_value=1).clip(lower=1)

    capacity_hours = 0.0
    for work_day, machines in machine_counts.items():
        capacity_hours += working_hours_for_weekday(work_day.weekday()) * int(machines)
    return capacity_hours


def estimate_ideal_rate(df: pd.DataFrame) -> float | None:
    required = {"quantidade_produzida", "duracao_horas"}
    if not required.issubset(df.columns):
        return None

    base = pd.DataFrame(
        {
            "quantidade_produzida": pd.to_numeric(
                df["quantidade_produzida"], errors="coerce"
            ),
            "duracao_horas": pd.to_numeric(df["duracao_horas"], errors="coerce"),
        }
    ).dropna()
    base = base[base["duracao_horas"] > 0]
    if base.empty:
        return None

    rates = base["quantidade_produzida"] / base["duracao_horas"]
    rates = rates[(rates > 0) & rates.notna()]
    if rates.empty:
        return None

    ideal_rate = rates.quantile(0.9)
    if pd.isna(ideal_rate) or ideal_rate <= 0:
        return None
    return float(ideal_rate)


def estimate_target_total(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None

    if {"display", "processo"}.issubset(df.columns):
        target_from_planilha = 0.0
        found_planilha_match = False

        for display in df["display"].dropna().astype("string").str.strip().unique():
            if not display:
                continue

            display_df = df[df["display"].astype("string").str.strip() == display].copy()
            if display_df.empty:
                continue

            planilha_path, _ = find_planilha_for_display([str(display)])
            if planilha_path is None:
                continue

            found_planilha_match = True
            try:
                mtime = planilha_path.stat().st_mtime
            except FileNotFoundError:
                mtime = None

            planilha_df = load_planilha_processes(str(planilha_path), mtime)
            if planilha_df.empty:
                continue

            lote_multiplier = get_lote_multiplier(display_df)
            if lote_multiplier <= 0:
                continue

            process_keys = {
                normalize_process_name(proc)
                for proc in display_df["processo"].dropna().unique()
                if normalize_process_name(proc)
            }
            if not process_keys:
                continue

            filtered_plan = planilha_df[planilha_df["processo_key"].isin(process_keys)]

            if "maquinario" in display_df.columns:
                maquinario_keys = {
                    normalize_process_name(maq)
                    for maq in display_df["maquinario"].dropna().unique()
                    if normalize_process_name(maq)
                }
                if maquinario_keys:
                    filtered_plan = filtered_plan[
                        filtered_plan["maquinario_key"].isin(maquinario_keys)
                    ]

            qnt_sum = filtered_plan["qnt_por_produto"].sum() if not filtered_plan.empty else 0
            if pd.notna(qnt_sum) and qnt_sum > 0:
                target_from_planilha += float(qnt_sum) * lote_multiplier

        if found_planilha_match and target_from_planilha > 0:
            return float(target_from_planilha)

    if "quantidade_total" not in df.columns:
        return None

    target_series = pd.to_numeric(df["quantidade_total"], errors="coerce")
    if not target_series.notna().any():
        return None

    if "numero_display" in df.columns:
        grouped = pd.DataFrame(
            {
                "target": target_series,
                "lote": df["numero_display"].apply(extract_lote_from_numero_display),
            }
        ).dropna(subset=["target", "lote"])
        if not grouped.empty:
            target_total = grouped.groupby("lote")["target"].max().sum()
            if pd.notna(target_total):
                return float(target_total)

    max_target = target_series.max()
    if pd.isna(max_target):
        return None
    return float(max_target)


def compute_dashboard_metrics(df: pd.DataFrame) -> dict[str, float | None]:
    produced = (
        pd.to_numeric(df["quantidade_produzida"], errors="coerce").fillna(0).sum()
        if "quantidade_produzida" in df.columns
        else 0.0
    )
    scrap = (
        pd.to_numeric(df["pecas_mortas"], errors="coerce").fillna(0).sum()
        if "pecas_mortas" in df.columns
        else 0.0
    )
    total_processed = produced + scrap
    quality = produced / total_processed if total_processed > 0 else None

    active_hours = (
        pd.to_numeric(df["duracao_horas"], errors="coerce")
        .fillna(0)
        .clip(lower=0)
        .sum()
        if "duracao_horas" in df.columns
        else 0.0
    )
    capacity_hours = estimate_capacity_hours(df)
    if capacity_hours is None:
        capacity_hours = active_hours
    inactive_hours = max(capacity_hours - active_hours, 0.0)
    availability = active_hours / capacity_hours if capacity_hours > 0 else None
    if availability is not None:
        availability = max(0.0, min(float(availability), 1.0))

    prod_rate = produced / active_hours if active_hours > 0 else None
    ideal_rate = estimate_ideal_rate(df)
    performance = (
        prod_rate / ideal_rate if prod_rate is not None and ideal_rate is not None else None
    )
    if performance is not None:
        performance = max(0.0, min(float(performance), 1.0))

    target_total = estimate_target_total(df)
    productivity = produced / target_total if target_total and target_total > 0 else None
    if productivity is not None:
        productivity = max(0.0, min(float(productivity), 1.0))

    scrap_rate = scrap / total_processed if total_processed > 0 else None
    oee = (
        availability * performance * quality
        if availability is not None and performance is not None and quality is not None
        else None
    )
    if oee is not None:
        oee = max(0.0, min(float(oee), 1.0))

    return {
        "produced": float(produced),
        "scrap": float(scrap),
        "active_hours": float(active_hours),
        "inactive_hours": float(inactive_hours),
        "quality": quality,
        "availability": availability,
        "performance": performance,
        "productivity": productivity,
        "scrap_rate": scrap_rate,
        "oee": oee,
        "target_total": target_total,
    }


def format_period_delta(current: float | None, previous: float | None) -> str:
    if current is None or pd.isna(current):
        return "Sem base comparativa"
    if previous is None or pd.isna(previous):
        return "Sem base comparativa"
    if previous == 0:
        return "Base anterior zerada"
    delta = (float(current) - float(previous)) / float(previous)
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta * 100:.1f}% vs mes anterior"


def format_period_label(period: pd.Period) -> str:
    months = {
        1: "Jan",
        2: "Fev",
        3: "Mar",
        4: "Abr",
        5: "Mai",
        6: "Jun",
        7: "Jul",
        8: "Ago",
        9: "Set",
        10: "Out",
        11: "Nov",
        12: "Dez",
    }
    return f"{months.get(period.month, str(period.month))}/{period.year}"


def build_dashboard_gauge(
    title: str,
    value: float | None,
    inverse: bool = False,
) -> go.Figure:
    has_value = value is not None and not pd.isna(value)
    if not has_value:
        value_pct = 0.0
    else:
        value_pct = max(0.0, min(float(value) * 100, 100.0))

    if inverse:
        steps = [
            {"range": [0, 30], "color": "rgba(39, 174, 96, 0.60)"},
            {"range": [30, 60], "color": "rgba(241, 196, 15, 0.70)"},
            {"range": [60, 100], "color": "rgba(192, 57, 43, 0.70)"},
        ]
        bar_color = "#2ecc71"
    else:
        steps = [
            {"range": [0, 50], "color": "rgba(192, 57, 43, 0.70)"},
            {"range": [50, 75], "color": "rgba(241, 196, 15, 0.70)"},
            {"range": [75, 100], "color": "rgba(39, 174, 96, 0.65)"},
        ]
        bar_color = "#58a6ff"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number" if has_value else "gauge",
            value=value_pct,
            title={"text": title, "font": {"size": 18}},
            number={"suffix": "%", "font": {"size": 30}},
            gauge={
                "shape": "angular",
                "axis": {"range": [0, 100], "tickcolor": "#afc3d9"},
                "bar": {"color": bar_color, "thickness": 0.25},
                "bgcolor": "rgba(18, 40, 66, 0.35)",
                "borderwidth": 1,
                "bordercolor": "rgba(236, 240, 241, 0.25)",
                "steps": steps,
            },
        )
    )
    fig.update_layout(
        height=230,
        margin=dict(l=8, r=8, t=36, b=6),
        paper_bgcolor="rgba(0, 0, 0, 0)",
        font=dict(color="#f5f7f8"),
    )
    if not has_value:
        fig.add_annotation(
            text="N/A",
            x=0.5,
            y=0.18,
            showarrow=False,
            font={"size": 28, "color": "#f5f7f8"},
        )
    return fig
