from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panel_views.dashboard import aggregate_selected_period, format_dashboard_scope


class ProductionDashboardTests(unittest.TestCase):
    def test_sector_summary_uses_all_months_in_selected_period(self) -> None:
        frame = pd.DataFrame(
            {
                "data_producao": ["2026-03-01", "2026-04-01", "2026-07-01"],
                "maquinario": ["Laser Chapa", "Solda Mig", "Dobradeira de Chapas"],
                "quantidade_produzida": [100, 200, 443],
            }
        )

        summary = aggregate_selected_period(
            frame,
            "maquinario",
            "quantidade_produzida",
        )

        self.assertEqual(
            set(summary["maquinario"]),
            {"Laser Chapa", "Solda Mig", "Dobradeira de Chapas"},
        )
        self.assertEqual(summary["quantidade_produzida"].sum(), 743)

    def test_sector_summary_applies_limit_after_ranking(self) -> None:
        frame = pd.DataFrame(
            {
                "maquinario": ["M1", "M2", "M3", "M4"],
                "pecas_mortas": [1, 10, 5, 2],
            }
        )

        summary = aggregate_selected_period(
            frame,
            "maquinario",
            "pecas_mortas",
            limit=3,
        )

        self.assertEqual(summary["maquinario"].tolist(), ["M2", "M3", "M4"])

    def test_sector_summary_does_not_hide_items_by_default(self) -> None:
        frame = pd.DataFrame(
            {
                "maquinario": [f"M{index}" for index in range(1, 11)],
                "quantidade_produzida": list(range(1, 11)),
            }
        )

        summary = aggregate_selected_period(
            frame,
            "maquinario",
            "quantidade_produzida",
        )

        self.assertEqual(len(summary), 10)

    def test_sector_summary_groups_missing_labels(self) -> None:
        frame = pd.DataFrame(
            {
                "maquinario": [None, "", "nan", "Laser Chapa"],
                "quantidade_produzida": [1, 2, 3, 4],
            }
        )

        summary = aggregate_selected_period(
            frame,
            "maquinario",
            "quantidade_produzida",
        ).set_index("maquinario")

        self.assertEqual(summary.loc["Nao informado", "quantidade_produzida"], 6)

    def test_scope_shows_selected_dates_and_record_count(self) -> None:
        frame = pd.DataFrame(
            {"data_producao": ["2026-03-23", "2026-06-09", None]}
        )

        scope = format_dashboard_scope(frame)

        self.assertEqual(
            scope,
            "Periodo analisado: 23/03/2026 a 09/06/2026 | 3 registros",
        )

    def test_summary_returns_empty_frame_when_dimension_is_missing(self) -> None:
        frame = pd.DataFrame({"quantidade_produzida": [10]})

        summary = aggregate_selected_period(
            frame,
            "maquinario",
            "quantidade_produzida",
        )

        self.assertTrue(summary.empty)


if __name__ == "__main__":
    unittest.main()
