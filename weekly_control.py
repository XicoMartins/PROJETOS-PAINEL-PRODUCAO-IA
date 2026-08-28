from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class ProjectIdentity:
    cliente: str
    display: str
    numero_display: str
    codigo_pintura: str


@dataclass(frozen=True)
class WeekPeriod:
    start: date
    end: date


@dataclass(frozen=True)
class MovementEntry:
    component_key: str
    movement: Literal["remessa", "retorno"]
    quantity: Decimal
    occurred_at: datetime


@dataclass(frozen=True)
class ComponentRequirement:
    source_component_key: str
    display_name: str
    quantity_per_set: Decimal | None
    display_order: int
    active: bool


@dataclass(frozen=True)
class WeeklyComponent:
    component_key: str
    display_name: str
    quantity_per_set: Decimal | None
    total_remessa: Decimal | None
    total_retorno: Decimal | None
    painting_balance: Decimal | None
    previous_balance: Decimal | None
    current_balance: Decimal | None


@dataclass(frozen=True)
class WeeklySummary:
    target_sets: int | None
    total_components: Decimal | None
    pending_pieces: Decimal
    pending_references: int


@dataclass(frozen=True)
class WeeklyControl:
    components: tuple[WeeklyComponent, ...]
    paint_rows: tuple[WeeklyComponent, ...]
    previous_summary: WeeklySummary
    current_summary: WeeklySummary
    warnings: tuple[str, ...]


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text).strip().upper()


def project_key(identity: ProjectIdentity) -> str:
    canonical = "\x1f".join(
        normalize_text(value)
        for value in (
            identity.cliente,
            identity.display,
            identity.numero_display,
            identity.codigo_pintura,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def weekly_periods(now: datetime | None = None) -> tuple[WeekPeriod, WeekPeriod]:
    instant = now or datetime.now(SAO_PAULO)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=SAO_PAULO)
    else:
        instant = instant.astimezone(SAO_PAULO)
    current = week_period_for_date(instant.date())
    following = week_period_for_date(current.start + timedelta(days=7))
    return current, following


def week_period_for_date(day: date) -> WeekPeriod:
    start = day - timedelta(days=day.weekday())
    return WeekPeriod(start, start + timedelta(days=4))


def validate_target_submission(
    selected_day: date,
    target_sets: int,
    confirmed: bool,
) -> tuple[WeekPeriod, int]:
    if not confirmed:
        raise ValueError("Confirme a gravação da meta acumulada.")
    if isinstance(target_sets, bool) or not isinstance(target_sets, int) or target_sets < 0:
        raise ValueError("A meta acumulada deve ser um número inteiro igual ou maior que zero.")
    return week_period_for_date(selected_day), target_sets


def movement_from_fields(
    process: object,
    machinery: object = "",
) -> Literal["remessa", "retorno"] | None:
    for text in (normalize_text(process), normalize_text(machinery)):
        if "RETORNO" in text:
            return "retorno"
        if "ENVIO" in text or "REMESSA" in text:
            return "remessa"
    return None


def component_key(process: object) -> str:
    key = normalize_text(process)
    key = re.sub(r"\b(?:ENVIO|REMESSA|RETORNO)\b", " ", key)
    key = re.sub(r"[-–—]+", " ", key)
    return re.sub(r"\s+", " ", key).strip()


def _difference(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _target_balance(
    total: Decimal | None,
    target: int | None,
    quantity_per_set: Decimal | None,
) -> Decimal | None:
    if total is None or target is None or quantity_per_set is None:
        return None
    return total - (Decimal(target) * quantity_per_set)


def _summary(
    rows: tuple[WeeklyComponent, ...],
    target: int | None,
    balance_name: Literal["previous_balance", "current_balance"],
) -> WeeklySummary:
    quantities = [row.quantity_per_set for row in rows]
    total_components = None
    if target is not None and all(quantity is not None for quantity in quantities):
        total_components = Decimal(target) * sum(
            (quantity for quantity in quantities if quantity is not None),
            Decimal("0"),
        )
    pending = [
        balance
        for row in rows
        if (balance := getattr(row, balance_name)) is not None and balance < 0
    ]
    return WeeklySummary(
        target_sets=target,
        total_components=total_components,
        pending_pieces=sum((-balance for balance in pending), Decimal("0")),
        pending_references=len(pending),
    )


def build_weekly_control(
    previous_target: int | None,
    current_target: int | None,
    requirements: tuple[ComponentRequirement, ...],
    entries: tuple[MovementEntry, ...],
) -> WeeklyControl:
    totals: dict[tuple[str, str], Decimal] = {}
    for entry in entries:
        key = (normalize_text(entry.component_key), entry.movement)
        totals[key] = totals.get(key, Decimal("0")) + entry.quantity

    rows: list[WeeklyComponent] = []
    for requirement in sorted(
        (item for item in requirements if item.active),
        key=lambda item: item.display_order,
    ):
        key = normalize_text(requirement.source_component_key)
        remessa = totals.get((key, "remessa"))
        retorno = totals.get((key, "retorno"))
        rows.append(
            WeeklyComponent(
                component_key=key,
                display_name=requirement.display_name,
                quantity_per_set=requirement.quantity_per_set,
                total_remessa=remessa,
                total_retorno=retorno,
                painting_balance=_difference(remessa, retorno),
                previous_balance=_target_balance(
                    retorno,
                    previous_target,
                    requirement.quantity_per_set,
                ),
                current_balance=_target_balance(
                    remessa,
                    current_target,
                    requirement.quantity_per_set,
                ),
            )
        )
    component_rows = tuple(rows)
    paint_rows = tuple(
        WeeklyComponent(
            component_key=key,
            display_name=key,
            quantity_per_set=None,
            total_remessa=totals.get((key, "remessa")),
            total_retorno=totals.get((key, "retorno")),
            painting_balance=_difference(
                totals.get((key, "remessa")),
                totals.get((key, "retorno")),
            ),
            previous_balance=None,
            current_balance=None,
        )
        for key in sorted({item[0] for item in totals if item[0].startswith("TINTA")})
    )
    return WeeklyControl(
        components=component_rows,
        paint_rows=paint_rows,
        previous_summary=_summary(component_rows, previous_target, "previous_balance"),
        current_summary=_summary(component_rows, current_target, "current_balance"),
        warnings=(),
    )
