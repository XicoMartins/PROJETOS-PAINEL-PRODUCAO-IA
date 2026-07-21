from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from services.process_forecast import WorkCalendar, add_productive_hours


@dataclass(frozen=True)
class RoutingTask:
    code: str
    process: str
    machine: str
    predecessors: tuple[str, ...]
    machine_units: int
    required_quantity: int
    scenario_hours: dict[str, float]


@dataclass
class RoutingScenario:
    name: str
    finish_at: datetime
    schedule: pd.DataFrame


def topological_order(tasks: list[RoutingTask]) -> list[str]:
    task_map = {task.code: task for task in tasks}
    if len(task_map) != len(tasks):
        raise ValueError("Os códigos dos processos devem ser únicos.")
    for task in tasks:
        unknown = set(task.predecessors) - set(task_map)
        if unknown:
            raise ValueError(
                f"O processo {task.code} referencia predecessores inexistentes: "
                + ", ".join(sorted(unknown))
            )
        if task.code in task.predecessors:
            raise ValueError(f"O processo {task.code} não pode depender dele mesmo.")

    incoming = {task.code: set(task.predecessors) for task in tasks}
    ready = [task.code for task in tasks if not incoming[task.code]]
    ordered: list[str] = []
    while ready:
        code = ready.pop(0)
        ordered.append(code)
        for task in tasks:
            if code in incoming[task.code]:
                incoming[task.code].remove(code)
                if not incoming[task.code] and task.code not in ordered and task.code not in ready:
                    ready.append(task.code)
    if len(ordered) != len(tasks):
        cyclic = sorted(set(task_map) - set(ordered))
        raise ValueError("Dependência cíclica entre processos: " + ", ".join(cyclic))
    return ordered


def collapse_missing_dependencies(
    dependencies: dict[str, tuple[str, ...]],
    available_codes: set[str],
) -> dict[str, tuple[str, ...]]:
    """Substitui predecessores sem dados pelos ancestrais disponíveis mais próximos."""
    memo: dict[str, tuple[str, ...]] = {}

    def expand(code: str, path: set[str]) -> tuple[str, ...]:
        if code in available_codes:
            return (code,)
        if code in path:
            raise ValueError("Dependência cíclica envolvendo processo sem histórico.")
        if code not in dependencies:
            raise ValueError(f"Código de processo inexistente: {code}.")
        if code in memo:
            return memo[code]
        expanded: list[str] = []
        for predecessor in dependencies[code]:
            for ancestor in expand(predecessor, path | {code}):
                if ancestor not in expanded:
                    expanded.append(ancestor)
        memo[code] = tuple(expanded)
        return memo[code]

    result: dict[str, tuple[str, ...]] = {}
    for code in available_codes:
        expanded: list[str] = []
        for predecessor in dependencies.get(code, ()):
            for ancestor in expand(predecessor, {code}):
                if ancestor != code and ancestor not in expanded:
                    expanded.append(ancestor)
        result[code] = tuple(expanded)
    return result


def _align_to_calendar(value: datetime, calendar: WorkCalendar) -> datetime:
    # Usa um intervalo desprezível para reaproveitar exatamente as regras do calendário.
    aligned = add_productive_hours(value, 1e-8, calendar)
    return aligned - timedelta(hours=1e-8)


def _resource_overload(
    start: datetime,
    finish: datetime,
    units: int,
    capacity: int,
    scheduled: list[dict],
) -> list[dict]:
    overlapping = [
        item for item in scheduled
        if item["start"] < finish and item["finish"] > start
    ]
    if not overlapping:
        return []
    boundaries = sorted(
        {start, finish}
        | {max(start, item["start"]) for item in overlapping}
        | {min(finish, item["finish"]) for item in overlapping}
    )
    for left, right in zip(boundaries, boundaries[1:]):
        if left >= right:
            continue
        active = [item for item in overlapping if item["start"] < right and item["finish"] > left]
        if units + sum(item["units"] for item in active) > capacity:
            return active
    return []


def schedule_routing(
    tasks: list[RoutingTask],
    *,
    scenario: str,
    start_at: datetime,
    calendar: WorkCalendar,
    machine_capacities: dict[str, int],
) -> RoutingScenario:
    if not tasks:
        raise ValueError("Inclua ao menos um processo no roteiro.")
    order = topological_order(tasks)
    task_map = {task.code: task for task in tasks}
    rows: dict[str, dict] = {}
    resources: dict[str, list[dict]] = {}

    for code in order:
        task = task_map[code]
        if scenario not in task.scenario_hours:
            raise ValueError(f"O processo {code} não possui duração para o cenário {scenario}.")
        hours = float(task.scenario_hours[scenario])
        if hours <= 0:
            raise ValueError(f"A duração do processo {code} deve ser positiva.")
        capacity = int(machine_capacities.get(task.machine, 0))
        if capacity <= 0:
            raise ValueError(f"Informe a capacidade disponível para {task.machine}.")
        if task.machine_units <= 0 or task.machine_units > capacity:
            raise ValueError(
                f"{code}: máquinas alocadas devem estar entre 1 e {capacity}."
            )

        candidate = start_at
        if task.predecessors:
            candidate = max(rows[item]["finish"] for item in task.predecessors)
        candidate = _align_to_calendar(candidate, calendar)
        machine_schedule = resources.setdefault(task.machine, [])
        while True:
            finish = add_productive_hours(candidate, hours, calendar)
            conflicts = _resource_overload(
                candidate, finish, task.machine_units, capacity, machine_schedule
            )
            if not conflicts:
                break
            candidate = _align_to_calendar(min(item["finish"] for item in conflicts), calendar)

        row = {
            "code": code,
            "process": task.process,
            "machine": task.machine,
            "predecessors": "; ".join(task.predecessors) or "—",
            "machine_units": task.machine_units,
            "required_quantity": task.required_quantity,
            "hours": hours,
            "start": candidate,
            "finish": finish,
        }
        rows[code] = row
        machine_schedule.append(
            {"start": candidate, "finish": finish, "units": task.machine_units, "code": code}
        )

    schedule = pd.DataFrame([rows[code] for code in order])
    return RoutingScenario(
        name=scenario,
        finish_at=max(row["finish"] for row in rows.values()),
        schedule=schedule,
    )


def schedule_all_scenarios(
    tasks: list[RoutingTask],
    *,
    start_at: datetime,
    calendar: WorkCalendar,
    machine_capacities: dict[str, int],
) -> dict[str, RoutingScenario]:
    return {
        scenario: schedule_routing(
            tasks,
            scenario=scenario,
            start_at=start_at,
            calendar=calendar,
            machine_capacities=machine_capacities,
        )
        for scenario in ("Otimista", "Provável", "Conservador")
    }
