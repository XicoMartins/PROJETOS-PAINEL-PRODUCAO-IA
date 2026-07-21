from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import build_navigation_tabs, get_user_role
from services.process_forecast import (
    WorkCalendar,
    add_productive_hours,
    generate_forecast,
    prepare_lot_history,
    require_admin_access,
)
from services.process_forecast_repository import list_forecasts


def history(rates: list[float], *, hours: float = 2.0) -> pd.DataFrame:
    rows = []
    for index, rate in enumerate(rates, start=1):
        rows.append(
            {
                "id": index,
                "display": "DISPLAY A",
                "processo": "SOLDA",
                "maquinario": "MIG",
                "numero_display": f"2601{index:04d}",
                "data_producao": date(2026, 1, min(index, 28)),
                "hora_inicio": "07:00",
                "hora_conclusao": "09:00",
                "quantidade_produzida": rate * hours,
                "duracao_horas": hours,
                "operadores_lista": ["Ana"],
                "pecas_mortas": 0,
            }
        )
    return pd.DataFrame(rows)


CALENDAR = WorkCalendar(
    daily_hours=9,
    shift_start=time(7),
    productive_weekdays=frozenset({0, 1, 2, 3, 4}),
)


class ProcessForecastTests(unittest.TestCase):
    def test_admin_sees_tab(self) -> None:
        self.assertEqual(get_user_role("admin"), "admin")
        self.assertIn("PREVISÃO DE PROCESSO", build_navigation_tabs(is_admin=True))

    def test_common_user_does_not_see_tab_and_cannot_call_service(self) -> None:
        self.assertEqual(get_user_role("producao"), "user")
        self.assertNotIn("PREVISÃO DE PROCESSO", build_navigation_tabs(is_admin=False))
        with self.assertRaises(PermissionError):
            require_admin_access(False)
        with self.assertRaises(PermissionError):
            list_forecasts(is_admin=False)

    def test_incompatible_processes_are_not_mixed(self) -> None:
        frame = history([10, 12])
        frame.loc[1, "processo"] = "CORTE"
        with self.assertRaises(ValueError):
            prepare_lot_history(frame)

    def test_display_without_history(self) -> None:
        result = generate_forecast(
            pd.DataFrame(), planned_quantity=100, start_at=datetime(2026, 7, 20, 7),
            planned_operators=1, calendar=CALENDAR,
        )
        self.assertFalse(result.scenarios)
        self.assertEqual(result.confidence, "Sem histórico suficiente")

    def test_one_lot_is_insufficient(self) -> None:
        result = generate_forecast(
            history([10]), planned_quantity=100, start_at=datetime(2026, 7, 20, 7),
            planned_operators=1, calendar=CALENDAR,
        )
        self.assertFalse(result.scenarios)

    def test_sufficient_history_has_high_confidence(self) -> None:
        result = generate_forecast(
            history([10] * 10), planned_quantity=100,
            start_at=datetime(2026, 7, 20, 7), planned_operators=1, calendar=CALENDAR,
        )
        self.assertEqual(result.confidence, "Alta")
        self.assertEqual(result.valid_lot_count, 10)

    def test_zero_duration_is_removed(self) -> None:
        frame = history([10, 12])
        frame.loc[0, "duracao_horas"] = 0
        lots, exclusions = prepare_lot_history(frame)
        self.assertEqual(len(lots), 1)
        self.assertEqual(exclusions["duracao_invalida"], 1)

    def test_duplicate_id_is_removed(self) -> None:
        frame = pd.concat([history([10, 12]), history([10]).assign(id=1)], ignore_index=True)
        lots, exclusions = prepare_lot_history(frame)
        self.assertEqual(len(lots), 2)
        self.assertEqual(exclusions["duplicados"], 1)

    def test_outlier_is_removed(self) -> None:
        lots, exclusions = prepare_lot_history(history([10, 11, 12, 13, 100]))
        self.assertEqual(len(lots), 4)
        self.assertEqual(exclusions["outliers"], 1)

    def test_invalid_planned_quantity(self) -> None:
        for value in (0, -1, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                generate_forecast(
                    history([10, 12]), planned_quantity=value,
                    start_at=datetime(2026, 7, 20, 7), planned_operators=1,
                    calendar=CALENDAR,
                )

    def test_friday_near_shift_end_crosses_weekend(self) -> None:
        finish = add_productive_hours(datetime(2026, 7, 24, 15), 2, CALENDAR)
        self.assertEqual(finish, datetime(2026, 7, 27, 8))

    def test_holiday_is_skipped(self) -> None:
        calendar = WorkCalendar(
            daily_hours=9, shift_start=time(7),
            productive_weekdays=frozenset({0, 1, 2, 3, 4}),
            holidays=frozenset({date(2026, 7, 27)}),
        )
        finish = add_productive_hours(datetime(2026, 7, 24, 15), 2, calendar)
        self.assertEqual(finish, datetime(2026, 7, 28, 8))

    def test_scenario_order(self) -> None:
        result = generate_forecast(
            history([8, 10, 12, 14, 16]), planned_quantity=500,
            start_at=datetime(2026, 7, 20, 7), planned_operators=1, calendar=CALENDAR,
        )
        optimistic = result.scenarios["Otimista"]
        probable = result.scenarios["Provável"]
        conservative = result.scenarios["Conservador"]
        self.assertGreaterEqual(optimistic.productivity, probable.productivity)
        self.assertGreaterEqual(probable.productivity, conservative.productivity)
        self.assertLessEqual(optimistic.finish_at, probable.finish_at)
        self.assertLessEqual(probable.finish_at, conservative.finish_at)

    def test_quantity_change_recalculates_duration(self) -> None:
        small = generate_forecast(
            history([10, 12, 14]), planned_quantity=100,
            start_at=datetime(2026, 7, 20, 7), planned_operators=1, calendar=CALENDAR,
        )
        large = generate_forecast(
            history([10, 12, 14]), planned_quantity=200,
            start_at=datetime(2026, 7, 20, 7), planned_operators=1, calendar=CALENDAR,
        )
        self.assertAlmostEqual(
            large.scenarios["Provável"].required_hours,
            small.scenarios["Provável"].required_hours * 2,
        )

    def test_operator_change_recalculates_productivity(self) -> None:
        one = generate_forecast(
            history([10, 12, 14]), planned_quantity=200,
            start_at=datetime(2026, 7, 20, 7), planned_operators=1, calendar=CALENDAR,
        )
        two = generate_forecast(
            history([10, 12, 14]), planned_quantity=200,
            start_at=datetime(2026, 7, 20, 7), planned_operators=2, calendar=CALENDAR,
        )
        self.assertAlmostEqual(
            two.scenarios["Provável"].productivity,
            one.scenarios["Provável"].productivity * 2,
        )
        self.assertAlmostEqual(
            two.scenarios["Provável"].required_hours,
            one.scenarios["Provável"].required_hours / 2,
        )

    def test_base_lot_comparison(self) -> None:
        frame = history([10, 12, 14])
        result = generate_forecast(
            frame, planned_quantity=100, start_at=datetime(2026, 7, 20, 7),
            planned_operators=1, calendar=CALENDAR, base_lot="26010003",
        )
        self.assertIsNotNone(result.base_comparison)
        self.assertEqual(result.base_comparison["position"], "Acima da média")


if __name__ == "__main__":
    unittest.main()
