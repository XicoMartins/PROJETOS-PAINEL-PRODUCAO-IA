from __future__ import annotations

import ast
import os
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from constants import DATA_DIR, FORMS_DIR, SQLITE_DB_PATH

try:
    import psycopg
except ImportError:  # pragma: no cover - Streamlit Cloud instala via requirements
    psycopg = None


ENV_DATABASE_KEYS = (
    "DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRESQL_URL",
    "SUPABASE_DB_URL",
)


def _normalize_col(col: str) -> str:
    col = col.replace("\r", " ").replace("\n", " ")
    col = unicodedata.normalize("NFKD", col)
    col = "".join(ch for ch in col if not unicodedata.combining(ch))
    col = col.strip().lower()
    col = re.sub(r"[^a-z0-9 ]+", " ", col)
    col = re.sub(r"\s+", " ", col).strip().replace(" ", "_")
    return col


def _parse_operators(val: str) -> list[str]:
    if pd.isna(val):
        return []
    text = str(val).strip()
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, Iterable):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    if ";" in text:
        return [part.strip() for part in text.split(";") if part.strip()]
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text] if text else []


def _get_secret_value(key: str) -> str | None:
    try:
        value = st.secrets.get(key)
    except Exception:
        return None
    return str(value).strip() if value else None


def get_database_url() -> str | None:
    for key in ENV_DATABASE_KEYS:
        value = os.getenv(key) or _get_secret_value(key)
        if value:
            return value
    return None


