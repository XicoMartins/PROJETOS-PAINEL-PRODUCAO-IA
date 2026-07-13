from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st


FILTER_COLUMNS = [
    ("cliente", "Cliente"),
    ("display", "Display"),
    ("numero_display", "Código do display"),
    ("codigo_pintura", "Código pintura"),
    ("maquinario", "Ferramental"),
    ("processo", "Processo"),
]


def _valid_options(series: pd.Series) -> list[str]:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.mask(cleaned.str.lower().isin(["", "none", "nan", "<na>"]))
    return sorted(cleaned.dropna().unique().tolist(), key=str.casefold)


def filter_painting_frame(
    frame: pd.DataFrame,
    date_range: tuple[date | None, date | None] | None = None,
    selections: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    """Aplica filtros da pintura; mantida pura para teste e reutilizacao."""
    filtered = frame.copy()
    selections = selections or {}
    if date_range and len(date_range) == 2 and "data_producao" in filtered.columns:
        start, end = date_range
        if start and end:
            dates = pd.to_datetime(filtered["data_producao"], errors="coerce").dt.date
            filtered = filtered[dates.notna() & dates.between(start, end)]

    for column, _label in FILTER_COLUMNS:
        selected = selections.get(column, [])
        if selected and column in filtered.columns:
            values = filtered[column].astype("string").str.strip()
            filtered = filtered[values.isin(selected)]
    return filtered


def _sanitize_state(key: str, options: list[str]) -> None:
    current = st.session_state.get(key)
    if not isinstance(current, list):
        if key in st.session_state:
            st.session_state[key] = []
        return
    allowed = set(options)
    st.session_state[key] = [value for value in current if value in allowed]


def apply_painting_filters(frame: pd.DataFrame) -> pd.DataFrame:
    """Renderiza os filtros laterais no mesmo padrao de navegacao do painel."""
    selections: dict[str, list[str]] = {}
    date_range: tuple[date | None, date | None] | None = None

    date_source = frame["data_producao"] if "data_producao" in frame.columns else pd.Series(dtype="object")
    dates = pd.to_datetime(date_source, errors="coerce").dropna()
    with st.sidebar:
        st.header("Filtros")
        if not dates.empty:
            min_date = dates.min().date()
            max_date = dates.max().date()
            date_range = st.date_input(
                "Período",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="painting_filter_period",
            )

        available = frame.copy()
        for column, label in FILTER_COLUMNS:
            options = _valid_options(available[column]) if column in available.columns else []
            key = f"painting_filter_{column}"
            _sanitize_state(key, options)
            selected = st.multiselect(label, options, key=key)
            selections[column] = selected
            if selected:
                available = filter_painting_frame(available, selections={column: selected})

    return filter_painting_frame(frame, date_range=date_range, selections=selections)
