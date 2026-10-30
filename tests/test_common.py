"""Tests for shared adapter helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.adapters.common import (  # noqa: E402
    cell_name,
    cm_to_100mm,
    coerce_bool,
    column_letters,
    parse_cell,
    parse_color,
    parse_range,
)


class CommonHelperTests(unittest.TestCase):
    def test_column_letters(self):
        self.assertEqual(column_letters(0), "A")
        self.assertEqual(column_letters(25), "Z")
        self.assertEqual(column_letters(26), "AA")
        self.assertEqual(cell_name(1, 2), "B3")

    def test_parse_cell(self):
        self.assertEqual(parse_cell("A1"), (0, 0))
        self.assertEqual(parse_cell("$B$3"), (1, 2))
        with self.assertRaises(ValueError):
            parse_cell("1A")

    def test_parse_range(self):
        self.assertEqual(parse_range("a1:b2"), ("A1", "B2"))
        self.assertEqual(parse_range("C3"), ("C3", "C3"))

    def test_color(self):
        self.assertEqual(parse_color("#FF0000"), 0xFF0000)
        self.assertEqual(parse_color("00ff00"), 0x00FF00)
        with self.assertRaises(ValueError):
            parse_color("rojo")

    def test_bool_and_measure(self):
        self.assertTrue(coerce_bool("sí"))
        self.assertTrue(coerce_bool("true"))
        self.assertFalse(coerce_bool("no"))
        self.assertEqual(cm_to_100mm(2.5), 2500)


if __name__ == "__main__":
    unittest.main()
