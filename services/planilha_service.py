from __future__ import annotations

import math
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

from constants import DISPLAY_PLANILHA_MAP
from filters import FilterContext


PLANILHA_FILENAME_PREFIX = "LISTA DE PROCESSO"
STANDARD_RATE_ALIASES = {
    "pecas_por_hora_padrao",
    "peca_por_hora_padrao",
    "pecas_hora_padrao",
}
STANDARD_MINUTES_ALIASES = {
    "tempo_padrao_min_por_peca",
    "tempo_padrao_minuto_por_peca",
    "minutos_padrao_por_peca",
}


def normalize_display_name(text: str) -> str:
    name = unicodedata.normalize("NFKD", str(text))
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    name = name.strip().lower()
    cleaned = []
    last_was_sep = False
    for ch in name:
        if ch.isalnum():
            cleaned.append(ch)
            last_was_sep = False
        else:
            if not last_was_sep:
                cleaned.append("_")
                last_was_sep = True
    return "".join(cleaned).strip("_")


def normalize_planilha_lookup_key(text: str) -> str:
    parts = normalize_display_name(text).split("_")
    normalized_parts = []
    for part in parts:
        if part.isdigit():
            normalized_parts.append(str(int(part)))
        elif part:
            normalized_parts.append(part)
    return "_".join(normalized_parts)


def normalize_process_name(text: str) -> str:
    return normalize_display_name(text)


def _positive_finite_number(value) -> float | None:
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


def resolve_standard_rate(
    pecas_por_hora_padrao=None,
    tempo_padrao_min_por_peca=None,
) -> tuple[float | None, str | None]:
    """Return a valid standard rate in pieces/hour and its source column.

    A positive ``pecas_por_hora_padrao`` has priority. Otherwise a positive
    standard time in minutes/piece is converted with ``60 / minutes``. Invalid,
    zero, negative, infinite and textual values do not produce a standard.
    """
    pieces_per_hour = _positive_finite_number(pecas_por_hora_padrao)
    if pieces_per_hour is not None:
        return pieces_per_hour, "pecas_por_hora_padrao"

    minutes_per_piece = _positive_finite_number(tempo_padrao_min_por_peca)
    if minutes_per_piece is None:
        return None, None
    return 60.0 / minutes_per_piece, "tempo_padrao_min_por_peca"


def _find_column_by_aliases(df: pd.DataFrame, aliases: set[str]):
    normalized_columns = {
        normalize_display_name(column): column for column in df.columns
    }
    for alias in aliases:
        column = normalized_columns.get(alias)
        if column is not None:
            return column
    return None


def build_planilha_file_map(planilhas_dir: Path) -> dict[str, Path]:
    if not planilhas_dir.exists():
        return {}
    return {
        path.name: path
        for path in planilhas_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".xlsx"
    }


def get_display_planilha_filename_map() -> dict[str, str]:
    return {
        normalize_planilha_lookup_key(display): filename
        for display, filename in DISPLAY_PLANILHA_MAP.items()
    }


def get_display_name_from_planilha_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    if stem.upper().startswith(PLANILHA_FILENAME_PREFIX):
        stem = stem[len(PLANILHA_FILENAME_PREFIX) :]
    return stem.strip(" -_")


def build_display_planilha_filename_map(planilhas_dir: Path) -> dict[str, str]:
    file_map = build_planilha_file_map(planilhas_dir)
    filename_map: dict[str, str] = {}
    for filename in sorted(file_map):
        display_name = get_display_name_from_planilha_filename(filename)
        display_key = normalize_planilha_lookup_key(display_name)
        if display_key:
            filename_map.setdefault(display_key, filename)

    filename_map.update(get_display_planilha_filename_map())
    return filename_map


def validate_planilha_configuration(df: pd.DataFrame | None = None) -> list[str]:
    planilhas_dir = Path(__file__).resolve().parent.parent / "planilhas"
    available_files = build_planilha_file_map(planilhas_dir)
    normalized_mapping = build_display_planilha_filename_map(planilhas_dir)
    issues: list[str] = []

    missing_files = sorted(
        {
            filename
            for filename in normalized_mapping.values()
            if filename not in available_files
        }
    )
    for filename in missing_files:
        issues.append(f"Arquivo de planilha configurado nao encontrado: {filename}")

    if df is not None and not df.empty and "display" in df.columns:
        unmapped_displays = sorted(
            {
                str(value).strip()
                for value in df["display"].dropna().unique()
                if normalize_planilha_lookup_key(value)
                and normalize_planilha_lookup_key(value) not in normalized_mapping
            }
        )
        for display in unmapped_displays:
            issues.append(f"Display sem planilha configurada: {display}")

    return issues


