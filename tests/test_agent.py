"""Tests for the agent loop using a fake LLM client."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.agent import Agent  # noqa: E402


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, tools=None, tool_choice="auto"):
        self.calls.append(copy.deepcopy(messages))
        if not self.responses:
            raise AssertionError("Unexpected extra LLM call")
        return self.responses.pop(0)


class AgentTests(unittest.TestCase):
    def test_tool_call_becomes_pending_action(self):
        client = FakeClient(
            [
                {
                    "content": "Preparando el cambio.",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "writer_insert_text",
                                "arguments": '{"text": "Hola mundo"}',
                            },
                        }
                    ],
                },
                {"content": "Listo, revisa la propuesta."},
            ]
        )
        result = Agent(client).run("Escribe hola mundo", "Documento Writer")
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(result.actions[0]["name"], "writer_insert_text")
        self.assertEqual(result.actions[0]["arguments"]["text"], "Hola mundo")
        self.assertIn("revisa", result.text.lower())
        self.assertEqual(len(client.calls), 2)
        tool_messages = [m for m in client.calls[1] if m.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0]["tool_call_id"], "call_1")

    def test_fallback_json_block_is_parsed(self):
        content = (
            "Puedo hacerlo.\n"
            "```json\n"
            '{"actions": [{"name": "calc_add_sheet", "arguments": {"name": "Resumen"}}]}\n'
            "```\n"
            "Pulsa Aplicar."
        )
        client = FakeClient([{"content": content}])
        result = Agent(client).run("Añade una hoja", "Documento Calc")
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(result.actions[0]["name"], "calc_add_sheet")
        self.assertNotIn("```", result.text)

    def test_plain_answer_has_no_actions(self):
        client = FakeClient([{"content": "Necesito que me indiques el texto."}])
        result = Agent(client).run("Mejora esto")
        self.assertEqual(result.actions, [])
        self.assertIn("Necesito", result.text)

    def test_invalid_tool_arguments_are_reported(self):
        client = FakeClient(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_bad",
                            "type": "function",
                            "function": {
                                "name": "writer_insert_text",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                {"content": "No pude preparar el cambio."},
            ]
        )
        result = Agent(client).run("Escribe algo")
        self.assertEqual(result.actions, [])
        self.assertTrue(result.errors)
        tool_messages = [m for m in client.calls[1] if m.get("role") == "tool"]
        self.assertIn("error", tool_messages[0]["content"])

    def test_document_context_is_not_persisted(self):
        client = FakeClient([{"content": "Hecho."}])
        agent = Agent(client)
        agent.run("Mejora esto", "Documento Writer con datos privados")
        user_message = next(m for m in agent.messages if m.get("role") == "user")
        self.assertEqual(user_message["content"], "Mejora esto")
        self.assertNotIn("datos privados", str(agent.messages))

    def test_resolve_pending_marks_tool_result(self):
        client = FakeClient(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "writer_insert_text",
                                "arguments": '{"text": "Hola"}',
                            },
                        }
                    ],
                },
                {"content": "Listo."},
            ]
        )
        agent = Agent(client)
        agent.run("Escribe hola")
        agent.resolve_pending(False, "El usuario rechazó el cambio.")
        tool_message = next(m for m in agent.messages if m.get("role") == "tool")
        payload = json.loads(tool_message["content"])
        self.assertEqual(payload["status"], "rejected")
        self.assertIn("rechazó", payload["message"])

    def test_tool_round_limit_is_reported(self):
        responses = []
        for index in range(6):
            responses.append(
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": "calc_add_sheet",
                                "arguments": json.dumps({"name": f"Hoja{index}"}),
                            },
                        }
                    ],
                }
            )
        client = FakeClient(responses)
        result = Agent(client).run("Añade hojas")
        self.assertEqual(len(result.actions), 6)
        self.assertTrue(any("límite" in error.lower() for error in result.errors))

    def test_generates_ids_when_provider_omits_them(self):
        client = FakeClient(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "calc_add_sheet",
                                "arguments": '{"name": "Hoja"}',
                            }
                        }
                    ],
                },
                {"content": "Listo."},
            ]
        )
        result = Agent(client).run("Añade hoja")
        self.assertEqual(len(result.actions), 1)
        generated_id = result.actions[0]["id"]
        self.assertTrue(generated_id)
        tool_messages = [m for m in client.calls[1] if m.get("role") == "tool"]
        self.assertEqual(tool_messages[0]["tool_call_id"], generated_id)


if __name__ == "__main__":
    unittest.main()
