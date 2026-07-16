from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from services.planilha_service import (
    find_planilha_for_display,
    load_planilha_processes,
    normalize_planilha_lookup_key,
    normalize_process_name,
)


MIN_STANDARD_COVERAGE_HOURS = 0.80
MISSING_REPORT_COLUMNS = [
    "display",
    "maquinario",
    "processo",
    "motivo",
    "apontamentos_sem_padrao",
    "horas_sem_padrao",
    "producao_sem_padrao",
]


@dataclass(slots=True)
class OperationalEfficiencyResult:
    """Weighted operational efficiency and standard-coverage diagnostics.

    ``raw_efficiency`` is ``sum(standard hours) / sum(real covered hours)``.
    Standard hours use good production plus scrap so quality remains the single
    OEE component that penalizes scrap. ``oee_efficiency`` caps the raw factor
    to [0, 1], while the raw value remains available for display above 100%.
    Efficiency is unavailable until covered hours reach ``coverage_threshold``.
    """

    raw_efficiency: float | None = None
    oee_efficiency: float | None = None
    standard_hours: float = 0.0
    covered_real_hours: float = 0.0
    total_valid_hours: float = 0.0
    coverage_hours: float | None = None
    covered_records: int = 0
    total_valid_records: int = 0
    coverage_records: float | None = None
    invalid_records: int = 0
    has_registered_standards: bool = False
    duplicate_standard_count: int = 0
    coverage_threshold: float = MIN_STANDARD_COVERAGE_HOURS
    missing_report: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=MISSING_REPORT_COLUMNS)
    )

    @property
    def coverage_sufficient(self) -> bool:
        return (
            self.coverage_hours is not None
            and self.coverage_hours >= self.coverage_threshold
        )


def _clean_optional_text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text


def _display_key(value) -> str:
    text = _clean_optional_text(value)
    return normalize_planilha_lookup_key(text) if text else ""


def _process_key(value) -> str:
    text = _clean_optional_text(value)
    return normalize_process_name(text) if text else ""


