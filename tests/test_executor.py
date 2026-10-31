"""Tests for action previews and basic executor validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.executor import Executor, describe_action  # noqa: E402


class FakeUndo:
    def __init__(self, titles=None, fail_undo=False):
        self.titles = list(titles or [])
        self.fail_undo = fail_undo
        self.entered = []
        self.leaves = 0
        self.undos = 0

    def enterUndoContext(self, title):
        self.entered.append(title)

    def leaveUndoContext(self):
        self.leaves += 1
        self.titles.append(Executor.PREVIEW_TITLE)

    def getAllUndoActionTitles(self):
        return tuple(self.titles)

    def undo(self):
        if self.fail_undo:
            raise RuntimeError("undo failed")
        if self.titles:
            self.titles.pop()
        self.undos += 1


class FakeDoc:
    def __init__(self, undo):
        self.undo = undo

    def getUndoManager(self):
        return self.undo


class FakeAdapter:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.executed = []

    def execute(self, action):
        if self.fail_on == action["name"]:
            raise RuntimeError("action failed")
        self.executed.append(action["name"])


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

    def test_apply_groups_actions_in_one_undo_context(self):
        undo = FakeUndo()
        adapter = FakeAdapter()
        actions = [
            {"name": "writer_insert_text", "arguments": {"text": "uno"}},
            {"name": "writer_insert_text", "arguments": {"text": "dos"}},
        ]
        with patch("core.executor._adapter_for", return_value=adapter):
            descriptions = Executor().apply(FakeDoc(undo), actions)
        self.assertEqual(adapter.executed, ["writer_insert_text", "writer_insert_text"])
        self.assertEqual(undo.entered, [Executor.PREVIEW_TITLE])
        self.assertEqual(undo.leaves, 1)
        self.assertEqual(len(descriptions), 2)

    def test_apply_records_preview_for_revert(self):
        undo = FakeUndo()
        adapter = FakeAdapter()
        executor = Executor()
        doc = FakeDoc(undo)
        with patch("core.executor._adapter_for", return_value=adapter):
            executor.apply(doc, [{"name": "writer_insert_text", "arguments": {"text": "x"}}])
        self.assertTrue(executor.can_revert)
        executor.revert(doc)
        self.assertEqual(undo.undos, 1)
        self.assertFalse(executor.can_revert)

    def test_none_arguments_are_not_mutated(self):
        undo = FakeUndo()
        adapter = FakeAdapter()
        action = {"name": "writer_insert_page_break", "arguments": None}
        with patch("core.executor._adapter_for", return_value=adapter):
            Executor().apply(FakeDoc(undo), [action])
        self.assertIsNone(action["arguments"])
        self.assertEqual(adapter.executed, ["writer_insert_page_break"])

    def test_failure_rolls_back_the_group(self):
        undo = FakeUndo()
        adapter = FakeAdapter(fail_on="writer_format")
        with patch("core.executor._adapter_for", return_value=adapter):
            with self.assertRaises(RuntimeError):
                Executor().apply(
                    FakeDoc(undo),
                    [
                        {"name": "writer_insert_text", "arguments": {"text": "x"}},
                        {"name": "writer_format", "arguments": {"bold": True}},
                    ],
                )
        self.assertEqual(adapter.executed, ["writer_insert_text"])
        self.assertEqual(undo.leaves, 1)
        self.assertEqual(undo.undos, 1)

    def test_no_undo_when_nothing_was_applied(self):
        undo = FakeUndo()
        adapter = FakeAdapter(fail_on="writer_insert_text")
        with patch("core.executor._adapter_for", return_value=adapter):
            with self.assertRaises(RuntimeError):
                Executor().apply(
                    FakeDoc(undo),
                    [{"name": "writer_insert_text", "arguments": {"text": "x"}}],
                )
        self.assertEqual(undo.leaves, 1)
        self.assertEqual(undo.undos, 0)

    def test_failed_rollback_is_reported(self):
        undo = FakeUndo(fail_undo=True)
        adapter = FakeAdapter(fail_on="writer_format")
        with patch("core.executor._adapter_for", return_value=adapter):
            with self.assertRaisesRegex(ValueError, "parcialmente"):
                Executor().apply(
                    FakeDoc(undo),
                    [
                        {"name": "writer_insert_text", "arguments": {"text": "x"}},
                        {"name": "writer_format", "arguments": {"bold": True}},
                    ],
                )

    def test_revert_refuses_to_undo_later_edits(self):
        undo = FakeUndo()
        adapter = FakeAdapter()
        executor = Executor()
        doc = FakeDoc(undo)
        with patch("core.executor._adapter_for", return_value=adapter):
            executor.apply(doc, [{"name": "writer_insert_text", "arguments": {"text": "x"}}])
        undo.titles.append("Escritura del usuario")
        with self.assertRaises(ValueError):
            executor.revert(doc)
        self.assertEqual(undo.undos, 0)

    def test_revert_requires_a_registered_preview(self):
        undo = FakeUndo()
        with self.assertRaises(ValueError):
            Executor().revert(FakeDoc(undo))
        self.assertEqual(undo.undos, 0)

    def test_revert_requires_the_same_document(self):
        undo = FakeUndo()
        adapter = FakeAdapter()
        executor = Executor()
        with patch("core.executor._adapter_for", return_value=adapter):
            executor.apply(FakeDoc(undo), [{"name": "writer_insert_text", "arguments": {"text": "x"}}])
        with self.assertRaises(ValueError):
            executor.revert(FakeDoc(undo))
        self.assertEqual(undo.undos, 0)

    def test_formula_is_shown_in_preview(self):
        text = describe_action(
            {
                "name": "calc_write_range",
                "arguments": {
                    "start_cell": "A1",
                    "values": [["=SUM(B1:B3)"]],
                },
            }
        )
        self.assertIn("=SUM(B1:B3)", text)


if __name__ == "__main__":
    unittest.main()
