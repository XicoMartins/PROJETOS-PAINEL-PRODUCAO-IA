import json
import re
import unittest
from dataclasses import replace
from datetime import datetime
from io import BytesIO
from unittest.mock import patch

from PIL import Image, ImageChops
from pypdf import PdfReader

from dashboard_png import build_dashboard_png
from streamlit_app import build_projects, render_dashboard
from test_project_sets import row
from test_weekly_control_data import SequencedFakeConnection
from test_weekly_report import ID, NOW, source
from weekly_control import build_weekly_control, weekly_periods
from weekly_control_data import load_weekly_source
from weekly_control_view import render_weekly_control_html
from weekly_report import changes, snapshot
from weekly_report_pdf import build_pdf


SUPPLIERS = ("SCHUNCK", "Multipint", "Aquapint", "Multipint")
DISPLAY_ORDER = ["Aquapint", "Multipint", "SCHUNCK"]


def dashboard_rows(suppliers):
    return [
        dict(row("ENVIO BASE PRETO", "Envio à Pintura", 9), fornecedor_pintura=supplier)
        for supplier in suppliers
    ] + [dict(row("ENVIO CORPO PRETO", "Envio à Pintura", 11), fornecedor_pintura=None)]


def weekly_source(suppliers):
    requirements = [
        {
            "source_component_key": key, "display_name": key, "quantity_per_set": 1,
            "display_order": index, "active": True, "updated_at": NOW,
        }
        for index, key in enumerate(("BASE", "CORPO"))
    ]
    entries = [
        {
            "id": index, "processo": "ENVIO BASE", "quantidade": 9,
            "timestamp": NOW, "fornecedor_pintura": supplier,
        }
        for index, supplier in enumerate(suppliers)
    ] + [{"id": 100, "processo": "ENVIO CORPO", "quantidade": 11,
          "timestamp": NOW, "fornecedor_pintura": None}]
    connection = SequencedFakeConnection([[], requirements, entries])
    return load_weekly_source("test", ID, *weekly_periods(NOW), connection=connection)


def supplier_labels(markup):
    return re.findall(r'(?:aria-label="(Aquapint|Multipint)"|>(SCHUNCK)<)', markup)


class PaintingSupplierTest(unittest.TestCase):
    def assert_ordered_suppliers(self, markup):
        self.assertEqual([logo or label for logo, label in supplier_labels(markup)], DISPLAY_ORDER)

    def test_dashboard_assigns_each_supplier_once_to_its_process(self):
        projects, timeline = build_projects(dashboard_rows(SUPPLIERS))
        processes = projects[0].processes
        self.assertEqual([(item.name, item.sent_quantity) for item in processes],
                         [("BASE", 36), ("CORPO", 11)])
        with patch("streamlit_app.st.markdown") as markdown:
            render_dashboard(projects, timeline, 2026, datetime(2026, 8, 1, 8))
        styles, dashboard = (call.args[0] for call in markdown.call_args_list)
        self.assertTrue(styles.startswith("<style>") and styles.endswith("</style>"))
        self.assertTrue(dashboard.lstrip().startswith('<div class="report-shell report-canvas"'))
        rendered = dashboard
        base, corpo = re.findall(r"<tr class='summary-process-row'>(.*?)</tr>", rendered)
        self.assert_ordered_suppliers(base)
        self.assertEqual(supplier_labels(corpo), [])

    def test_dashboard_png_draws_suppliers_in_stable_order_within_the_same_width(self):
        def png(suppliers):
            projects, dates = build_projects(dashboard_rows(suppliers))
            return Image.open(BytesIO(build_dashboard_png(
                projects, dates, [], width=1200, updated_at=datetime(2026, 8, 1, 8, 0)
            ))).convert("RGB")

        branded = png(SUPPLIERS)
        legacy = png((None,) * len(SUPPLIERS))
        reordered = png(tuple(reversed(SUPPLIERS)))
        self.assertEqual(branded.width, legacy.width)
        self.assertIsNone(ImageChops.difference(branded, reordered).getbbox())
        self.assertTrue(branded.size != legacy.size or ImageChops.difference(branded, legacy).getbbox())

    def test_weekly_tables_assign_suppliers_to_each_process_in_both_panels(self):
        data = weekly_source(tuple(reversed(SUPPLIERS)))
        control = build_weekly_control(None, None, data.requirements, data.entries)
        self.assertEqual([row.total_remessa for row in control.components], [36, 11])
        rendered = render_weekly_control_html(ID, *weekly_periods(NOW), control, NOW)
        for base in re.findall(r'<th scope="row">BASE(.*?)</th>', rendered):
            self.assert_ordered_suppliers(base)
        self.assertEqual(len(re.findall(r'<th scope="row">BASE(.*?)</th>', rendered)), 2)
        self.assertEqual(rendered.count('<th scope="row">CORPO</th>'), 2)
        self.assertEqual(len(supplier_labels(rendered)), 6)

    def test_null_supplier_matches_checkpoint_created_before_the_column(self):
        legacy_row = {"id": 1, "processo": "ENVIO CORPO"}
        saved = json.loads(json.dumps(snapshot(ID, replace(source(), source_entries=(legacy_row,)))))
        current = snapshot(ID, replace(source(), source_entries=(
            dict(legacy_row, fornecedor_pintura=None),
        )))
        self.assertEqual(current, saved)
        self.assertNotIn("painting_suppliers", current["rows"]["component:CORPO"])

    def test_supplier_edit_is_reported_even_when_totals_and_supplier_set_match(self):
        before = snapshot(ID, weekly_source(("Multipint", "Aquapint", "Multipint")))
        after = snapshot(ID, weekly_source(("Aquapint", "Aquapint", "Multipint")))
        result = changes(after, before)
        self.assertEqual([item["key"] for item in result], ["component:BASE"])
        self.assertEqual(result[0]["deltas"]["total_remessa"], "0")
        self.assertEqual(result[0]["current"].get("painting_suppliers"), ["Aquapint", "Multipint"])

    def test_weekly_pdf_embeds_process_logos_and_renders_schunck_as_text(self):
        def page(suppliers):
            snap = snapshot(ID, weekly_source(suppliers))
            report = {"snapshot": snap, "previous_at": None, "rows": changes(snap, None)}
            return PdfReader(BytesIO(build_pdf([report], NOW))).pages[0]

        branded = page(SUPPLIERS)
        self.assertEqual(branded.extract_text().count("SCHUNCK"), 2)
        self.assertEqual(len(branded.images), 3)
        images = branded["/Resources"]["/XObject"]
        operations = branded.get_contents().operations
        for index, (operands, operator) in enumerate(operations):
            if operator == b"Do":
                image = images[operands[0]]
                drawn_width, _, _, drawn_height, _, _ = operations[index - 1][0]
                self.assertLessEqual(drawn_width, 65)
                self.assertAlmostEqual(drawn_width / drawn_height,
                                       image["/Width"] / image["/Height"], places=4)
        legacy = page((None,) * len(SUPPLIERS))
        self.assertNotIn("SCHUNCK", legacy.extract_text())
        self.assertEqual(len(legacy.images), 1)


if __name__ == "__main__":
    unittest.main()