@st.cache_data(show_spinner=False)
def load_planilha_processes(path_str: str, mtime: float | None) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, engine="openpyxl")
    except Exception:
        return pd.DataFrame()

    if df.empty or len(df.columns) < 5:
        return pd.DataFrame()

    maquinario_col = _find_column_by_aliases(
        df, {"ferramental", "maquinario", "maquina"}
    ) or df.columns[2]
    process_col = _find_column_by_aliases(df, {"processo"}) or df.columns[3]
    qnt_col = _find_column_by_aliases(
        df, {"qnt", "quantidade_por_produto", "qnt_por_produto"}
    ) or df.columns[4]
    pieces_hour_col = _find_column_by_aliases(df, STANDARD_RATE_ALIASES)
    minutes_piece_col = _find_column_by_aliases(df, STANDARD_MINUTES_ALIASES)

    selected_columns = [maquinario_col, process_col, qnt_col]
    for optional_column in (pieces_hour_col, minutes_piece_col):
        if optional_column is not None and optional_column not in selected_columns:
            selected_columns.append(optional_column)

    plan = df[selected_columns].copy()
    plan["ordem_planilha"] = range(1, len(plan) + 1)
    plan["maquinario_nome"] = plan[maquinario_col].astype("string").str.strip()
    plan["processo_nome"] = plan[process_col].astype("string").str.strip()
    invalid_machine = plan["maquinario_nome"].str.lower().isin(
        ["", "none", "nan", "<na>"]
    )
    invalid_process = plan["processo_nome"].str.lower().isin(
        ["", "none", "nan", "<na>"]
    )
    plan.loc[invalid_machine, "maquinario_nome"] = pd.NA
    plan.loc[invalid_process, "processo_nome"] = pd.NA
    plan["maquinario_key"] = plan[maquinario_col].apply(normalize_process_name)
    plan["processo_key"] = plan[process_col].apply(normalize_process_name)
    plan["qnt_por_produto"] = pd.to_numeric(plan[qnt_col], errors="coerce")
    plan = plan.dropna(
        subset=["maquinario_nome", "processo_nome", "qnt_por_produto"]
    )
    if plan.empty:
        return pd.DataFrame()

    pieces_hour_values = (
        plan[pieces_hour_col]
        if pieces_hour_col is not None
        else pd.Series(pd.NA, index=plan.index, dtype="object")
    )
    minutes_piece_values = (
        plan[minutes_piece_col]
        if minutes_piece_col is not None
        else pd.Series(pd.NA, index=plan.index, dtype="object")
    )
    resolved = [
        resolve_standard_rate(pieces_hour, minutes_piece)
        for pieces_hour, minutes_piece in zip(
            pieces_hour_values, minutes_piece_values
        )
    ]
    plan["standard_rate_pph"] = [item[0] for item in resolved]
    plan["standard_source"] = [item[1] for item in resolved]

    name_map = (
        plan[["processo_key", "processo_nome"]]
        .dropna(subset=["processo_nome"])
        .drop_duplicates(subset=["processo_key"], keep="first")
        .set_index("processo_key")["processo_nome"]
    )
    machine_name_map = (
        plan[["maquinario_key", "maquinario_nome"]]
        .dropna(subset=["maquinario_nome"])
        .drop_duplicates(subset=["maquinario_key"], keep="first")
        .set_index("maquinario_key")["maquinario_nome"]
    )

    rows = []
    for (machine_key, process_key), group in plan.groupby(
        ["maquinario_key", "processo_key"], dropna=False
    ):
        valid_standards = group.dropna(subset=["standard_rate_pph"])
        duplicate_standard = len(valid_standards) > 1
        standard_rate = (
            float(valid_standards.iloc[0]["standard_rate_pph"])
            if len(valid_standards) == 1
            else None
        )
        standard_source = (
            str(valid_standards.iloc[0]["standard_source"])
            if len(valid_standards) == 1
            else None
        )
        rows.append(
            {
                "maquinario_key": machine_key,
                "processo_key": process_key,
                "qnt_por_produto": group["qnt_por_produto"].sum(),
                "processo_nome": name_map.get(process_key),
                "maquinario_nome": machine_name_map.get(machine_key),
                "standard_rate_pph": standard_rate,
                "standard_source": standard_source,
                "standard_duplicate": duplicate_standard,
                "has_standard_value": not valid_standards.empty,
                "ordem_planilha": int(group["ordem_planilha"].min()),
            }
        )
    return pd.DataFrame(rows).sort_values("ordem_planilha").reset_index(drop=True)


