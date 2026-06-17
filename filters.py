from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import streamlit as st


@dataclass(slots=True)
class FilterContext:
    date_range: tuple[date | None, date | None] | None = None
    display_selected: list[str] = field(default_factory=list)
    numero_display_selected: list[str] = field(default_factory=list)
    maquinario_selected: list[str] = field(default_factory=list)
    processo_selected: list[str] = field(default_factory=list)
    operador_selected: list[str] = field(default_factory=list)
    filtered_no_operator: pd.DataFrame = field(default_factory=pd.DataFrame)

    def with_overrides(
        self,
        *,
        display_selected: list[str] | None = None,
        numero_display_selected: list[str] | None = None,
        maquinario_selected: list[str] | None = None,
        processo_selected: list[str] | None = None,
        operador_selected: list[str] | None = None,
        filtered_no_operator: pd.DataFrame | None = None,
    ) -> FilterContext:
        return FilterContext(
            date_range=self.date_range,
            display_selected=list(
                self.display_selected
                if display_selected is None
                else display_selected
            ),
            numero_display_selected=list(
                self.numero_display_selected
                if numero_display_selected is None
                else numero_display_selected
            ),
            maquinario_selected=list(
                self.maquinario_selected
                if maquinario_selected is None
                else maquinario_selected
            ),
            processo_selected=list(
                self.processo_selected
                if processo_selected is None
                else processo_selected
            ),
            operador_selected=list(
                self.operador_selected
                if operador_selected is None
                else operador_selected
            ),
            filtered_no_operator=(
                self.filtered_no_operator
                if filtered_no_operator is None
                else filtered_no_operator
            ),
        )


def _normalize_text(series: pd.Series, *, lower: bool = False) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    if lower:
        cleaned = cleaned.str.lower()

    # Drop placeholders / blanks that become options like "none" or "nan".
    lowered = cleaned.str.lower()
    invalid = lowered.isin(["", "none", "nan", "<na>"])
    return cleaned.mask(invalid, pd.NA)


