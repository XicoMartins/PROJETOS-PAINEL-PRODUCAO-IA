from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from data_loader import get_database_url
from services.process_forecast import ForecastResult, require_admin_access

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


TABLE_NAME = "process_forecasts"


def _database_url() -> str:
    if psycopg is None:
        raise RuntimeError("Dependência psycopg não instalada.")
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL não configurada.")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def ensure_forecast_schema(*, is_admin: bool) -> None:
    require_admin_access(is_admin)
    database_url = _database_url()
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT NOT NULL,
                    display TEXT NOT NULL,
                    processo TEXT NOT NULL,
                    maquinario TEXT NOT NULL,
                    lote_base TEXT,
                    quantidade_planejada INTEGER NOT NULL CHECK (quantidade_planejada > 0),
                    inicio_estimado TIMESTAMP NOT NULL,
                    operadores_planejados INTEGER NOT NULL CHECK (operadores_planejados > 0),
                    parametros JSONB NOT NULL,
                    resultado JSONB NOT NULL
                )
                """
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_created_at ON {TABLE_NAME}(created_at DESC)"
            )
        connection.commit()


def _result_payload(result: ForecastResult) -> dict[str, Any]:
    return {
        "confidence": result.confidence,
        "valid_lots": result.valid_lot_count,
        "coefficient_variation": result.coefficient_variation,
        "standard_deviation": result.standard_deviation,
        "historical_productivity": result.historical_productivity,
        "exclusions": result.exclusions,
        "scenarios": {
            name: {
                "productivity": scenario.productivity,
                "required_hours": scenario.required_hours,
                "finish_at": scenario.finish_at.isoformat(),
            }
            for name, scenario in result.scenarios.items()
        },
    }


def save_forecast(
    *,
    is_admin: bool,
    username: str,
    display: str,
    processo: str,
    maquinario: str,
    base_lot: str | None,
    planned_quantity: int,
    start_at: datetime,
    planned_operators: int,
    parameters: dict[str, Any],
    result: ForecastResult,
) -> int:
    require_admin_access(is_admin)
    if not result.scenarios:
        raise ValueError("Não é possível salvar uma previsão sem cenários calculados.")
    ensure_forecast_schema(is_admin=True)
    query = f"""
        INSERT INTO {TABLE_NAME} (
            created_by, display, processo, maquinario, lote_base,
            quantidade_planejada, inicio_estimado, operadores_planejados,
            parametros, resultado
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        RETURNING id
    """
    values = (
        str(username), str(display), str(processo), str(maquinario),
        str(base_lot) if base_lot else None, int(planned_quantity), start_at,
        int(planned_operators), json.dumps(parameters, ensure_ascii=False),
        json.dumps(_result_payload(result), ensure_ascii=False),
    )
    database_url = _database_url()
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, values)
            forecast_id = int(cursor.fetchone()[0])
        connection.commit()
    return forecast_id


def save_routing_forecast(
    *,
    is_admin: bool,
    username: str,
    display: str,
    planned_quantity: int,
    start_at: datetime,
    operators_per_machine: int,
    parameters: dict[str, Any],
    routing_result: dict[str, Any],
) -> int:
    require_admin_access(is_admin)
    ensure_forecast_schema(is_admin=True)
    query = f"""
        INSERT INTO {TABLE_NAME} (
            created_by, display, processo, maquinario, lote_base,
            quantidade_planejada, inicio_estimado, operadores_planejados,
            parametros, resultado
        ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s::jsonb, %s::jsonb)
        RETURNING id
    """
    values = (
        str(username), str(display), "ROTEIRO COMPLETO", "MÚLTIPLOS",
        int(planned_quantity), start_at, int(operators_per_machine),
        json.dumps(parameters, ensure_ascii=False),
        json.dumps(routing_result, ensure_ascii=False),
    )
    database_url = _database_url()
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, values)
            forecast_id = int(cursor.fetchone()[0])
        connection.commit()
    return forecast_id


def list_forecasts(*, is_admin: bool, limit: int = 50) -> list[dict[str, Any]]:
    require_admin_access(is_admin)
    safe_limit = min(max(int(limit), 1), 200)
    ensure_forecast_schema(is_admin=True)
    query = f"""
        SELECT id, created_at, created_by, display, processo, maquinario,
               lote_base, quantidade_planejada, inicio_estimado,
               operadores_planejados, resultado
        FROM {TABLE_NAME}
        ORDER BY created_at DESC
        LIMIT %s
    """
    database_url = _database_url()
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (safe_limit,))
            columns = [description.name for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
