from __future__ import annotations

import unittest

import app


class FilteredUpdateBannerTests(unittest.TestCase):
    def test_banner_identifies_latest_filtered_production(self) -> None:
        builder = getattr(app, "build_last_production_banner", None)
        self.assertTrue(callable(builder), "construtor do indicador superior ausente")

        html = builder("03/09/2026 às 16:27")

        self.assertIn("Última produção lançada", html)
        self.assertIn("03/09/2026 às 16:27", html)


if __name__ == "__main__":
    unittest.main()
