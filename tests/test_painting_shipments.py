from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_loader import PAINTING_COLUMNS, _normalize_painting_frame
from filters import render_month_range_filter
from painting_filters import filter_painting_frame
from services.painting_panel_service import (
    compute_painting_panel_summary,
    extract_painting_color,
    extract_painting_multiplier,
    find_painting_image,
)


class PaintingShipmentsTests(unittest.TestCase):
    @patch("filters.st.markdown")
    @patch("filters.st.select_slider", return_value=("2026-06", "2026-07"))
    @patch(
        "filters._sanitize_month_range_state",
        return_value=("2026-06", "2026-07"),
    )
    def test_month_range_filter_matches_production_panel(
        self,
        _mock_sanitize,
        mock_slider,
        _mock_markdown,
    ) -> None:
        result = render_month_range_filter(
            pd.Series(["2026-06-10", "2026-07-13"]),
            key="painting_filter_month_range",
        )

        self.assertEqual(result, (date(2026, 6, 1), date(2026, 7, 31)))
        self.assertEqual(
            mock_slider.call_args.kwargs["key"],
            "painting_filter_month_range",
        )

    def test_painting_code_uses_last_four_digits(self) -> None:
        self.assertEqual(extract_painting_multiplier("26010476"), 476)
        self.assertEqual(extract_painting_multiplier("PINT-0054"), 54)
        self.assertIsNone(extract_painting_multiplier("sem codigo"))

    def test_color_ignores_shipping_direction(self) -> None:
        self.assertEqual(extract_painting_color("ENVIO - VERMELHO"), "VERMELHO")
        self.assertEqual(extract_painting_color("RETORNO - VERMELHO"), "VERMELHO")

    def test_empty_frame_keeps_expected_columns(self) -> None:
        frame, quality = _normalize_painting_frame(pd.DataFrame())

        self.assertTrue(frame.empty)
        self.assertEqual(frame.columns.tolist(), PAINTING_COLUMNS)
        self.assertEqual(quality["warnings"], [])

    def test_normalization_handles_nulls_dates_and_numbers(self) -> None:
        raw = pd.DataFrame(
            {
                "id": [1, 2],
                "data_producao": ["13/07/26", None],
                "numero_display": ["12345678.0", None],
                "quantidade": ["10", None],
                "quantidade_total": ["25", "invalido"],
                "cliente": [" Cliente A ", None],
            }
        )

        frame, _quality = _normalize_painting_frame(raw)

        self.assertEqual(frame.loc[0, "data_producao"], date(2026, 7, 13))
        self.assertIsNone(frame.loc[1, "data_producao"])
        self.assertEqual(frame.loc[0, "numero_display"], "12345678")
        self.assertEqual(frame["quantidade"].tolist(), [10, 0])
        self.assertEqual(frame["quantidade_total"].tolist(), [25, 0])
        self.assertEqual(frame.loc[0, "cliente"], "Cliente A")
        self.assertTrue(pd.isna(frame.loc[1, "cliente"]))

    def test_filters_apply_period_and_all_painting_dimensions(self) -> None:
        frame = pd.DataFrame(
            {
                "data_producao": [date(2026, 7, 10), date(2026, 7, 13)],
                "cliente": ["A", "B"],
                "display": ["D1", "D2"],
                "numero_display": ["100", "200"],
                "codigo_pintura": ["AZUL", "PRETO"],
                "maquinario": ["F1", "F2"],
                "processo": ["P1", "P2"],
            }
        )
        selections = {
            "cliente": ["B"],
            "display": ["D2"],
            "numero_display": ["200"],
            "codigo_pintura": ["PRETO"],
            "maquinario": ["F2"],
            "processo": ["P2"],
        }

        filtered = filter_painting_frame(
            frame,
            date_range=(date(2026, 7, 12), date(2026, 7, 13)),
            selections=selections,
        )

        self.assertEqual(filtered.index.tolist(), [1])

    def test_expected_quantity_is_split_between_send_and_return(self) -> None:
        frame = pd.DataFrame(
            {
                "display": ["DISPLAY ARAMADO G"] * 3,
                "processo": [
                    "ENVIO - VERMELHO",
                    "ENVIO - VERMELHO",
                    "RETORNO - VERMELHO",
                ],
                "codigo_pintura": ["26010476"] * 3,
                "quantidade": [100, 50, 90],
            }
        )
        plans_dir = ROOT / "planilhas_pintura"

        summary = compute_painting_panel_summary(frame, planilhas_dir=plans_dir)

        self.assertEqual(summary.lote_text, "0476")
        self.assertAlmostEqual(summary.total_enviado, 150.0)
        self.assertAlmostEqual(summary.total_retorno, 90.0)
        self.assertAlmostEqual(summary.pendente_enviar, 326.0)
        self.assertAlmostEqual(summary.pendente_retornar, 386.0)

        send_only = compute_painting_panel_summary(
            frame.iloc[:2], planilhas_dir=plans_dir
        )
        self.assertAlmostEqual(send_only.total_retorno, 0.0)
        self.assertAlmostEqual(send_only.pendente_retornar, 476.0)

    def test_image_match_uses_color_for_send_and_return(self) -> None:
        images_dir = ROOT / "FOTOS PINTURA"

        sent = find_painting_image(
            images_dir, "DISPLAY ARAMADO G", "ENVIO - VERMELHO"
        )
        returned = find_painting_image(
            images_dir, "DISPLAY ARAMADO G", "RETORNO - VERMELHO"
        )

        self.assertIsNotNone(sent)
        self.assertEqual(sent, returned)
        self.assertIn("VERMELHO", sent.name)


if __name__ == "__main__":
    unittest.main()
