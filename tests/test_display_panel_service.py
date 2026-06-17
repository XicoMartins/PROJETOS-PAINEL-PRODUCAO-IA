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
from services.display_panel_service import compute_display_panel_summary


class DisplayPanelServiceTests(unittest.TestCase):
    @patch("services.display_panel_service.load_planilha_processes")
    @patch("services.display_panel_service.find_planilha_for_display")
    def test_compute_summary_uses_planilha_and_operator_comparison(
        self,
        mock_find_planilha,
        mock_load_planilha,
    ) -> None:
        df = pd.DataFrame(
            {
                "display": ["PG + ECONOMIA HIBRIDO", "PG + ECONOMIA HIBRIDO"],
                "numero_display": ["26010001", "26010001"],
                "processo": ["2,65 Nest 1", "2,65 Nest 1"],
                "maquinario": ["laser chapa", "laser chapa"],
                "operador": ["Ana", "Bia"],
                "quantidade_produzida": [100, 50],
                "duracao_horas": [5.0, 5.0],
                "data_producao": ["2026-04-24", "2026-04-24"],
            }
        )
        filter_context = FilterContext(
            display_selected=["PG + ECONOMIA HIBRIDO"],
            numero_display_selected=["26010001"],
            operador_selected=["Ana"],
            filtered_no_operator=df.copy(),
        )
        mock_find_planilha.return_value = (Path("fake.xlsx"), "fake.xlsx")
        mock_load_planilha.return_value = pd.DataFrame(
            {
                "maquinario_key": ["laser_chapa"],
                "processo_key": ["2_65_nest_1"],
                "qnt_por_produto": [200.0],
            }
        )

        summary = compute_display_panel_summary(
            df,
            filter_context,
            operator_count=2,
        )

        self.assertEqual(summary.planilha_name, "fake.xlsx")
        self.assertEqual(summary.lote_text, "0001")
        self.assertEqual(summary.registros, 2)
        self.assertAlmostEqual(summary.total_produzido, 150.0)
        self.assertAlmostEqual(summary.target_total, 200.0)
        self.assertAlmostEqual(summary.remaining, 50.0)
        self.assertIsNotNone(summary.time_estimate)
        self.assertEqual(summary.time_estimate.subtitle, "Calculo com 2 operadores")
        self.assertAlmostEqual(summary.time_estimate.best_hours, 1.25)
        self.assertAlmostEqual(summary.time_estimate.avg_hours, 50.0 / 30.0)
        self.assertAlmostEqual(summary.time_estimate.worst_hours, 2.5)
        self.assertIsNotNone(summary.operator_comparison)
        self.assertEqual(summary.operator_comparison.label, "Ana")
        self.assertAlmostEqual(summary.operator_comparison.operator_total, 100.0)
        self.assertAlmostEqual(summary.operator_comparison.percent, 100.0 / 150.0)
        self.assertAlmostEqual(summary.operator_comparison.rate_operator, 20.0)
        self.assertAlmostEqual(summary.operator_comparison.rate_process, 15.0)
        self.assertAlmostEqual(
            summary.operator_comparison.ratio,
            20.0 / 15.0,
        )

    @patch("services.display_panel_service.find_planilha_for_display")
    def test_compute_summary_falls_back_to_quantidade_total_when_planilha_missing(
        self,
        mock_find_planilha,
    ) -> None:
        df = pd.DataFrame(
            {
                "display": ["Display X", "Display X"],
                "numero_display": ["26010001", "26010002"],
                "processo": ["Proc A", "Proc A"],
                "maquinario": ["maq 1", "maq 1"],
                "quantidade_produzida": [10, 20],
                "duracao_horas": [1.0, 2.0],
                "quantidade_total": [300, 500],
                "data_producao": ["2026-04-24", "2026-04-24"],
            }
        )
        filter_context = FilterContext(
            display_selected=["Display X"],
            numero_display_selected=["26010001", "26010002"],
            filtered_no_operator=df.copy(),
        )
        mock_find_planilha.return_value = (None, None)

        summary = compute_display_panel_summary(
            df,
            filter_context,
            operator_count=1,
        )

        self.assertEqual(
            summary.planilha_warning,
            "Planilha de processos nao encontrada para o display selecionado.",
        )
        self.assertAlmostEqual(summary.target_total, 800.0)
        self.assertAlmostEqual(summary.remaining, 770.0)
        self.assertEqual(summary.qnt_planilha, None)

    @patch("services.display_panel_service.load_planilha_processes")
    @patch("services.display_panel_service.find_planilha_for_display")
    def test_remaining_from_planilha_does_not_discount_overproduced_process(
        self,
        mock_find_planilha,
        mock_load_planilha,
    ) -> None:
        df = pd.DataFrame(
            {
                "display": ["Display X", "Display X"],
                "numero_display": ["26010001", "26010001"],
                "processo": ["Proc A", "Proc B"],
                "maquinario": ["maq 1", "maq 1"],
                "quantidade_produzida": [150, 20],
                "duracao_horas": [10.0, 2.0],
                "data_producao": ["2026-04-24", "2026-04-24"],
            }
        )
        filter_context = FilterContext(
            display_selected=["Display X"],
            numero_display_selected=["26010001"],
            maquinario_selected=["maq 1"],
            filtered_no_operator=df.copy(),
        )
        mock_find_planilha.return_value = (Path("fake.xlsx"), "fake.xlsx")
        mock_load_planilha.return_value = pd.DataFrame(
            {
                "maquinario_key": ["maq_1", "maq_1"],
                "processo_key": ["proc_a", "proc_b"],
                "qnt_por_produto": [100.0, 100.0],
            }
        )

        summary = compute_display_panel_summary(
            df,
            filter_context,
            operator_count=1,
        )

        self.assertAlmostEqual(summary.target_total, 200.0)
        self.assertAlmostEqual(summary.total_produzido, 170.0)
        self.assertAlmostEqual(summary.remaining, 80.0)


if __name__ == "__main__":
    unittest.main()
