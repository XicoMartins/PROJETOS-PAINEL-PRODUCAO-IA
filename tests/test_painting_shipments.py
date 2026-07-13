from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_loader import PAINTING_COLUMNS, _normalize_painting_frame
from painting_filters import filter_painting_frame


class PaintingShipmentsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
