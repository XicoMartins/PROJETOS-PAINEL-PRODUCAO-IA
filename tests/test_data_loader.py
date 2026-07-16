from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_loader import _normalize_loaded_frame


class DataLoaderTests(unittest.TestCase):
    def test_duration_crossing_midnight_is_positive(self) -> None:
        raw = pd.DataFrame(
            {
                "data_producao": ["15/07/26"],
                "hora_inicio": ["23:30"],
                "hora_fim": ["01:00"],
                "quantidade": [10],
                "pecas_mortas": [0],
            }
        )

        normalized, _ = _normalize_loaded_frame(raw)

        self.assertAlmostEqual(normalized.loc[0, "duracao_horas"], 1.5)


if __name__ == "__main__":
    unittest.main()
