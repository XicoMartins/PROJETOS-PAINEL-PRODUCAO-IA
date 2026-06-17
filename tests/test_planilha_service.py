from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filters import FilterContext
from services.planilha_service import (
    build_display_planilha_filename_map,
    build_remaining_by_process,
    round_piece_total,
)


class PlanilhaServiceTests(unittest.TestCase):
    def test_build_display_map_auto_registers_planilha_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            planilhas_dir = Path(tmp)
            filename = "LISTA DE PROCESSO RACK TESTE 3 BANDEJAS.xlsx"
            (planilhas_dir / filename).touch()

            filename_map = build_display_planilha_filename_map(planilhas_dir)

        self.assertEqual(filename_map["rack_teste_3_bandejas"], filename)

    def test_round_piece_total_removes_planilha_float_noise(self) -> None:
        self.assertEqual(round_piece_total(13.0000003), 13.0)
        self.assertEqual(round_piece_total(89.9999992), 90.0)

    @patch("services.planilha_service.load_planilha_processes")
    @patch("services.planilha_service.find_planilha_for_display")
    def test_remaining_uses_rounded_expected_total(
        self,
        mock_find_planilha,
        mock_load_planilha,
    ) -> None:
        df = pd.DataFrame(
            {
                "display": ["PG + ECONOMIA HIBRIDO"],
                "numero_display": ["26011700"],
                "maquinario": ["laser chapa"],
                "processo": ["2,65 Nest 2 Atualizado"],
                "quantidade_produzida": [13],
                "duracao_horas": [7.5],
            }
        )
        filter_context = FilterContext(
            display_selected=["PG + ECONOMIA HIBRIDO"],
            numero_display_selected=["26011700"],
            maquinario_selected=["laser chapa"],
        )
        mock_find_planilha.return_value = (Path("fake.xlsx"), "fake.xlsx")
        mock_load_planilha.return_value = pd.DataFrame(
            {
                "maquinario_key": ["laser_chapa"],
                "processo_key": ["2_65_nest_2_atualizado"],
                "qnt_por_produto": [0.007647059],
            }
        )

        remaining, warn_msg, _ = build_remaining_by_process(
            df,
            filter_context,
            compute_prod_rate=lambda frame: 1.0,
        )

        self.assertIsNone(warn_msg)
        self.assertEqual(float(remaining.loc[0, "total_esperado"]), 13.0)
        self.assertEqual(float(remaining.loc[0, "pecas_faltantes"]), 0.0)
        self.assertEqual(float(remaining.loc[0, "horas_faltantes"]), 0.0)


if __name__ == "__main__":
    unittest.main()
