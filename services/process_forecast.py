from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable

import pandas as pd


MINIMUM_LOTS = 2


@dataclass(frozen=True)
class WorkCalendar:
    daily_hours: float = 9.0
    shift_start: time = time(7, 0)
    productive_weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})
    holidays: frozenset[date] = frozenset()

    def __post_init__(self) -> None:
        if not 0 < self.daily_hours <= 24:
            raise ValueError("Horas produtivas por dia devem estar entre 0 e 24.")
        if not self.productive_weekdays:
            raise ValueError("Selecione ao menos um dia produtivo.")


@dataclass(frozen=True)
class ForecastScenario:
    name: str
    productivity: float
    required_hours: float
    finish_at: datetime


@dataclass
class ForecastResult:
    lots: pd.DataFrame
    scenarios: dict[str, ForecastScenario]
    confidence: str
    coefficient_variation: float | None
    standard_deviation: float | None
    historical_productivity: float | None
    base_comparison: dict[str, object] | None
    exclusions: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_lot_count(self) -> int:
        return len(self.lots)


def require_admin_access(is_admin: bool) -> None:
    if not is_admin:
        raise PermissionError("Funcionalidade exclusiva para administradores.")


def _clean_text(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    return cleaned.mask(cleaned.str.lower().isin(["", "none", "nan", "<na>"]))


def _operator_count(value: object) -> int:
    if isinstance(value, (list, tuple, set)):
        return max(1, len([item for item in value if str(item).strip()]))
    if value is None or (not isinstance(value, (list, tuple, set)) and pd.isna(value)):
        return 1
    text = str(value).strip()
    if not text:
        return 1
    separator = ";" if ";" in text else ","
    return max(1, len([part for part in text.split(separator) if part.strip()]))


def _lote_column(frame: pd.DataFrame) -> str | None:
    for column in ("numero_display", "codigo_lote"):
        if column in frame.columns and _clean_text(frame[column]).notna().any():
            return column
    return None


def prepare_lot_history(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Limpa apontamentos e consolida produtividade por lote comparável.

    O chamador deve filtrar previamente um único display, processo e maquinário.
    Registros concluídos são inferidos pela presença de duração positiva, pois a
    fonte atual não possui coluna formal de status ou de tempo parado.
    """
    exclusions = {
        "duplicados": 0,
        "lote_ausente": 0,
        "quantidade_invalida": 0,
        "duracao_invalida": 0,
        "outliers": 0,
    }
    if df.empty:
        return pd.DataFrame(), exclusions

    for alternatives, label in (
        (("display_clean", "display"), "display"),
        (("processo_clean", "processo"), "processo"),
        (("maquinario_clean", "maquinario"), "maquinário"),
    ):
        column = next((name for name in alternatives if name in df.columns), None)
        if column and _clean_text(df[column]).nunique() > 1:
            raise ValueError(f"A amostra deve conter um único {label} comparável.")

    required = {"quantidade_produzida", "duracao_horas"}
    if not required.issubset(df.columns):
        return pd.DataFrame(), exclusions
    lote_col = _lote_column(df)
    if lote_col is None:
        exclusions["lote_ausente"] = len(df)
        return pd.DataFrame(), exclusions

    work = df.copy()
    before = len(work)
    if "id" in work.columns and work["id"].notna().any():
        work = work.drop_duplicates(subset=["id"], keep="first")
    else:
        signature = [
            col for col in (
                lote_col, "data_producao", "hora_inicio", "hora_conclusao",
                "quantidade_produzida", "duracao_horas", "operador",
                "maquinario", "processo",
            ) if col in work.columns
        ]
        work = work.drop_duplicates(subset=signature, keep="first")
    exclusions["duplicados"] = before - len(work)

    work["lote"] = _clean_text(work[lote_col])
    missing_lot = work["lote"].isna()
    exclusions["lote_ausente"] = int(missing_lot.sum())
    work = work[~missing_lot].copy()

    work["quantidade"] = pd.to_numeric(work["quantidade_produzida"], errors="coerce")
    work["horas"] = pd.to_numeric(work["duracao_horas"], errors="coerce")
    invalid_quantity = work["quantidade"].isna() | (work["quantidade"] <= 0)
    exclusions["quantidade_invalida"] = int(invalid_quantity.sum())
    work = work[~invalid_quantity].copy()
    invalid_duration = work["horas"].isna() | (work["horas"] <= 0)
    exclusions["duracao_invalida"] = int(invalid_duration.sum())
    work = work[~invalid_duration].copy()
    if work.empty:
        return pd.DataFrame(), exclusions

    operator_source = (
        work["operadores_lista"] if "operadores_lista" in work.columns
        else work.get("operador", pd.Series("", index=work.index))
    )
    work["operadores_num"] = operator_source.apply(_operator_count)
    work["horas_operador"] = work["horas"] * work["operadores_num"]
    work["pecas_mortas_num"] = pd.to_numeric(
        work.get("pecas_mortas", pd.Series(0, index=work.index)), errors="coerce"
    ).fillna(0).clip(lower=0)
    work["data_num"] = pd.to_datetime(
        work.get("data_producao", pd.Series(pd.NaT, index=work.index)), errors="coerce"
    )

    lots = (
        work.groupby("lote", as_index=False)
        .agg(
            quantidade_produzida=("quantidade", "sum"),
            duracao_horas=("horas", "sum"),
            horas_operador=("horas_operador", "sum"),
            operadores=("operadores_num", "max"),
            pecas_mortas=("pecas_mortas_num", "sum"),
            data_inicio=("data_num", "min"),
            data_termino=("data_num", "max"),
            apontamentos=("lote", "size"),
        )
    )
    lots["produtividade_por_operador"] = (
        lots["quantidade_produzida"] / lots["horas_operador"]
    )
    lots["produtividade"] = lots["quantidade_produzida"] / lots["duracao_horas"]

    # Tukey (1,5 IQR) só é aplicado quando há ao menos quatro lotes.
    if len(lots) >= 4:
        rates = lots["produtividade_por_operador"]
        q1, q3 = rates.quantile([0.25, 0.75])
        iqr = q3 - q1
        if pd.notna(iqr) and iqr > 0:
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outlier = (rates < lower) | (rates > upper)
            exclusions["outliers"] = int(outlier.sum())
            lots = lots[~outlier].copy()

    return lots.sort_values(["data_inicio", "lote"], na_position="last").reset_index(drop=True), exclusions


def classify_confidence(lot_count: int, coefficient_variation: float | None) -> str:
    if lot_count < MINIMUM_LOTS:
        return "Sem histórico suficiente"
    level = 3 if lot_count >= 10 else 2 if lot_count >= 5 else 1
    if coefficient_variation is not None:
        if coefficient_variation > 0.8:
            level -= 2
        elif coefficient_variation > 0.5:
            level -= 1
    return {3: "Alta", 2: "Média", 1: "Baixa"}.get(max(1, level), "Baixa")


def add_productive_hours(start_at: datetime, hours: float, calendar: WorkCalendar) -> datetime:
    if hours < 0 or not math.isfinite(hours):
        raise ValueError("Horas necessárias devem ser um número positivo.")
    remaining = float(hours)
    current = start_at
    while remaining > 1e-9:
        day = current.date()
        day_start = datetime.combine(day, calendar.shift_start)
        day_end = day_start + timedelta(hours=calendar.daily_hours)
        productive = current.weekday() in calendar.productive_weekdays and day not in calendar.holidays
        if not productive or current >= day_end:
            current = datetime.combine(day + timedelta(days=1), calendar.shift_start)
            continue
        if current < day_start:
            current = day_start
        available = (day_end - current).total_seconds() / 3600
        used = min(available, remaining)
        current += timedelta(hours=used)
        remaining -= used
        if remaining > 1e-9:
            current = datetime.combine(day + timedelta(days=1), calendar.shift_start)
    return current


def _tail_size(count: int) -> int:
    if count <= 2:
        return count
    return min(count, max(2, math.ceil(count * 0.20)))


def compare_base_lot(lots: pd.DataFrame, base_lot: str | None, historical_rate: float) -> dict[str, object] | None:
    if not base_lot:
        return None
    match = lots[lots["lote"].astype(str) == str(base_lot)]
    if match.empty:
        return None
    row = match.iloc[0]
    rate = float(row["produtividade_por_operador"])
    difference = (rate / historical_rate - 1) if historical_rate > 0 else 0.0
    cv = lots["produtividade_por_operador"].std(ddof=1) / historical_rate if len(lots) > 1 else 0
    if abs(difference) <= max(0.10, float(cv or 0)):
        position = "Dentro da faixa esperada"
    elif difference > 0:
        position = "Acima da média"
    else:
        position = "Abaixo da média"
    return {
        "lote": str(base_lot), "productivity_per_operator": rate,
        "difference_percent": difference, "position": position,
        "quantity": float(row["quantidade_produzida"]),
        "hours": float(row["duracao_horas"]), "operators": int(row["operadores"]),
        "scrap": float(row["pecas_mortas"]), "start": row["data_inicio"],
        "finish": row["data_termino"],
    }


def generate_forecast(
    df: pd.DataFrame,
    *,
    planned_quantity: int,
    start_at: datetime,
    planned_operators: int,
    calendar: WorkCalendar,
    planned_machines: int = 1,
    base_lot: str | None = None,
) -> ForecastResult:
    if isinstance(planned_quantity, bool) or int(planned_quantity) != planned_quantity or planned_quantity <= 0:
        raise ValueError("A quantidade planejada deve ser um número inteiro positivo.")
    if isinstance(planned_operators, bool) or int(planned_operators) != planned_operators or planned_operators <= 0:
        raise ValueError("A quantidade de operadores deve ser um número inteiro positivo.")
    if isinstance(planned_machines, bool) or int(planned_machines) != planned_machines or planned_machines <= 0:
        raise ValueError("A quantidade de máquinas deve ser um número inteiro positivo.")

    lots, exclusions = prepare_lot_history(df)
    if len(lots) < MINIMUM_LOTS:
        return ForecastResult(
            lots=lots, scenarios={}, confidence="Sem histórico suficiente",
            coefficient_variation=None, standard_deviation=None,
            historical_productivity=None, base_comparison=None,
            exclusions=exclusions,
            warnings=["São necessários pelo menos 2 lotes válidos e comparáveis."],
        )

    rates = lots["produtividade_por_operador"].astype(float)
    historical_per_operator = float(lots["quantidade_produzida"].sum() / lots["horas_operador"].sum())
    standard_deviation = float(rates.std(ddof=1))
    coefficient_variation = standard_deviation / historical_per_operator if historical_per_operator > 0 else None
    tail = _tail_size(len(lots))
    ordered = rates.sort_values()
    per_operator_rates = {
        "Otimista": float(ordered.tail(tail).median()),
        "Provável": historical_per_operator,
        "Conservador": float(ordered.head(tail).median()),
    }
    # Garante a ordem sem mascarar os valores históricos calculados.
    per_operator_rates["Otimista"] = max(per_operator_rates["Otimista"], historical_per_operator)
    per_operator_rates["Conservador"] = min(per_operator_rates["Conservador"], historical_per_operator)

    scenarios: dict[str, ForecastScenario] = {}
    for name, per_operator_rate in per_operator_rates.items():
        productivity = per_operator_rate * int(planned_operators) * int(planned_machines)
        required = float(planned_quantity) / productivity
        scenarios[name] = ForecastScenario(
            name=name, productivity=productivity, required_hours=required,
            finish_at=add_productive_hours(start_at, required, calendar),
        )

    warnings = []
    if exclusions["outliers"]:
        warnings.append(f"{exclusions['outliers']} lote(s) fora dos limites de Tukey foram excluídos.")
    if coefficient_variation is not None and coefficient_variation > 0.5:
        warnings.append("Alta dispersão histórica; use a previsão com cautela.")
    return ForecastResult(
        lots=lots, scenarios=scenarios,
        confidence=classify_confidence(len(lots), coefficient_variation),
        coefficient_variation=coefficient_variation,
        standard_deviation=standard_deviation,
        historical_productivity=(
            historical_per_operator * int(planned_operators) * int(planned_machines)
        ),
        base_comparison=compare_base_lot(lots, base_lot, historical_per_operator),
        exclusions=exclusions, warnings=warnings,
    )


def parse_holidays(values: Iterable[date | datetime | str]) -> frozenset[date]:
    parsed: set[date] = set()
    for value in values:
        timestamp = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.notna(timestamp):
            parsed.add(timestamp.date())
    return frozenset(parsed)