def find_planilha_for_display(
    display_selected: list[str],
) -> tuple[Path | None, str | None]:
    planilhas_dir = Path(__file__).resolve().parent.parent / "planilhas"
    file_map = build_planilha_file_map(planilhas_dir)
    if not display_selected or not file_map:
        return None, None

    display_key = normalize_planilha_lookup_key(display_selected[0])
    filename_map = build_display_planilha_filename_map(planilhas_dir)
    target_filename = filename_map.get(display_key)
    if target_filename is None:
        return None, None
    planilha_path = file_map.get(target_filename)
    if planilha_path is not None:
        return planilha_path, planilha_path.name
    return None, None


def extract_lote_from_numero_display(value: str | int | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "<na>"}:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return digits[-4:] if len(digits) >= 4 else digits


def get_lote_multiplier(df: pd.DataFrame) -> int:
    if "numero_display" not in df:
        return 0
    lotes = df["numero_display"].apply(extract_lote_from_numero_display).dropna()
    lote_multiplier = 0
    for lote in lotes.unique():
        try:
            lote_multiplier += int(lote)
        except ValueError:
            continue
    return lote_multiplier


def round_piece_total(value: float | int | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    if numeric < 0:
        return 0.0
    return float(math.floor(numeric + 0.5))


def build_expected_by_process(
    df: pd.DataFrame,
    filter_context: FilterContext,
    *,
    compute_prod_rate,
    display_selected_override: list[str] | None = None,
) -> tuple[pd.DataFrame, str | None, str | None]:
    del compute_prod_rate
    if df.empty or "processo" not in df:
        return pd.DataFrame(), None, None

    display_selected = (
        display_selected_override
        if display_selected_override is not None
        else filter_context.display_selected
    )
    planilha_path, planilha_name = find_planilha_for_display(display_selected)
    if planilha_path is None:
        return pd.DataFrame(), "Planilha de processos nao encontrada para o display.", None

    try:
        mtime = planilha_path.stat().st_mtime
    except FileNotFoundError:
        mtime = None

    planilha_df = load_planilha_processes(str(planilha_path), mtime)
    if planilha_df.empty:
        return pd.DataFrame(), "Planilha sem processos validos.", planilha_name

    lote_multiplier = get_lote_multiplier(df)
    if lote_multiplier <= 0:
        return pd.DataFrame(), "Lote (numero_display) nao informado.", planilha_name

    maquinarios = []
    if "maquinario" in df:
        maquinarios = [
            normalize_process_name(val)
            for val in df["maquinario"].dropna().unique()
            if normalize_process_name(val)
        ]
    if not maquinarios:
        maquinarios = list(planilha_df["maquinario_key"].unique())

    rows = []
    for processo in sorted(df["processo"].dropna().unique()):
        proc_key = normalize_process_name(processo)
        if not proc_key:
            continue
        filtered = planilha_df[
            (planilha_df["processo_key"] == proc_key)
            & (planilha_df["maquinario_key"].isin(maquinarios))
        ]
        qnt_por_produto = filtered["qnt_por_produto"].sum() if not filtered.empty else None
        total_esperado = (
            round_piece_total(qnt_por_produto * lote_multiplier)
            if qnt_por_produto is not None
            else None
        )
        rows.append(
            {
                "processo": processo,
                "qnt_por_produto": qnt_por_produto,
                "total_esperado": total_esperado,
            }
        )
    expected_df = pd.DataFrame(rows)
    return expected_df, None, planilha_name


def build_remaining_by_process(
    df: pd.DataFrame,
    filter_context: FilterContext,
    *,
    compute_prod_rate,
) -> tuple[pd.DataFrame, str | None, str | None]:
    if df.empty:
        return pd.DataFrame(), "Sem dados apos os filtros.", None
    required_cols = {"processo", "quantidade_produzida", "duracao_horas"}
    if not required_cols.issubset(df.columns):
        return pd.DataFrame(), "Colunas insuficientes para calcular faltante por processo.", None

    display_selected = filter_context.display_selected
    maquinario_selected = filter_context.maquinario_selected
    processo_selected = filter_context.processo_selected
    comparing_many_processes = len(processo_selected) >= 2

    if processo_selected and not comparing_many_processes:
        return pd.DataFrame(), None, None
    if not maquinario_selected:
        return pd.DataFrame(), None, None

    planilha_path, planilha_name = find_planilha_for_display(display_selected)
    if planilha_path is None:
        return (
            pd.DataFrame(),
            "Planilha de processos nao encontrada para o display selecionado.",
            None,
        )

    try:
        mtime = planilha_path.stat().st_mtime
    except FileNotFoundError:
        mtime = None

    planilha_df = load_planilha_processes(str(planilha_path), mtime)
    if planilha_df.empty:
        return pd.DataFrame(), "Planilha sem processos validos.", planilha_name

    lote_multiplier = get_lote_multiplier(df)
    if lote_multiplier <= 0:
        return pd.DataFrame(), "Lote (numero_display) nao informado.", planilha_name

    machine_keys = [
        normalize_process_name(machine)
        for machine in maquinario_selected
        if normalize_process_name(machine)
    ]
    if machine_keys:
        planilha_df = planilha_df[planilha_df["maquinario_key"].isin(machine_keys)]
    if planilha_df.empty:
        return (
            pd.DataFrame(),
            "Sem processos na planilha para o maquinario selecionado.",
            planilha_name,
        )

    produced = df.copy()
    produced["processo"] = produced["processo"].astype("string").str.strip()
    invalid_process = produced["processo"].str.lower().isin(["", "none", "nan", "<na>"])
    produced.loc[invalid_process, "processo"] = pd.NA
    produced["processo_key"] = produced["processo"].apply(normalize_process_name)
    produced = produced.dropna(subset=["processo"]).copy()
    non_empty_key = produced["processo_key"].astype("string").str.strip().ne("")
    produced = produced[non_empty_key.fillna(False)].copy()
    produced["produzido"] = pd.to_numeric(
        produced["quantidade_produzida"], errors="coerce"
    ).fillna(0)
    produced["duracao_horas_num"] = pd.to_numeric(
        produced["duracao_horas"], errors="coerce"
    )

    produced_by_process = (
        produced.groupby("processo_key", as_index=False)["produzido"].sum()
    )

    rate_base = produced[produced["duracao_horas_num"] > 0].copy()
    if not rate_base.empty:
        rate_by_process = (
            rate_base.groupby("processo_key", as_index=False)
            .agg({"produzido": "sum", "duracao_horas_num": "sum"})
            .reset_index(drop=True)
        )
        rate_by_process["media_prod_hora"] = (
            rate_by_process["produzido"] / rate_by_process["duracao_horas_num"]
        )
        rate_by_process = rate_by_process[["processo_key", "media_prod_hora"]]
    else:
        rate_by_process = pd.DataFrame(columns=["processo_key", "media_prod_hora"])

    process_ref = (
        produced[["processo", "processo_key"]]
        .drop_duplicates()
        .sort_values("processo")
        .drop_duplicates(subset=["processo_key"], keep="first")
    )

    expected = (
        planilha_df.groupby("processo_key", as_index=False)["qnt_por_produto"]
        .sum()
        .reset_index(drop=True)
    )
    expected["total_esperado"] = (
        expected["qnt_por_produto"] * lote_multiplier
    ).apply(round_piece_total)

    result = process_ref.merge(expected, on="processo_key", how="left")
    result = result.merge(produced_by_process, on="processo_key", how="left")
    result = result.merge(rate_by_process, on="processo_key", how="left")
    result["produzido"] = pd.to_numeric(result["produzido"], errors="coerce").fillna(0)

    global_rate = compute_prod_rate(df)
    result["media_prod_hora"] = pd.to_numeric(
        result["media_prod_hora"], errors="coerce"
    )
    if global_rate is not None and global_rate > 0:
        result["media_prod_hora"] = result["media_prod_hora"].fillna(global_rate)

    result["pecas_faltantes"] = (
        pd.to_numeric(result["total_esperado"], errors="coerce").fillna(0)
        - result["produzido"]
    ).clip(lower=0)
    result["horas_faltantes"] = pd.NA
    valid_rate = result["media_prod_hora"] > 0
    result.loc[valid_rate, "horas_faltantes"] = (
        result.loc[valid_rate, "pecas_faltantes"] / result.loc[valid_rate, "media_prod_hora"]
    )

    result = result.sort_values("processo")
    return result, None, planilha_name
