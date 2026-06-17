from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None


DEFAULT_SQLITE_PATH = (
    Path(__file__).resolve().parents[2] / "PROJETOS -BACKEND" / "db.sqlite3"
)
TABLE_NAME = "production_entries"


def normalize_postgres_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://") :]

    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def read_secret_database_url() -> str | None:
    secrets_path = Path(".streamlit") / "secrets.toml"
    if not secrets_path.exists() or tomllib is None:
        return None

    with secrets_path.open("rb") as file:
        secrets = tomllib.load(file)

    value = secrets.get("DATABASE_URL")
    return str(value).strip() if value else None


def get_database_url(cli_value: str | None) -> str:
    database_url = (
        cli_value
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
        or os.getenv("SUPABASE_DB_URL")
        or read_secret_database_url()
    )
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL nao encontrada. Informe com --database-url ou configure "
            "a variavel de ambiente DATABASE_URL."
        )
    return normalize_postgres_url(database_url)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_source_hash(row: dict[str, Any]) -> str:
    ordered_keys = [
        "schema_version",
        "timestamp",
        "cliente",
        "display",
        "numero_display",
        "maquinario",
        "processo",
        "data_producao",
        "operadores",
        "numero_operadores",
        "hora_inicio",
        "hora_fim",
        "quantidade",
        "pecas_mortas",
        "quantidade_total",
    ]
    raw = "||".join(normalize_text(row.get(key)) for key in ordered_keys)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_legacy_entries(sqlite_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite legado nao encontrado: {sqlite_path}")

    query = """
        SELECT
            source_hash,
            schema_version,
            timestamp,
            cliente,
            display,
            numero_display,
            maquinario,
            processo,
            data_producao,
            operadores,
            numero_operadores,
            hora_inicio,
            hora_fim,
            quantidade,
            pecas_mortas,
            quantidade_total,
            import_key
        FROM core_productionentry
        ORDER BY id
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query).fetchall()]

    normalized_rows = []
    for row in rows:
        normalized = {
            "schema_version": normalize_text(row.get("schema_version")) or "legacy",
            "timestamp": normalize_text(row.get("timestamp")) or None,
            "cliente": normalize_text(row.get("cliente")),
            "display": normalize_text(row.get("display")),
            "numero_display": normalize_text(row.get("numero_display")),
            "maquinario": normalize_text(row.get("maquinario")),
            "processo": normalize_text(row.get("processo")),
            "data_producao": normalize_text(row.get("data_producao")),
            "operadores": normalize_text(row.get("operadores")),
            "numero_operadores": normalize_int(row.get("numero_operadores")),
            "hora_inicio": normalize_text(row.get("hora_inicio")),
            "hora_fim": normalize_text(row.get("hora_fim")),
            "quantidade": normalize_int(row.get("quantidade")),
            "pecas_mortas": normalize_int(row.get("pecas_mortas")),
            "quantidade_total": normalize_int(row.get("quantidade_total")),
            "source_hash": normalize_text(row.get("source_hash")),
            "import_key": normalize_text(row.get("import_key")) or None,
        }
        if not normalized["source_hash"]:
            normalized["source_hash"] = build_source_hash(normalized)
        normalized_rows.append(normalized)

    return normalized_rows


def ensure_postgres_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id BIGSERIAL PRIMARY KEY,
                import_key TEXT UNIQUE,
                source_hash TEXT UNIQUE,
                schema_version TEXT,
                timestamp TIMESTAMPTZ,
                cliente TEXT,
                display TEXT,
                numero_display TEXT,
                maquinario TEXT,
                processo TEXT,
                data_producao TEXT,
                operadores TEXT,
                numero_operadores INTEGER,
                hora_inicio TEXT,
                hora_fim TEXT,
                quantidade INTEGER DEFAULT 0,
                pecas_mortas INTEGER DEFAULT 0,
                quantidade_total INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON {TABLE_NAME}(timestamp DESC)
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_source_hash
            ON {TABLE_NAME}(source_hash)
            """
        )
    conn.commit()


def insert_entries(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    columns = [
        "schema_version",
        "timestamp",
        "cliente",
        "display",
        "numero_display",
        "maquinario",
        "processo",
        "data_producao",
        "operadores",
        "numero_operadores",
        "hora_inicio",
        "hora_fim",
        "quantidade",
        "pecas_mortas",
        "quantidade_total",
        "source_hash",
        "import_key",
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    column_list = ", ".join(columns)
    values = [tuple(row.get(column) for column in columns) for row in rows]

    with conn.cursor() as cursor:
        cursor.executemany(
            f"""
            INSERT INTO {TABLE_NAME} ({column_list})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING
            """,
            values,
        )
        inserted = cursor.rowcount
    conn.commit()
    return inserted


def count_postgres_entries(conn: psycopg.Connection) -> int:
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        return int(cursor.fetchone()[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra a base SQLite legada para PostgreSQL production_entries."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help=f"Caminho do db.sqlite3 legado. Padrao: {DEFAULT_SQLITE_PATH}",
    )
    parser.add_argument(
        "--database-url",
        help="URL PostgreSQL. Se omitido, usa DATABASE_URL/env ou .streamlit/secrets.toml.",
    )
    parser.add_argument("--limit", type=int, help="Importa apenas N registros.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas valida e conta os registros do SQLite, sem gravar no PostgreSQL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_legacy_entries(args.sqlite_path, args.limit)
    print(f"SQLite legado: {args.sqlite_path}")
    print(f"Registros encontrados: {len(rows)}")

    if args.dry_run:
        print("Dry-run concluido. Nenhum dado foi gravado.")
        return 0

    database_url = get_database_url(args.database_url)
    with psycopg.connect(database_url) as conn:
        ensure_postgres_schema(conn)
        before = count_postgres_entries(conn)
        inserted = insert_entries(conn, rows)
        after = count_postgres_entries(conn)

    print(f"Registros antes no PostgreSQL: {before}")
    print(f"Registros inseridos: {inserted}")
    print(f"Registros depois no PostgreSQL: {after}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
