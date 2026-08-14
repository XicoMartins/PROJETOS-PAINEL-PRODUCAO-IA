import unittest
from datetime import date

from dashboard_png import (
    _normalize_projects,
    _summary_columns,
    _summary_values,
    generate_dashboard_png,
)


class DashboardPngSetsTest(unittest.TestCase):
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