def _normalize_integer_text(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.str.replace(",", ".", regex=False)
    cleaned = cleaned.str.split(".", n=1).str[0]
    return _normalize_text(cleaned)


def _sorted_unique(series: pd.Series) -> list[str]:
    return sorted(series.dropna().unique())


def _sanitize_multiselect_state(key: str, options: list[str]) -> None:
    if key not in st.session_state:
        return
    current_values = st.session_state.get(key, [])
    if not isinstance(current_values, list):
        st.session_state[key] = []
        return
    option_set = set(options)
    st.session_state[key] = [value for value in current_values if value in option_set]


def _filter_by_selection(
    frame: pd.DataFrame, column: str, selected_values: list[str]
) -> pd.DataFrame:
    if not selected_values or column not in frame.columns:
        return frame
    return frame[frame[column].isin(selected_values)]


def apply_filters(df: pd.DataFrame) -> tuple[pd.DataFrame, FilterContext]:
    if df.empty:
        return df, FilterContext(filtered_no_operator=df.copy())

    df_filter = df.copy()
    if "display" in df_filter.columns:
        df_filter["display_clean"] = (
            _normalize_text(
                df_filter["display"]
                .astype("string")
                .str.replace(
                    r"(?i)\s*-\s*lote.*", "", regex=True
                )
            )
        )
    if "maquinario" in df_filter.columns:
        df_filter["maquinario_clean"] = (
            _normalize_text(df_filter["maquinario"], lower=True)
        )
    if "codigo_lote" in df_filter.columns:
        df_filter["codigo_lote_clean"] = (
            _normalize_text(df_filter["codigo_lote"])
        )
    if "numero_display" in df_filter.columns:
        df_filter["numero_display_clean"] = (
            _normalize_integer_text(df_filter["numero_display"])
        )
    if "processo" in df_filter.columns:
        df_filter["processo_clean"] = _normalize_text(df_filter["processo"])
    if "operador" in df_filter.columns:
        df_filter["operador_clean"] = _normalize_text(df_filter["operador"])

    dates = (
        df_filter["data_producao"].dropna()
        if "data_producao" in df_filter.columns
        else None
    )
    min_date = dates.min() if dates is not None and not dates.empty else None
    max_date = dates.max() if dates is not None and not dates.empty else None

    with st.sidebar:
        st.header("Filtros")
        date_range: tuple[date | None, date | None] | None = None
        if min_date is not None and max_date is not None:
            date_range = st.date_input(
                "Periodo",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )

        displays = (
            _sorted_unique(df_filter["display_clean"])
            if "display_clean" in df_filter.columns
            else []
        )
        _sanitize_multiselect_state("filter_display", displays)
        display_selected = st.multiselect(
            "Display/Peca produzida", displays, key="filter_display"
        )

        lote_col = None
        if "numero_display_clean" in df_filter.columns:
            lote_col = "numero_display_clean"
        elif "codigo_lote_clean" in df_filter.columns:
            lote_col = "codigo_lote_clean"

        lotes: list[str] = []
        if lote_col and display_selected:
            available_lotes = df_filter
            available_lotes = _filter_by_selection(
                available_lotes, "display_clean", display_selected
            )
            lotes = _sorted_unique(available_lotes[lote_col])

        _sanitize_multiselect_state("filter_numero_display", lotes)
        lote_label = (
            "Numero display"
            if lote_col == "numero_display_clean"
            else "Codigo do lote"
        )
        lote_selected = st.multiselect(
            lote_label, lotes, key="filter_numero_display"
        )

        available_machines = df_filter.copy()
        available_machines = _filter_by_selection(
            available_machines, "display_clean", display_selected
        )
        if lote_col:
            available_machines = _filter_by_selection(
                available_machines, lote_col, lote_selected
            )

        machines = (
            _sorted_unique(available_machines["maquinario_clean"])
            if "maquinario_clean" in available_machines.columns
            else []
        )
        _sanitize_multiselect_state("filter_maquinario", machines)
        machine_selected = st.multiselect(
            "Maquinario", machines, key="filter_maquinario"
        )

        available_processes = df_filter.copy()
        available_processes = _filter_by_selection(
            available_processes, "display_clean", display_selected
        )
        if lote_col:
            available_processes = _filter_by_selection(
                available_processes, lote_col, lote_selected
            )
        available_processes = _filter_by_selection(
            available_processes, "maquinario_clean", machine_selected
        )

        processes = (
            _sorted_unique(available_processes["processo_clean"])
            if "processo_clean" in available_processes.columns
            else []
        )
        _sanitize_multiselect_state("filter_processo", processes)
        process_selected = st.multiselect(
            "Processo", processes, key="filter_processo"
        )

        available_operators = available_processes
        available_operators = _filter_by_selection(
            available_operators, "processo_clean", process_selected
        )
        operators = (
            _sorted_unique(available_operators["operador_clean"])
            if "operador_clean" in available_operators.columns
            else []
        )
        _sanitize_multiselect_state("filter_operador", operators)
        operator_selected = st.multiselect(
            "Operador", operators, key="filter_operador"
        )

    filtered = df_filter.copy()
    if date_range and len(date_range) == 2:
        start, end = date_range
        if start and end:
            if "data_producao" in filtered.columns:
                filtered = filtered[filtered["data_producao"].notna()]
                filtered = filtered[
                    (filtered["data_producao"] >= start)
                    & (filtered["data_producao"] <= end)
                ]

    filtered = _filter_by_selection(filtered, "maquinario_clean", machine_selected)
    filtered = _filter_by_selection(filtered, "processo_clean", process_selected)
    filtered = _filter_by_selection(filtered, "display_clean", display_selected)
    if lote_col:
        filtered = _filter_by_selection(filtered, lote_col, lote_selected)

    filtered_no_operator = filtered.copy()

    filtered = _filter_by_selection(filtered, "operador_clean", operator_selected)

    clean_cols = [
        "maquinario_clean",
        "display_clean",
        "codigo_lote_clean",
        "numero_display_clean",
        "processo_clean",
        "operador_clean",
    ]
    filtered_no_operator = filtered_no_operator.drop(columns=clean_cols, errors="ignore")
    filtered = filtered.drop(columns=clean_cols, errors="ignore")

    context = FilterContext(
        date_range=date_range,
        display_selected=list(display_selected),
        numero_display_selected=list(lote_selected),
        maquinario_selected=list(machine_selected),
        processo_selected=list(process_selected),
        operador_selected=list(operator_selected),
        filtered_no_operator=filtered_no_operator,
    )
    return filtered, context
