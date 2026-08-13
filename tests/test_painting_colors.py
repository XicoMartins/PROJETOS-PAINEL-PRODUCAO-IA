import unittest

from painting_colors import painting_code_parts


class PaintingCodePartsTest(unittest.TestCase):
    def test_maps_known_abbreviation_and_removes_lot_padding(self):
        self.assertEqual(painting_code_parts("VM - 0010"), ("VM", "VERMELHO", "10"))

    def test_accepts_compact_code(self):
        self.assertEqual(painting_code_parts("PR0185"), ("PR", "PRETO", "185"))

    def test_flags_unknown_abbreviation(self):
        self.assertEqual(painting_code_parts("CZ - 0025"), ("CZ", "COR NÃO CADASTRADA (CZ)", "25"))

    def test_keeps_legacy_numeric_code_visible(self):
        self.assertEqual(painting_code_parts("0010"), ("", "SEM COR", "10"))


if __name__ == "__main__":
    unittest.main()
