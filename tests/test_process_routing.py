from __future__ import annotations

import sys
import unittest
from datetime import datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.process_forecast import WorkCalendar, generate_forecast
from services.process_routing import (
    RoutingTask,
    collapse_missing_dependencies,
    schedule_routing,
    topological_order,
)
from services.process_forecast_repository import save_routing_forecast
from tests.test_process_forecast import history


CALENDAR = WorkCalendar(
    daily_hours=24,
    shift_start=time(0),
    productive_weekdays=frozenset(range(7)),
)
START = datetime(2026, 7, 20, 0)


def task(
    code: str,
    *,
    machine: str,
    hours: float,
    predecessors: tuple[str, ...] = (),
    units: int = 1,
) -> RoutingTask:
    return RoutingTask(
        code=code,
        process=code,
        machine=machine,
        predecessors=predecessors,
        machine_units=units,
        required_quantity=100,
        scenario_hours={"Provável": hours},
    )


class ProcessRoutingTests(unittest.TestCase):
    def test_missing_process_is_bypassed_to_nearest_available_predecessor(self) -> None:
        dependencies = {
            "P01": (),
            "P02": ("P01",),
            "P03": ("P02",),
            "P04": ("P03",),
        }
        effective = collapse_missing_dependencies(
            dependencies, {"P01", "P03", "P04"}
        )
        self.assertEqual(effective["P03"], ("P01",))
        self.assertEqual(effective["P04"], ("P03",))

    def test_missing_initial_process_leaves_next_available_process_initial(self) -> None:
        dependencies = {"P01": (), "P02": ("P01",)}
        effective = collapse_missing_dependencies(dependencies, {"P02"})
        self.assertEqual(effective["P02"], ())

    def test_routing_persistence_is_admin_only(self) -> None:
        with self.assertRaises(PermissionError):
            save_routing_forecast(
                is_admin=False, username="user", display="A", planned_quantity=1,
                start_at=START, operators_per_machine=1, parameters={}, routing_result={},
            )

    def test_dependent_process_starts_after_predecessor(self) -> None:
        result = schedule_routing(
            [task("P01", machine="A", hours=10), task("P02", machine="B", hours=5, predecessors=("P01",))],
            scenario="Provável", start_at=START, calendar=CALENDAR,
            machine_capacities={"A": 1, "B": 1},
        )
        rows = result.schedule.set_index("code")
        self.assertEqual(rows.loc["P02", "start"], rows.loc["P01", "finish"])
        self.assertEqual(result.finish_at, START.replace(hour=15))

    def test_independent_processes_run_in_parallel_on_different_machines(self) -> None:
        result = schedule_routing(
            [task("P01", machine="A", hours=10), task("P02", machine="B", hours=5)],
            scenario="Provável", start_at=START, calendar=CALENDAR,
            machine_capacities={"A": 1, "B": 1},
        )
        rows = result.schedule.set_index("code")
        self.assertEqual(rows.loc["P01", "start"], rows.loc["P02", "start"])
        self.assertEqual(result.finish_at, START.replace(hour=10))

    def test_same_machine_capacity_serializes_parallel_processes(self) -> None:
        result = schedule_routing(
            [task("P01", machine="A", hours=10), task("P02", machine="A", hours=5)],
            scenario="Provável", start_at=START, calendar=CALENDAR,
            machine_capacities={"A": 1},
        )
        rows = result.schedule.set_index("code")
        self.assertEqual(rows.loc["P02", "start"], rows.loc["P01", "finish"])
        self.assertEqual(result.finish_at, START.replace(hour=15))

    def test_two_machines_allow_two_parallel_allocations(self) -> None:
        result = schedule_routing(
            [task("P01", machine="A", hours=10), task("P02", machine="A", hours=5)],
            scenario="Provável", start_at=START, calendar=CALENDAR,
            machine_capacities={"A": 2},
        )
        rows = result.schedule.set_index("code")
        self.assertEqual(rows.loc["P01", "start"], rows.loc["P02", "start"])

    def test_allocation_cannot_exceed_machine_capacity(self) -> None:
        with self.assertRaises(ValueError):
            schedule_routing(
                [task("P01", machine="A", hours=10, units=2)],
                scenario="Provável", start_at=START, calendar=CALENDAR,
                machine_capacities={"A": 1},
            )

    def test_dependency_cycle_is_rejected(self) -> None:
        tasks = [
            task("P01", machine="A", hours=1, predecessors=("P02",)),
            task("P02", machine="B", hours=1, predecessors=("P01",)),
        ]
        with self.assertRaises(ValueError):
            topological_order(tasks)

    def test_machine_quantity_reduces_individual_process_time(self) -> None:
        one = generate_forecast(
            history([10, 12, 14]), planned_quantity=240, start_at=START,
            planned_operators=1, planned_machines=1, calendar=CALENDAR,
        )
        two = generate_forecast(
            history([10, 12, 14]), planned_quantity=240, start_at=START,
            planned_operators=1, planned_machines=2, calendar=CALENDAR,
        )
        self.assertAlmostEqual(
            two.scenarios["Provável"].required_hours,
            one.scenarios["Provável"].required_hours / 2,
        )


if __name__ == "__main__":
    unittest.main()
