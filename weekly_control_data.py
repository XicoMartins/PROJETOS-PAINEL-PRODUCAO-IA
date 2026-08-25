from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import psycopg
import psycopg.rows

from weekly_control import (
    ComponentRequirement,
    MovementEntry,
    ProjectIdentity,
    WeekPeriod,
    component_key,
    movement_from_fields,
    project_key,
)


@dataclass(frozen=True)
class ProjectOption:
    key: str
    identity: ProjectIdentity
    label: str
    last_movement_at: datetime


@dataclass(frozen=True)
class WeeklySourceData:
    previous_target: int | None
    current_target: int | None
    requirements: tuple[ComponentRequirement, ...]
    entries: tuple[MovementEntry, ...]
    detected_component_keys: tuple[str, ...]
    updated_at: datetime | None
    warnings: tuple[str, ...]


def _project_label(identity: ProjectIdentity) -> str:
    return (
        f"{identity.cliente} · {identity.display} · "
        f"Nº {identity.numero_display} · {identity.codigo_pintura}"
    )


def list_painting_projects(db_url: str) -> tuple[ProjectOption, ...]:
    if not db_url:
        raise RuntimeError("DATABASE_URL ainda não foi configurada neste aplicativo.")
    with psycopg.connect(db_url, connect_timeout=12) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT cliente, display, numero_display, codigo_pintura,
                       MAX(COALESCE(timestamp, created_at)) AS last_movement_at
                  FROM public.painting_entries
                 WHERE NULLIF(BTRIM(cliente), '') IS NOT NULL
                   AND NULLIF(BTRIM(display), '') IS NOT NULL
                   AND NULLIF(BTRIM(numero_display), '') IS NOT NULL
                   AND NULLIF(BTRIM(codigo_pintura), '') IS NOT NULL
              GROUP BY cliente, display, numero_display, codigo_pintura
              ORDER BY last_movement_at DESC NULLS LAST,
                       cliente, display, numero_display, codigo_pintura
                """
            )
            rows = cursor.fetchall()

    projects = []
    for row in rows:
        identity = ProjectIdentity(
            cliente=str(row["cliente"]).strip(),
            display=str(row["display"]).strip(),
            numero_display=str(row["numero_display"]).strip(),
            codigo_pintura=str(row["codigo_pintura"]).strip(),
        )
        projects.append(
            ProjectOption(
                key=project_key(identity),
                identity=identity,
                label=_project_label(identity),
                last_movement_at=row["last_movement_at"],
            )
        )
    return tuple(projects)


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_weekly_source(
    db_url: str,
    identity: ProjectIdentity,
    previous_period: WeekPeriod,
    current_period: WeekPeriod,
) -> WeeklySourceData:
    if not db_url:
        raise RuntimeError("DATABASE_URL ainda não foi configurada neste aplicativo.")
    key = project_key(identity)
    with psycopg.connect(db_url, connect_timeout=12) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT week_start, target_sets
                  FROM public.painting_weekly_targets
                 WHERE project_key = %s
                   AND week_start IN (%s, %s)
              ORDER BY week_start
                """,
                (key, previous_period.start, current_period.start),
            )
            target_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT source_component_key, display_name, quantity_per_set,
                       display_order, active
                  FROM public.painting_component_requirements
                 WHERE project_key = %s
              ORDER BY display_order, source_component_key
                """,
                (key,),
            )
            requirement_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT processo, maquinario, quantidade, timestamp, created_at
                  FROM public.painting_entries
                 WHERE cliente = %s
                   AND display = %s
                   AND numero_display = %s
                   AND codigo_pintura = %s
              ORDER BY timestamp, created_at, id
                """,
                (
                    identity.cliente,
                    identity.display,
                    identity.numero_display,
                    identity.codigo_pintura,
                ),
            )
            movement_rows = cursor.fetchall()

    targets = {row["week_start"]: int(row["target_sets"]) for row in target_rows}
    requirements = tuple(
        ComponentRequirement(
            source_component_key=component_key(row["source_component_key"]),
            display_name=str(row["display_name"]).strip(),
            quantity_per_set=(
                Decimal(str(row["quantity_per_set"]))
                if row["quantity_per_set"] is not None
                else None
            ),
            display_order=int(row["display_order"]),
            active=bool(row["active"]),
        )
        for row in requirement_rows
    )
    entries: list[MovementEntry] = []
    warnings: list[str] = []
    for row in movement_rows:
        movement = movement_from_fields(row.get("processo"), row.get("maquinario"))
        occurred_at = _as_datetime(row.get("timestamp") or row.get("created_at"))
        if movement is None or occurred_at is None or row.get("quantidade") is None:
            warnings.append(
                f"Movimento ignorado por dados incompletos: {row.get('processo') or 'sem processo'}"
            )
            continue
        try:
            quantity = Decimal(str(row["quantidade"]))
        except InvalidOperation:
            warnings.append(f"Quantidade inválida: {row.get('processo') or 'sem processo'}")
            continue
        entries.append(
            MovementEntry(
                component_key=component_key(row.get("processo")),
                movement=movement,
                quantity=quantity,
                occurred_at=occurred_at,
            )
        )
    detected = tuple(
        sorted(
            {
                entry.component_key
                for entry in entries
                if entry.component_key and not entry.component_key.startswith("TINTA")
            }
        )
    )
    return WeeklySourceData(
        previous_target=targets.get(previous_period.start),
        current_target=targets.get(current_period.start),
        requirements=requirements,
        entries=tuple(entries),
        detected_component_keys=detected,
        updated_at=max((entry.occurred_at for entry in entries), default=None),
        warnings=tuple(warnings),
    )