def _positive_rate(value) -> float | None:
    normalized = (
        str(value).strip().replace(",", ".")
        if isinstance(value, str)
        else value
    )
    numeric = pd.to_numeric(pd.Series([normalized]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    numeric = float(numeric)
    if not math.isfinite(numeric) or numeric <= 0:
        return None
    return numeric


def calculate_standard_hours(
    quantity_processed: float | int | None,
    standard_rate_pph: float | int | None,
) -> float | None:
    """Return required standard hours as processed quantity / pieces per hour."""
    quantity = pd.to_numeric(pd.Series([quantity_processed]), errors="coerce").iloc[0]
    rate = _positive_rate(standard_rate_pph)
    if pd.isna(quantity) or rate is None:
        return None
    quantity = float(quantity)
    if not math.isfinite(quantity) or quantity < 0:
        return None
    return quantity / rate


def calculate_efficiency_period_change(
    current: OperationalEfficiencyResult,
    previous: OperationalEfficiencyResult,
) -> float | None:
    """Return period-over-period change only for two reliable efficiencies."""
    if current.raw_efficiency is None or previous.raw_efficiency is None:
        return None
    if previous.raw_efficiency == 0:
        return None
    change = (current.raw_efficiency - previous.raw_efficiency) / previous.raw_efficiency
    return float(change) if math.isfinite(change) else None


def load_standard_catalog_for_entries(entries: pd.DataFrame) -> pd.DataFrame:
    """Load exact process/machine standards for every display in the entries."""
    if entries.empty or "display" not in entries.columns:
        return pd.DataFrame()

    catalog_parts = []
    displays = [
        text
        for value in entries["display"].dropna().unique()
        if (text := _clean_optional_text(value))
    ]
    for display in displays:
        planilha_path, _ = find_planilha_for_display([display])
        if planilha_path is None:
            continue
        try:
            mtime = Path(planilha_path).stat().st_mtime
        except FileNotFoundError:
            mtime = None
        plan = load_planilha_processes(str(planilha_path), mtime)
        if plan.empty:
            continue
        plan = plan.copy()
        plan["display"] = display
        plan["display_key"] = _display_key(display)
        catalog_parts.append(plan)

    if not catalog_parts:
        return pd.DataFrame()
    return pd.concat(catalog_parts, ignore_index=True)


def _operator_values(row: pd.Series) -> list[str]:
    values = row.get("operadores_lista")
    if isinstance(values, (list, tuple, set)):
        operators = values
    else:
        operator = _clean_optional_text(row.get("operador"))
        operators = operator.split(";") if operator else []
    return [
        text
        for value in operators
        if (text := _clean_optional_text(value)) is not None
    ]


def build_best_operator_standard_catalog(entries: pd.DataFrame) -> pd.DataFrame:
    """Build one historical pieces/hour standard per production combination.

    For every exact display + machine + process combination, each operator's
    weighted throughput is ``sum(good + scrap) / sum(valid real hours)``. The
    operator with the highest finite positive throughput becomes the historical
    reference. Multi-operator entries contribute the same observed throughput
    to every named operator because the record represents their shared work.
    """
    output_columns = [
        "display",
        "maquinario",
        "processo",
        "display_key",
        "maquinario_key",
        "processo_key",
        "standard_rate_pph",
        "standard_source",
        "standard_duplicate",
        "has_standard_value",
        "reference_operator",
        "reference_records",
        "reference_hours",
        "reference_processed_quantity",
    ]
    if entries is None or entries.empty:
        return pd.DataFrame(columns=output_columns)

    work = entries.copy()
    work["real_hours"] = pd.to_numeric(
        work.get("duracao_horas", pd.Series(pd.NA, index=work.index)),
        errors="coerce",
    )
    work["good_quantity"] = pd.to_numeric(
        work.get("quantidade_produzida", pd.Series(pd.NA, index=work.index)),
        errors="coerce",
    )
    work["scrap_quantity"] = pd.to_numeric(
        work.get("pecas_mortas", pd.Series(0, index=work.index)),
        errors="coerce",
    )
    work["processed_quantity"] = work["good_quantity"] + work["scrap_quantity"]
    work["display_key"] = work.get(
        "display", pd.Series(pd.NA, index=work.index)
    ).apply(_display_key)
    work["maquinario_key"] = work.get(
        "maquinario", pd.Series(pd.NA, index=work.index)
    ).apply(_process_key)
    work["processo_key"] = work.get(
        "processo", pd.Series(pd.NA, index=work.index)
    ).apply(_process_key)
    work["display_label"] = work.get(
        "display", pd.Series(pd.NA, index=work.index)
    ).apply(_clean_optional_text)
    work["maquinario_label"] = work.get(
        "maquinario", pd.Series(pd.NA, index=work.index)
    ).apply(_clean_optional_text)
    work["processo_label"] = work.get(
        "processo", pd.Series(pd.NA, index=work.index)
    ).apply(_clean_optional_text)
    work["operators"] = work.apply(_operator_values, axis=1)

    valid = (
        work["real_hours"].notna()
        & work["good_quantity"].notna()
        & work["scrap_quantity"].notna()
        & work["real_hours"].apply(lambda value: math.isfinite(value) and value > 0)
        & work["good_quantity"].apply(lambda value: math.isfinite(value) and value >= 0)
        & work["scrap_quantity"].apply(lambda value: math.isfinite(value) and value >= 0)
        & work["display_key"].ne("")
        & work["maquinario_key"].ne("")
        & work["processo_key"].ne("")
        & work["operators"].apply(bool)
    )
    work = work.loc[valid].explode("operators")
    if work.empty:
        return pd.DataFrame(columns=output_columns)
    work["operator_key"] = work["operators"].apply(_process_key)
    work = work[work["operator_key"].ne("")]

    group_columns = [
        "display_key",
        "maquinario_key",
        "processo_key",
        "operator_key",
    ]
    rates = (
        work.groupby(group_columns, dropna=False)
        .agg(
            display=("display_label", "first"),
            maquinario=("maquinario_label", "first"),
            processo=("processo_label", "first"),
            reference_operator=("operators", "first"),
            reference_records=("processed_quantity", "size"),
            reference_hours=("real_hours", "sum"),
            reference_processed_quantity=("processed_quantity", "sum"),
        )
        .reset_index()
    )
    rates["standard_rate_pph"] = (
        rates["reference_processed_quantity"] / rates["reference_hours"]
    )
    rates = rates[
        rates["standard_rate_pph"].apply(
            lambda value: math.isfinite(value) and value > 0
        )
    ].copy()
    if rates.empty:
        return pd.DataFrame(columns=output_columns)

    rates = rates.sort_values(
        group_columns[:-1] + ["standard_rate_pph", "operator_key"],
        ascending=[True, True, True, False, True],
    )
    best = rates.drop_duplicates(group_columns[:-1], keep="first").copy()
    best["standard_source"] = "melhor_operador_historico"
    best["standard_duplicate"] = False
    best["has_standard_value"] = True
    return best[output_columns].reset_index(drop=True)


def combine_standard_catalogs(
    explicit: pd.DataFrame | None,
    historical: pd.DataFrame | None,
) -> pd.DataFrame:
    """Prefer explicit spreadsheet standards and fill gaps from history."""
    explicit_catalog = _prepare_catalog(explicit)
    historical_catalog = _prepare_catalog(historical)
    if explicit_catalog.empty:
        return historical_catalog
    if historical_catalog.empty:
        return explicit_catalog

    key_columns = ["display_key", "maquinario_key", "processo_key"]
    blocking_explicit = explicit_catalog[
        explicit_catalog["has_standard_value"]
        | explicit_catalog["standard_duplicate"]
    ].copy()
    blocked_keys = set(
        blocking_explicit[key_columns].itertuples(index=False, name=None)
    )
    historical_fallback = historical_catalog[
        ~historical_catalog[key_columns].apply(tuple, axis=1).isin(blocked_keys)
    ]
    return pd.concat(
        [blocking_explicit, historical_fallback], ignore_index=True, sort=False
    )


def build_effective_standard_catalog(
    reference_entries: pd.DataFrame,
    target_entries: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return spreadsheet standards plus best-operator historical fallbacks."""
    targets = reference_entries if target_entries is None else target_entries
    explicit = load_standard_catalog_for_entries(targets)
    historical = build_best_operator_standard_catalog(reference_entries)
    return combine_standard_catalogs(explicit, historical)


def _prepare_catalog(standards: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "display",
        "display_key",
        "maquinario_key",
        "processo_key",
        "standard_rate_pph",
        "standard_duplicate",
        "has_standard_value",
    ]
    if standards is None or standards.empty:
        return pd.DataFrame(columns=columns)

    catalog = standards.copy()
    if "display_key" not in catalog.columns:
        catalog["display_key"] = catalog.get(
            "display", pd.Series(pd.NA, index=catalog.index)
        ).apply(_display_key)
    else:
        catalog["display_key"] = catalog["display_key"].apply(_display_key)

    if "maquinario_key" not in catalog.columns:
        catalog["maquinario_key"] = catalog.get(
            "maquinario", pd.Series(pd.NA, index=catalog.index)
        ).apply(_process_key)
    else:
        catalog["maquinario_key"] = catalog["maquinario_key"].apply(_process_key)

    if "processo_key" not in catalog.columns:
        catalog["processo_key"] = catalog.get(
            "processo", pd.Series(pd.NA, index=catalog.index)
        ).apply(_process_key)
    else:
        catalog["processo_key"] = catalog["processo_key"].apply(_process_key)

    if "standard_rate_pph" not in catalog.columns:
        catalog["standard_rate_pph"] = pd.NA
    catalog["standard_rate_pph"] = catalog["standard_rate_pph"].apply(
        _positive_rate
    )
    if "standard_duplicate" not in catalog.columns:
        catalog["standard_duplicate"] = False
    catalog["standard_duplicate"] = catalog["standard_duplicate"].fillna(False).astype(bool)
    if "has_standard_value" not in catalog.columns:
        catalog["has_standard_value"] = catalog["standard_rate_pph"].notna()
    catalog["has_standard_value"] = catalog["has_standard_value"].fillna(False).astype(bool)
    return catalog


def _index_catalog(catalog: pd.DataFrame, columns: list[str]) -> dict[tuple, list[dict]]:
    index: dict[tuple, list[dict]] = {}
    for row in catalog.to_dict("records"):
        key = tuple(row.get(column, "") for column in columns)
        index.setdefault(key, []).append(row)
    return index


def _resolve_candidates(candidates: list[dict] | None) -> tuple[float | None, str]:
    if not candidates:
        return None, "Sem padrao cadastrado"
    if len(candidates) != 1:
        return None, "Associacao ambigua"
    candidate = candidates[0]
    if bool(candidate.get("standard_duplicate", False)):
        return None, "Padrao duplicado"
    rate = _positive_rate(candidate.get("standard_rate_pph"))
    if rate is None:
        return None, "Sem padrao cadastrado"
    return rate, "Coberto"


def _build_missing_standard_report(work: pd.DataFrame) -> pd.DataFrame:
    missing = work[work["valid_record"] & ~work["covered"]].copy()
    if missing.empty:
        return pd.DataFrame(columns=MISSING_REPORT_COLUMNS)

    for source, target in (
        ("display", "display_label"),
        ("maquinario", "maquinario_label"),
        ("processo", "processo_label"),
    ):
        if source in missing.columns:
            missing[target] = missing[source].apply(
                lambda value: _clean_optional_text(value) or "Nao informado"
            )
        else:
            missing[target] = "Nao informado"

    report = (
        missing.groupby(
            ["display_label", "maquinario_label", "processo_label", "standard_reason"],
            dropna=False,
        )
        .agg(
            apontamentos_sem_padrao=("standard_reason", "size"),
            horas_sem_padrao=("real_hours", "sum"),
            producao_sem_padrao=("processed_quantity", "sum"),
        )
        .reset_index()
        .rename(
            columns={
                "display_label": "display",
                "maquinario_label": "maquinario",
                "processo_label": "processo",
                "standard_reason": "motivo",
            }
        )
        .sort_values("horas_sem_padrao", ascending=False)
        .reset_index(drop=True)
    )
    return report[MISSING_REPORT_COLUMNS]


def calculate_operational_efficiency(
    entries: pd.DataFrame,
    standards: pd.DataFrame | None = None,
    *,
    coverage_threshold: float = MIN_STANDARD_COVERAGE_HOURS,
) -> OperationalEfficiencyResult:
    """Calculate weighted efficiency from standard hours and covered real hours.

    Valid entries require positive real duration plus non-negative numeric good
    production and scrap. Processed quantity is good production + scrap so scrap
    is penalized only by OEE quality. Matching is exact and follows: display +
    machine + process; display + process when machine is absent; display + machine
    when process is absent. Ambiguous and duplicate standards remain uncovered.
    """
    threshold = max(0.0, min(float(coverage_threshold), 1.0))
    if entries is None or entries.empty:
        return OperationalEfficiencyResult(coverage_threshold=threshold)

    work = entries.copy()
    work["real_hours"] = pd.to_numeric(
        work.get("duracao_horas", pd.Series(pd.NA, index=work.index)),
        errors="coerce",
    )
    work["good_quantity"] = pd.to_numeric(
        work.get("quantidade_produzida", pd.Series(pd.NA, index=work.index)),
        errors="coerce",
    )
    work["scrap_quantity"] = pd.to_numeric(
        work.get("pecas_mortas", pd.Series(0, index=work.index)),
        errors="coerce",
    )
    work["processed_quantity"] = work["good_quantity"] + work["scrap_quantity"]
    work["valid_record"] = (
        work["real_hours"].notna()
        & work["good_quantity"].notna()
        & work["scrap_quantity"].notna()
        & work["real_hours"].apply(lambda value: math.isfinite(value) and value > 0)
        & work["good_quantity"].apply(lambda value: math.isfinite(value) and value >= 0)
        & work["scrap_quantity"].apply(lambda value: math.isfinite(value) and value >= 0)
    )
    work["display_key"] = work.get(
        "display", pd.Series(pd.NA, index=work.index)
    ).apply(_display_key)
    work["maquinario_key"] = work.get(
        "maquinario", pd.Series(pd.NA, index=work.index)
    ).apply(_process_key)
    work["processo_key"] = work.get(
        "processo", pd.Series(pd.NA, index=work.index)
    ).apply(_process_key)

    if standards is None:
        standards = build_effective_standard_catalog(entries, entries)
    catalog = _prepare_catalog(standards)
    exact_index = _index_catalog(
        catalog, ["display_key", "maquinario_key", "processo_key"]
    )
    display_process_index = _index_catalog(
        catalog, ["display_key", "processo_key"]
    )
    display_machine_index = _index_catalog(
        catalog, ["display_key", "maquinario_key"]
    )

    resolved_rates = []
    reasons = []
    for row in work.itertuples(index=False):
        if not row.valid_record:
            resolved_rates.append(None)
            reasons.append("Apontamento invalido")
            continue
        if not row.display_key:
            resolved_rates.append(None)
            reasons.append("Display nao informado")
            continue
        if row.maquinario_key and row.processo_key:
            candidates = exact_index.get(
                (row.display_key, row.maquinario_key, row.processo_key)
            )
        elif row.processo_key:
            candidates = display_process_index.get((row.display_key, row.processo_key))
        elif row.maquinario_key:
            candidates = display_machine_index.get((row.display_key, row.maquinario_key))
        else:
            candidates = None
        rate, reason = _resolve_candidates(candidates)
        resolved_rates.append(rate)
        reasons.append(reason)

    work["standard_rate_pph"] = resolved_rates
    work["standard_reason"] = reasons
    work["covered"] = work["valid_record"] & work["standard_rate_pph"].notna()
    work["standard_hours"] = 0.0
    covered = work["covered"]
    if covered.any():
        work.loc[covered, "standard_hours"] = (
            work.loc[covered, "processed_quantity"]
            / work.loc[covered, "standard_rate_pph"]
        )

    valid = work["valid_record"]
    total_valid_hours = float(work.loc[valid, "real_hours"].sum())
    covered_real_hours = float(work.loc[covered, "real_hours"].sum())
    standard_hours = float(work.loc[covered, "standard_hours"].sum())
    total_valid_records = int(valid.sum())
    covered_records = int(covered.sum())
    coverage_hours = (
        covered_real_hours / total_valid_hours if total_valid_hours > 0 else None
    )
    coverage_records = (
        covered_records / total_valid_records if total_valid_records > 0 else None
    )

    raw_efficiency = None
    if (
        coverage_hours is not None
        and coverage_hours >= threshold
        and covered_real_hours > 0
    ):
        raw_efficiency = standard_hours / covered_real_hours
        if not math.isfinite(raw_efficiency):
            raw_efficiency = None
    oee_efficiency = (
        max(0.0, min(raw_efficiency, 1.0))
        if raw_efficiency is not None
        else None
    )
    has_registered_standards = bool(
        not catalog.empty and catalog["has_standard_value"].any()
    )
    duplicate_count = int(
        catalog["standard_duplicate"].sum()
    ) if not catalog.empty else 0

    return OperationalEfficiencyResult(
        raw_efficiency=raw_efficiency,
        oee_efficiency=oee_efficiency,
        standard_hours=standard_hours,
        covered_real_hours=covered_real_hours,
        total_valid_hours=total_valid_hours,
        coverage_hours=coverage_hours,
        covered_records=covered_records,
        total_valid_records=total_valid_records,
        coverage_records=coverage_records,
        invalid_records=int((~valid).sum()),
        has_registered_standards=has_registered_standards,
        duplicate_standard_count=duplicate_count,
        coverage_threshold=threshold,
        missing_report=_build_missing_standard_report(work),
    )
