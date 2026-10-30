"""Tests for action previews and basic executor validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.executor import Executor, describe_action  # noqa: E402


class DescribeActionTests(unittest.TestCase):
    def test_text_action(self):
        text = describe_action(
            {"name": "writer_insert_text", "arguments": {"text": "Hola mundo"}}
        )
        self.assertIn("Insertar texto", text)
        self.assertIn("Hola mundo", text)

    def test_table_action_counts_cells(self):
        text = describe_action(
            {
                "name": "calc_create_table",
                "arguments": {"data": [["A", "B"], ["1", "2"]]},
            }
        )
        self.assertIn("2 filas", text)
        self.assertIn("2 columnas", text)

    def test_unknown_action_uses_name(self):
        self.assertIn("desconocida", describe_action({"name": "desconocida", "arguments": {}}))

    def test_short_text_is_truncated(self):
        text = describe_action(
            {"name": "writer_insert_text", "arguments": {"text": "x" * 200}}
        )
        self.assertLess(len(text), 120)


class ExecutorValidationTests(unittest.TestCase):
    def test_empty_actions_are_ignored(self):
        self.assertEqual(Executor().apply(object(), []), [])

    def test_missing_document_is_rejected(self):
        with self.assertRaises(ValueError):
            Executor().apply(None, [{"name": "writer_insert_text", "arguments": {}}])

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            Executor().apply(object(), [{"name": "nope", "arguments": {}}])


if __name__ == "__main__":
    unittest.main()