def _validate_period(period: WeekPeriod) -> None:
    if period.start.weekday() != 0 or period.end != period.start + timedelta(days=4):
        raise ValueError("A semana deve começar na segunda-feira e terminar na sexta-feira.")


def save_weekly_target(
    db_url: str,
    identity: ProjectIdentity,
    period: WeekPeriod,
    target_sets: int,
) -> None:
    if not db_url:
        raise RuntimeError("DATABASE_URL ainda não foi configurada neste aplicativo.")
    _validate_period(period)
    if isinstance(target_sets, bool) or not isinstance(target_sets, int) or target_sets < 0:
        raise ValueError("A meta acumulada deve ser um número inteiro igual ou maior que zero.")
    with psycopg.connect(db_url, connect_timeout=12) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.painting_weekly_targets (
                    project_key, source_cliente, source_display,
                    source_numero_display, source_codigo_pintura,
                    week_start, week_end, target_sets
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (project_key, week_start) DO UPDATE SET
                    source_cliente = EXCLUDED.source_cliente,
                    source_display = EXCLUDED.source_display,
                    source_numero_display = EXCLUDED.source_numero_display,
                    source_codigo_pintura = EXCLUDED.source_codigo_pintura,
                    week_end = EXCLUDED.week_end,
                    target_sets = EXCLUDED.target_sets,
                    updated_at = now()
                """,
                (
                    project_key(identity),
                    identity.cliente,
                    identity.display,
                    identity.numero_display,
                    identity.codigo_pintura,
                    period.start,
                    period.end,
                    target_sets,
                ),
            )
        connection.commit()


def _validated_requirements(
    requirements: tuple[ComponentRequirement, ...],
) -> tuple[ComponentRequirement, ...]:
    validated: list[ComponentRequirement] = []
    seen_keys: set[str] = set()
    seen_orders: set[int] = set()
    for requirement in requirements:
        key = component_key(requirement.source_component_key)
        display_name = str(requirement.display_name).strip()
        quantity = requirement.quantity_per_set
        order = requirement.display_order
        if not key or not display_name:
            raise ValueError("Componente e nome de exibição são obrigatórios.")
        if quantity is not None and quantity <= 0:
            raise ValueError("A quantidade por conjunto deve ser maior que zero.")
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise ValueError("A ordem de exibição deve ser um inteiro igual ou maior que zero.")
        if key in seen_keys:
            raise ValueError(f"Componente duplicado: {key}.")
        if order in seen_orders:
            raise ValueError(f"Ordem de exibição duplicada: {order}.")
        seen_keys.add(key)
        seen_orders.add(order)
        validated.append(
            ComponentRequirement(
                source_component_key=key,
                display_name=display_name,
                quantity_per_set=quantity,
                display_order=order,
                active=bool(requirement.active),
            )
        )
    return tuple(validated)


def save_component_requirements(
    db_url: str,
    identity: ProjectIdentity,
    requirements: tuple[ComponentRequirement, ...],
) -> None:
    if not db_url:
        raise RuntimeError("DATABASE_URL ainda não foi configurada neste aplicativo.")
    validated = _validated_requirements(requirements)
    key = project_key(identity)
    with psycopg.connect(db_url, connect_timeout=12) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.painting_component_requirements WHERE project_key = %s",
                (key,),
            )
            for requirement in validated:
                cursor.execute(
                    """
                    INSERT INTO public.painting_component_requirements (
                        project_key, source_component_key, display_name,
                        quantity_per_set, display_order, active
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        key,
                        requirement.source_component_key,
                        requirement.display_name,
                        requirement.quantity_per_set,
                        requirement.display_order,
                        requirement.active,
                    ),
                )
        connection.commit()
