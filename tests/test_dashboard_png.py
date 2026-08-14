import unittest
from datetime import date

from PIL import Image, ImageDraw

from dashboard_png import (
    FONTS,
    _insight_text_layout,
    _normalize_projects,
    _summary_columns,
    _summary_values,
    generate_dashboard_png,
)
from streamlit_app import _reference_png_insights


class DashboardPngSetsTest(unittest.TestCase):
    def test_bounds_multiple_reference_warnings_inside_fixed_insight_rows(self):
        warnings = tuple(
            f"DISPLAY TESTE PRETO 1 / PROCESSO {index}: QNT de retorno ausente"
            for index in range(1, 7)
        )

        insights = _reference_png_insights(warnings)

        self.assertEqual([item[2] for item in insights[:4]], list(warnings[:4]))
        self.assertEqual(
            insights[4],
            ("⚠", "Referências de conjuntos", "Mais 2 avisos de referência."),
        )

        draw = ImageDraw.Draw(Image.new("RGB", (400, 100), "white"))
        text = "Referências de conjuntos: " + warnings[0] * 3
        layout = _insight_text_layout(draw, text, FONTS.get(12), 250, 54)

        self.assertEqual(len(layout), 3)
        self.assertLessEqual(layout[-1][1] + 15, 50)
        self.assertTrue(layout[-1][0].endswith("…"))

    def test_normalizes_and_places_set_counts_in_summary(self):
        projects = _normalize_projects([{
            "name": "DISPLAY",
            "sent_sets": 2,
            "returned_sets": 1,
            "total_sent_quantity": 9,
            "total_returned_quantity": 8,
            "processes": [{
                "name": "BASE",
                "sent_quantity": 9,
                "returned_quantity": 8,
                "sent_sets": 2,
                "returned_sets": 2,
            }],
        }])

        labels = [label for label, _ in _summary_columns(True)]
        values = _summary_values("display", projects[0], True)

        self.assertEqual(labels[2:6], ["Env. total", "Conj. env.", "Ret. total", "Conj. ret."])
        self.assertEqual(values[2:6], ["9,0", "2", "8,0", "1"])
        self.assertEqual(projects[0].processes[0].sent_sets, 2)

    def test_generates_png_with_set_columns(self):
        png = generate_dashboard_png(
            metrics=[],
            projects=[{
                "name": "DISPLAY",
                "sent_dates": [date(2026, 8, 1)],
                "return_dates": [date(2026, 8, 2)],
                "sent_sets": 2,
                "returned_sets": 1,
                "sent_quantity": 9,
                "returned_quantity": 8,
                "total_sent_quantity": 9,
                "total_returned_quantity": 8,
                "processes": [{
                    "name": "BASE",
                    "sent_quantity": 9,
                    "returned_quantity": 8,
                    "sent_sets": 2,
                    "returned_sets": 2,
                }],
            }],
            timeline_dates=[date(2026, 8, 1), date(2026, 8, 2)],
            insights=[{"title": "Referências", "text": "arquivo sem QNT", "kind": "warning"}],
            width=1280,
        )

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 10_000)


if __name__ == "__main__":
    unittest.main()
