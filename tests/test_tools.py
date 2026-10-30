"""Tests for tool validation and argument parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.tools import TOOLS, TOOLS_BY_NAME, ToolError, parse_arguments  # noqa: E402


class ToolTests(unittest.TestCase):
    def test_tool_names_are_unique(self):
        names = [tool["function"]["name"] for tool in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(TOOLS_BY_NAME))

    def test_parses_json_string(self):
        arguments = parse_arguments("writer_insert_text", '{"text": "Hola"}')
        self.assertEqual(arguments, {"text": "Hola"})

    def test_parses_dict(self):
        arguments = parse_arguments("calc_add_sheet", {"name": "Datos"})
        self.assertEqual(arguments, {"name": "Datos"})

    def test_rejects_unknown_tool(self):
        with self.assertRaises(ToolError):
            parse_arguments("unknown_tool", {})

    def test_rejects_invalid_json(self):
        with self.assertRaises(ToolError):
            parse_arguments("writer_insert_text", "{no json")

    def test_rejects_missing_required_argument(self):
        with self.assertRaises(ToolError):
            parse_arguments("writer_insert_text", {})
        with self.assertRaises(ToolError):
            parse_arguments("writer_insert_text", {"text": ""})

    def test_rejects_non_object_arguments(self):
        with self.assertRaises(ToolError):
            parse_arguments("writer_insert_text", "[]")

    def test_rejects_invalid_enum(self):
        with self.assertRaises(ToolError):
            parse_arguments(
                "writer_insert_text",
                {"text": "Hola", "position": "somewhere"},
            )

    def test_rejects_invalid_type(self):
        with self.assertRaises(ToolError):
            parse_arguments("writer_insert_text", {"text": "Hola", "new_paragraph": "yes"})
        with self.assertRaises(ToolError):
            parse_arguments(
                "calc_write_range",
                {"start_cell": "A1", "values": [["ok", {"bad": 1}]]},
            )

    def test_rejects_unknown_properties(self):
        with self.assertRaises(ToolError):
            parse_arguments("writer_insert_text", {"text": "Hola", "extra": True})

    def test_optional_null_is_ignored(self):
        arguments = parse_arguments(
            "writer_insert_text",
            {"text": "Hola", "style": None, "new_paragraph": None},
        )
        self.assertEqual(arguments["text"], "Hola")


if __name__ == "__main__":
    unittest.main()
