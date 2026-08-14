import tempfile
import time
import unittest
from pathlib import Path

from openpyxl import Workbook

from painting_references import (
    complete_sets,
    load_reference_catalog,
    reference_key,
    scan_reference_directory,
)


def write_book(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


class PaintingReferencesTest(unittest.TestCase):
    def test_reads_qnt_by_header_in_columns_d_and_e(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "ilha.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT", "QNT TOTAL"],
                ["ILHA", "Envio à Pintura", "CORPO - PRETO - ENVIO", 4, 36],
            ])
            write_book(root / "slim.xlsx", [
                ["CLIENTE", "ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["SOLAR", "RACK SLIM", "Retorno da Pintura", "Corpo - Preto", 1],
            ])

            catalog = load_reference_catalog(scan_reference_directory(root))

            self.assertEqual(catalog.quantities[reference_key("ILHA", "CORPO", "remessa")], 4)
            self.assertEqual(catalog.quantities[reference_key("RACK SLIM", "CORPO", "retorno")], 1)

    def test_ignores_excel_temporary_files_and_signature_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "display.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["DISPLAY", "Envio", "CORPO", 1],
            ])
            (root / "~$display.xlsx").write_bytes(b"locked")
            first = scan_reference_directory(root)
            time.sleep(0.01)
            write_book(root / "novo.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["NOVO", "Retorno", "BASE", 2],
            ])
            second = scan_reference_directory(root)

            self.assertEqual([item.name for item in first.files], ["display.xlsx"])
            self.assertNotEqual(first.files, second.files)

    def test_keeps_valid_files_when_another_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "valido.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["DISPLAY", "Envio", "BASE", 2],
            ])
            (root / "quebrado.xlsx").write_bytes(b"not an xlsx")

            catalog = load_reference_catalog(scan_reference_directory(root))

            self.assertEqual(catalog.quantities[reference_key("DISPLAY", "BASE", "remessa")], 2)
            self.assertTrue(any("quebrado.xlsx" in warning for warning in catalog.warnings))

    def test_rejects_invalid_and_conflicting_qnt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_book(root / "conflito.xlsx", [
                ["ACABADO", "FERRAMENTAL", "PROCESSO", "QNT"],
                ["DISPLAY", "Envio", "BASE", 2],
                ["DISPLAY", "Envio", "BASE", 3],
                ["DISPLAY", "Retorno", "CORPO", 0],
            ])

            catalog = load_reference_catalog(scan_reference_directory(root))

            self.assertNotIn(reference_key("DISPLAY", "BASE", "remessa"), catalog.quantities)
            self.assertNotIn(reference_key("DISPLAY", "CORPO", "retorno"), catalog.quantities)
            self.assertGreaterEqual(len(catalog.warnings), 2)

    def test_normalizes_accents_movements_colors_and_floors_sets(self):
        self.assertEqual(
            reference_key("PG + ECONOMIA HÍBRIDO", "Corpo - Preto - Retorno", "retorno"),
            reference_key("PG + ECONOMIA HIBRIDO", "CORPO", "retorno"),
        )
        self.assertEqual(complete_sets(9, 4), 2)
        self.assertEqual(complete_sets(0, 4), 0)
        self.assertIsNone(complete_sets(9, None))


if __name__ == "__main__":
    unittest.main()
