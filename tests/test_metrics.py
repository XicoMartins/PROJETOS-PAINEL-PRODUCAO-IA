from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filters import FilterContext
from services.metrics import compute_dashboard_metrics, resolve_last_update_metric
from services.metrics import build_dashboard_gauge


class MetricsServiceTests(unittest.TestCase):
    def test_resolve_last_update_metric_returns_datetime_for_processo(self) -> None:
        df = pd.DataFrame(
            {
                "data_producao": ["2026-04-23", "2026-04-24"],
                "hora_conclusao": ["14:10", "15:30"],
            }
        )
        filter_context = FilterContext(
            processo_selected=["Nest 1"],
            filtered_no_operator=df.copy(),
        )

        title, value = resolve_last_update_metric(df, filter_context)

        self.assertEqual(title, "Ult. atualizacao processo")
        self.assertEqual(value, "24/04/2026 15:30")

    def test_resolve_last_update_metric_returns_date_for_display_scope(self) -> None:
        df = pd.DataFrame(
            {
                "data_producao": ["2026-04-23", "2026-04-24"],
                "hora_conclusao": ["14:10", "15:30"],
            }
        )
        filter_context = FilterContext(filtered_no_operator=df.copy())

        title, value = resolve_last_update_metric(df, filter_context)

        self.assertEqual(title, "Ultima atualizacao")
        self.assertEqual(value, "24/04/2026")

    @patch("services.metrics.estimate_target_total")
    @patch("services.metrics.estimate_ideal_rate")
    @patch("services.metrics.estimate_capacity_hours")
    def test_compute_dashboard_metrics_calculates_core_indicators(
        self,
        mock_capacity_hours,
        mock_ideal_rate,
        mock_target_total,
    ) -> None:
        df = pd.DataFrame(
            {
                "quantidade_produzida": [50, 30],
                "pecas_mortas": [10, 10],
                "duracao_horas": [4.0, 6.0],
            }
        )
        mock_capacity_hours.return_value = 20.0
        mock_ideal_rate.return_value = 10.0
        mock_target_total.return_value = 200.0

        metrics = compute_dashboard_metrics(df)

        self.assertAlmostEqual(metrics["produced"], 80.0)
        self.assertAlmostEqual(metrics["scrap"], 20.0)
        self.assertAlmostEqual(metrics["active_hours"], 10.0)
        self.assertAlmostEqual(metrics["inactive_hours"], 10.0)
        self.assertAlmostEqual(metrics["quality"], 0.8)
        self.assertAlmostEqual(metrics["availability"], 0.5)
        self.assertAlmostEqual(metrics["performance"], 0.8)
        self.assertAlmostEqual(metrics["productivity"], 0.4)
        self.assertAlmostEqual(metrics["scrap_rate"], 0.2)
        self.assertAlmostEqual(metrics["oee"], 0.32)
        self.assertAlmostEqual(metrics["target_total"], 200.0)

    @patch("services.metrics.estimate_target_total", return_value=100.0)
    @patch("services.metrics.estimate_ideal_rate", return_value=10.0)
    @patch("services.metrics.estimate_capacity_hours", return_value=5.0)
    def test_availability_is_capped_at_one_and_does_not_inflate_oee(
        self,
        _mock_capacity_hours,
        _mock_ideal_rate,
        _mock_target_total,
    ) -> None:
        df = pd.DataFrame(
            {
                "quantidade_produzida": [80],
                "pecas_mortas": [20],
                "duracao_horas": [10.0],
            }
        )

        metrics = compute_dashboard_metrics(df)

        self.assertEqual(metrics["availability"], 1.0)
        self.assertAlmostEqual(metrics["performance"], 0.8)
        self.assertAlmostEqual(metrics["quality"], 0.8)
        self.assertAlmostEqual(metrics["oee"], 0.64)

    def test_gauge_shows_na_when_metric_is_unavailable(self) -> None:
        figure = build_dashboard_gauge("OEE", None)

        self.assertEqual(figure.data[0]["mode"], "gauge")
        self.assertEqual(figure.layout.annotations[0]["text"], "N/A")


if __name__ == "__main__":
    unittest.main()