def _parse_time(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    return pd.to_datetime(s, format="%H:%M", errors="coerce")


def _normalize_integer_text(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.str.replace(",", ".", regex=False)
    cleaned = cleaned.str.split(".", n=1).str[0]
    lowered = cleaned.str.lower()
    invalid = lowered.isin(["", "none", "nan", "<na>"])
    return cleaned.mask(invalid, pd.NA)


def _normalize_filter_text(series: pd.Series, *, lower: bool = False) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    if lower:
        cleaned = cleaned.str.lower()
    invalid = cleaned.str.lower().isin(["", "none", "nan", "<na>"])
    return cleaned.mask(invalid, pd.NA)


def _add_filter_columns(frame: pd.DataFrame) -> None:
    """Prepara uma vez as colunas usadas pelos filtros da interface."""
    if "display" in frame.columns:
        display = frame["display"].astype("string").str.replace(
            r"(?i)\s*-\s*lote.*", "", regex=True
        )
        frame["display_clean"] = _normalize_filter_text(display)
    if "maquinario" in frame.columns:
        frame["maquinario_clean"] = _normalize_filter_text(
            frame["maquinario"], lower=True
        )
    if "codigo_lote" in frame.columns:
        frame["codigo_lote_clean"] = _normalize_filter_text(frame["codigo_lote"])
    if "numero_display" in frame.columns:
        frame["numero_display_clean"] = _normalize_integer_text(
            frame["numero_display"]
        )
    if "processo" in frame.columns:
        frame["processo_clean"] = _normalize_filter_text(frame["processo"])
    if "operador" in frame.columns:
        frame["operador_clean"] = _normalize_filter_text(frame["operador"])


def _pick_forms_csv(forms_dir: Path) -> Path | None:
    if not forms_dir.exists():
        return None
    csv_files = list(forms_dir.glob("*.csv"))
    if not csv_files:
        return None
    try:
        return max(csv_files, key=lambda path: path.stat().st_mtime)
    except FileNotFoundError:
        return None


def _empty_result(message: str | None = None) -> tuple[pd.DataFrame, Path | None, dict]:
    quality = {"warnings": [], "fixes": [], "nulls": {}}
    if message:
        quality["warnings"].append(message)
    return pd.DataFrame(), None, quality


def _read_csv_source(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep=",",
        encoding="utf-8",
        engine="python",
        on_bad_lines="skip",
    )


def _read_sqlite_source(path: Path) -> pd.DataFrame:
    query = """
        SELECT
            id,
            timestamp,
            cliente,
            display,
            numero_display,
            maquinario,
            processo,
            data_producao,
            operadores,
            hora_inicio,
            hora_fim,
            quantidade,
            pecas_mortas,
            quantidade_total
        FROM core_productionentry
    """
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(query, conn)


def _read_postgres_source() -> pd.DataFrame:
    if psycopg is None:
        raise RuntimeError("Dependencia psycopg nao instalada.")

    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL nao configurada nos Secrets.")
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    query = """
        SELECT
            id,
            timestamp,
            cliente,
            display,
            numero_display,
            maquinario,
            processo,
            data_producao,
            operadores,
            hora_inicio,
            hora_fim,
            quantidade,
            pecas_mortas,
            quantidade_total
        FROM production_entries
        ORDER BY timestamp DESC, id DESC
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [desc.name for desc in cursor.description]
    return pd.DataFrame(rows, columns=columns)


def _read_painting_postgres_source() -> pd.DataFrame:
    """Le os lancamentos de pintura usando a mesma conexao do painel."""
    if psycopg is None:
        raise RuntimeError("Dependencia psycopg nao instalada.")

    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL nao configurada nos Secrets.")
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    query = """
        SELECT
            id,
            timestamp,
            cliente,
            display,
            numero_display,
            codigo_pintura,
            maquinario,
            processo,
            data_producao,
            hora_lancamento,
            quantidade,
            quantidade_total,
            created_at
        FROM painting_entries
        ORDER BY timestamp DESC NULLS LAST, id DESC
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [desc.name for desc in cursor.description]
    return pd.DataFrame(rows, columns=columns)


PAINTING_COLUMNS = [
    "id", "timestamp", "cliente", "display", "numero_display",
    "codigo_pintura", "maquinario", "processo", "data_producao",
    "hora_lancamento", "quantidade", "quantidade_total", "created_at",
]


def _normalize_painting_frame(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normaliza pintura sem aplicar regras exclusivas da producao."""
    quality: dict[str, list | dict] = {"warnings": [], "fixes": [], "nulls": {}}
    if df_raw.empty:
        return pd.DataFrame(columns=PAINTING_COLUMNS), quality

    frame = df_raw.copy()
    frame.columns = [_normalize_col(col) for col in frame.columns]
    for column in PAINTING_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[PAINTING_COLUMNS]

    raw_dates = frame["data_producao"].astype("string").str.strip()
    parsed_dates = pd.to_datetime(raw_dates, format="%d/%m/%y", errors="coerce")
    missing_dates = parsed_dates.isna()
    if missing_dates.any():
        parsed_dates.loc[missing_dates] = pd.to_datetime(
            raw_dates.loc[missing_dates], format="%d/%m/%Y", errors="coerce"
        )
    still_missing = parsed_dates.isna()
    if still_missing.any():
        parsed_dates.loc[still_missing] = pd.to_datetime(
            raw_dates.loc[still_missing], errors="coerce"
        )
    frame["data_producao"] = parsed_dates.dt.date.astype("object")
    frame.loc[parsed_dates.isna(), "data_producao"] = None

    for column in ("timestamp", "created_at"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    for column in ("quantidade", "quantidade_total"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).clip(lower=0)

    frame["numero_display"] = _normalize_integer_text(frame["numero_display"])
    for column in (
        "cliente", "display", "numero_display", "codigo_pintura",
        "maquinario", "processo", "hora_lancamento",
    ):
        cleaned = frame[column].astype("string").str.strip()
        invalid = cleaned.str.lower().isin(["", "none", "nan", "<na>"])
        frame[column] = cleaned.mask(invalid, pd.NA)

    quality["nulls"] = {
        column: int(frame[column].isna().sum()) for column in PAINTING_COLUMNS
    }
    return frame, quality


@st.cache_data(show_spinner=False, ttl=60)
def load_painting_data() -> tuple[pd.DataFrame, Path | None, dict]:
    """Carrega painting_entries diretamente do PostgreSQL com cache de 60s."""
    try:
        df_raw = _read_painting_postgres_source()
    except Exception as exc:
        return _empty_result(f"Falha ao ler PostgreSQL: {exc}")
    frame, quality = _normalize_painting_frame(df_raw)
    return frame, Path("painting_entries"), quality


def _normalize_loaded_frame(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if df_raw.empty:
        return df_raw, {"warnings": [], "fixes": [], "nulls": {}}

    df_raw = df_raw.copy()
    df_raw.columns = [_normalize_col(col) for col in df_raw.columns]

    rename = {
        "id": "id",
        "timestamp": "timestamp",
        "cliente": "cliente",
        "display": "display",
        "numero_display": "numero_display",
        "numero_do_display": "numero_display",
        "maquinario": "maquinario",
        "maquina_rio": "maquinario",
        "processo": "processo",
        "codigo_do_lote": "codigo_lote",
        "codigo_lote": "codigo_lote",
        "lote": "codigo_lote",
        "data": "data_producao",
        "data_producao": "data_producao",
        "operadores": "operadores",
        "hora_inicio": "hora_inicio",
        "hora_fim": "hora_conclusao",
        "hora_fim_": "hora_conclusao",
        "quantidade": "quantidade_produzida",
        "quantidade_produzida": "quantidade_produzida",
        "pecas_mortas": "pecas_mortas",
        "quantidade_total": "quantidade_total",
    }
    df_raw = df_raw.rename(columns=rename)

    expected = [
        "id",
        "timestamp",
        "cliente",
        "display",
        "numero_display",
        "maquinario",
        "processo",
        "codigo_lote",
        "data_producao",
        "operadores",
        "hora_inicio",
        "hora_conclusao",
        "quantidade_produzida",
        "pecas_mortas",
        "quantidade_total",
    ]
    df_raw = df_raw[[c for c in expected if c in df_raw.columns]]

    quality: dict[str, list | dict] = {"warnings": [], "fixes": [], "nulls": {}}

    if "data_producao" in df_raw.columns:
        parsed_date = pd.to_datetime(df_raw["data_producao"], format="%d/%m/%y", errors="coerce")
        mask_na = parsed_date.isna()
        if mask_na.any():
            parsed_date.loc[mask_na] = pd.to_datetime(
                df_raw.loc[mask_na, "data_producao"], format="%d/%m/%Y", errors="coerce"
            )
        data_producao = parsed_date.dt.date.astype("object")
        data_producao.loc[parsed_date.isna()] = None
        future_mask = data_producao.apply(
            lambda value: value is not None and value > date.today()
        )
        future_count = future_mask.sum()
        if future_count > 0:
            quality["warnings"].append(
                f"{future_count} datas de producao no futuro foram anuladas."
            )
            data_producao.loc[future_mask] = None
        df_raw["data_producao"] = data_producao

    if "operadores" in df_raw.columns:
        df_raw["operadores_lista"] = df_raw["operadores"].apply(_parse_operators)
        df_raw["operador"] = df_raw["operadores_lista"].apply(
            lambda values: "; ".join(values) if values else ""
        )
        df_raw = df_raw.drop(columns=["operadores"])
        df_raw = df_raw.reset_index(drop=True)

    for col in ["quantidade_produzida", "pecas_mortas"]:
        if col in df_raw.columns:
            df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce").fillna(0)
            negatives = (df_raw[col] < 0).sum()
            if negatives > 0:
                quality["fixes"].append(
                    f"{negatives} valores negativos em '{col}' ajustados para 0."
                )
                df_raw[col] = df_raw[col].clip(lower=0)

    start_time = _parse_time(df_raw["hora_inicio"]) if "hora_inicio" in df_raw.columns else None
    end_time = _parse_time(df_raw["hora_conclusao"]) if "hora_conclusao" in df_raw.columns else None

    if end_time is not None:
        df_raw["hora"] = end_time.dt.hour
    elif start_time is not None:
        df_raw["hora"] = start_time.dt.hour

    if start_time is not None and end_time is not None:
        start_sec = start_time.dt.hour * 3600 + start_time.dt.minute * 60 + start_time.dt.second
        end_sec = end_time.dt.hour * 3600 + end_time.dt.minute * 60 + end_time.dt.second
        duracao_horas = (end_sec - start_sec) / 3600
        df_raw["duracao_horas"] = pd.to_numeric(duracao_horas, errors="coerce")

    if "numero_display" in df_raw.columns:
        df_raw["numero_display"] = _normalize_integer_text(df_raw["numero_display"])

    for text_col in [
        "maquinario",
        "operador",
        "display",
        "processo",
        "cliente",
        "codigo_lote",
        "numero_display",
    ]:
        if text_col in df_raw.columns:
            df_raw[text_col] = df_raw[text_col].astype(str).str.strip()

    key_cols = [
        "data_producao",
        "maquinario",
        "operador",
        "display",
        "processo",
        "quantidade_produzida",
        "pecas_mortas",
    ]
    quality["nulls"] = {
        col: int(df_raw[col].isna().sum()) for col in key_cols if col in df_raw.columns
    }

    _add_filter_columns(df_raw)

    return df_raw, quality


@st.cache_data(show_spinner=False, ttl=60)
def _load_data_cached(
    source: str, path_str: str, mtime: float | None
) -> tuple[pd.DataFrame, Path | None, dict]:
    if source == "forms_postgres":
        try:
            df_raw = _read_postgres_source()
        except Exception as exc:
            return _empty_result(f"Falha ao ler PostgreSQL: {exc}")
        df_raw, quality = _normalize_loaded_frame(df_raw)
        return df_raw, Path("production_entries"), quality

    path = Path(path_str)
    if not path.exists():
        return _empty_result()

    try:
        if source == "sqlite":
            df_raw = _read_sqlite_source(path)
        else:
            df_raw = _read_csv_source(path)
    except (OSError, pd.errors.ParserError, sqlite3.DatabaseError) as exc:
        return _empty_result(f"Falha ao ler a fonte de dados: {exc}")

    df_raw, quality = _normalize_loaded_frame(df_raw)
    return df_raw, path, quality


def load_data(source: str = "base_atual") -> tuple[pd.DataFrame, Path | None, dict]:
    if source == "forms_postgres":
        return _load_data_cached(source, "postgresql", None)
    if source == "forms":
        path = _pick_forms_csv(FORMS_DIR)
    elif source == "sqlite":
        path = SQLITE_DB_PATH
    else:
        path = DATA_DIR / "registros.csv"
    if path is None:
        return _empty_result()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    return _load_data_cached(source, str(path), mtime)
