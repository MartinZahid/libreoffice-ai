"""Tests for shared adapter helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.adapters.common import (  # noqa: E402
    as_int,
    bounded_float,
    cell_name,
    cm_to_100mm,
    coerce_bool,
    column_letters,
    document_kind,
    first_selection_range,
    parse_cell,
    parse_color,
    parse_range,
    selection_text,
    validate_image_path,
)


class FakeText:
    def __init__(self, text):
        self._text = text

    def getString(self):
        return self._text


class FakeSelection:
    def __init__(self, texts):
        self._texts = texts

    def getCount(self):
        return len(self._texts)

    def getByIndex(self, index):
        return FakeText(self._texts[index])


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

    def test_numbers_are_validated(self):
        self.assertEqual(as_int(None, 7), 7)
        self.assertEqual(as_int("3", 1), 3)
        with self.assertRaises(ValueError):
            as_int("tres", 1)
        self.assertEqual(bounded_float(None, 2.0, 1.0, 3.0, "Valor"), 2.0)
        with self.assertRaises(ValueError):
            bounded_float("9", 2.0, 1.0, 3.0, "Valor")

    def test_selection_helpers_support_index_access(self):
        index_access = FakeSelection(["uno", "dos"])
        self.assertEqual(selection_text(index_access), "uno\ndos")
        self.assertEqual(first_selection_range(index_access).getString(), "uno")
        direct = FakeText("texto")
        self.assertIs(first_selection_range(direct), direct)

    def test_document_kind(self):
        class Doc:
            def __init__(self, service):
                self.service = service

            def supportsService(self, service):
                return service == self.service

        self.assertEqual(
            document_kind(Doc("com.sun.star.text.TextDocument")), "writer"
        )
        self.assertEqual(
            document_kind(Doc("com.sun.star.sheet.SpreadsheetDocument")), "calc"
        )
        self.assertEqual(document_kind(Doc("unknown")), "unknown")

    def test_image_path_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "foto.PNG"
            image.write_bytes(b"not-a-real-image")
            self.assertEqual(validate_image_path(str(image)), str(image.resolve()))
            with self.assertRaises(ValueError):
                validate_image_path("relative.png")
            with self.assertRaises(ValueError):
                validate_image_path(r"\\server\share\foto.png")
            with self.assertRaises(ValueError):
                validate_image_path("https://example.com/foto.png")
            text = Path(directory) / "nota.txt"
            text.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_image_path(str(text))

    def test_image_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "grande.png"
            with open(image, "wb") as handle:
                handle.truncate(20 * 1024 * 1024 + 1)
            with self.assertRaises(ValueError):
                validate_image_path(str(image))


if __name__ == "__main__":
    unittest.main()
