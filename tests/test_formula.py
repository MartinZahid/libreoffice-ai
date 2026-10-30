"""Tests for the formula safety filter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.formula import validate_formula  # noqa: E402


class FormulaTests(unittest.TestCase):
    def test_allows_normal_formulas(self):
        validate_formula("=SUM(A1:A3)")
        validate_formula("=IF(A1>0;\"sí\";\"no\")")
        validate_formula("texto normal")

    def test_blocks_external_functions(self):
        for formula in (
            "=WEBSERVICE(\"https://example.com\")",
            "=HYPERLINK(\"https://example.com\";\"x\")",
            "=IMPORTXML(\"https://example.com\";\"//x\")",
            "=IMPORTHTML(\"https://example.com\";\"table\";1)",
            "=IMPORTDATA(\"https://example.com\")",
            "=IMPORTFEED(\"https://example.com\")",
            "=DDE(\"soffice\";\"a\";\"b\")",
            "=RTD(\"x\";\"y\")",
        ):
            with self.subTest(formula=formula):
                with self.assertRaises(ValueError):
                    validate_formula(formula)

    def test_is_case_insensitive(self):
        with self.assertRaises(ValueError):
            validate_formula("=webservice(\"https://example.com\")")


if __name__ == "__main__":
    unittest.main()
