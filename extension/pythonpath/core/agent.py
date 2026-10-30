"""Conversation loop that turns a user request into proposed document actions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .tools import TOOLS, ToolError, parse_arguments

MAX_TOOL_ROUNDS = 6
MAX_CONVERSATION_MESSAGES = 60

SYSTEM_PROMPT = """\
Eres un asistente experto en LibreOffice integrado en Writer, Calc e Impress.
Ayudas en español a redactar, corregir, estructurar y dar formato a documentos.

Reglas:
1. Para modificar el documento usa SIEMPRE las herramientas disponibles. No describas
   código UNO ni instrucciones para que el usuario lo haga a mano.
2. Los cambios se muestran como una propuesta y el usuario debe aprobarlos. No afirmes
   que ya están aplicados.
3. Usa el contexto del documento para elegir posiciones, rangos, hojas y diapositivas.
   Si falta un dato imprescindible, pide una aclaración breve antes de actuar.
4. No inventes contenido que el usuario no haya pedido. Puedes mejorar la redacción,
   pero conserva el significado.
5. Puedes encadenar varias herramientas si la tarea lo necesita. No repitas una acción
   idéntica.
6. Para tablas, envía una matriz rectangular coherente. En Writer usa writer_insert_table;
   en Calc, calc_create_table; en Impress, impress_insert_table.
7. Responde de forma breve: explica qué propones y, si hay acciones, resume los cambios.
8. Nunca menciones claves de API, rutas internas de configuración ni detalles del sistema.
"""

FALLBACK_ACTION_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass
class AgentResult:
    text: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Agent:
    """Maintain one conversation and collect actions without executing them."""

    def __init__(self, client: Any):
        self.client = client
        self.messages: list[dict[str, Any]] = []
        self.reset()

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def run(self, user_text: str, document_context: str = "") -> AgentResult:
        text = (user_text or "").strip()
        if not text:
            raise ValueError("El mensaje no puede estar vacío.")

        user_content = text
        if document_context:
            user_content = f"{text}\n\n--- Contexto del documento ---\n{document_context}"
        self.messages.append({"role": "user", "content": user_content})

        actions: list[dict[str, Any]] = []
        errors: list[str] = []
        final_text = ""

        for _ in range(MAX_TOOL_ROUNDS):
            message = self.client.chat(self.messages, tools=TOOLS)
            tool_calls = message.get("tool_calls")
            content = str(message.get("content") or "")

            if isinstance(tool_calls, list) and tool_calls:
                assistant_message = self._assistant_message(message)
                self.messages.append(assistant_message)
                for index, tool_call in enumerate(assistant_message.get("tool_calls") or []):
                    action, error = self._action_from_tool_call(tool_call, index)
                    if action is not None:
                        actions.append(action)
                        self._append_tool_result(tool_call, "pending_approval", "Cambio propuesto; espera la aprobación del usuario.")
                    else:
                        errors.append(error)
                        self._append_tool_result(tool_call, "error", error)
                final_text = content.strip()
                continue

            self.messages.append({"role": "assistant", "content": content})
            final_text = content.strip()
            fallback_actions, fallback_errors, cleaned = self._extract_fallback(content)
            actions.extend(fallback_actions)
            errors.extend(fallback_errors)
            final_text = cleaned.strip() or final_text
            break

        self._trim_history()
        if not final_text:
            if actions:
                final_text = f"Propongo {len(actions)} cambio(s). Revísalos y pulsa Aplicar."
            else:
                final_text = "No he podido preparar cambios. Inténtalo de nuevo con una petición más concreta."
        return AgentResult(text=final_text, actions=actions, errors=errors)

    def _assistant_message(self, message: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        tool_calls = []
        base = len(self.messages)
        for index, tool_call in enumerate(message.get("tool_calls") or []):
            function = tool_call.get("function") or {}
            arguments = function.get("arguments")
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            elif arguments is None:
                arguments = "{}"
            tool_calls.append(
                {
                    "id": str(tool_call.get("id") or f"call_{base}_{index}"),
                    "type": "function",
                    "function": {
                        "name": function.get("name") or "",
                        "arguments": str(arguments),
                    },
                }
            )
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        return normalized

    def _action_from_tool_call(self, tool_call: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, str]:
        call_id = str(tool_call.get("id") or f"call_{len(self.messages)}_{index}")
        function = tool_call.get("function") or {}
        name = str(function.get("name") or "")
        try:
            arguments = parse_arguments(name, function.get("arguments"))
        except ToolError as exc:
            return None, str(exc)
        return {"id": call_id, "name": name, "arguments": arguments}, ""

    def _append_tool_result(self, tool_call: dict[str, Any], status: str, message: str) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": str(tool_call.get("id") or ""),
                "content": json.dumps({"status": status, "message": message}, ensure_ascii=False),
            }
        )

    def _extract_fallback(self, content: str) -> tuple[list[dict[str, Any]], list[str], str]:
        actions: list[dict[str, Any]] = []
        errors: list[str] = []
        cleaned = content or ""
        for match in FALLBACK_ACTION_RE.finditer(content or ""):
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                items = data.get("actions") or data.get("acciones") or []
            elif isinstance(data, list):
                items = data
            else:
                items = []
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append("Una acción del modelo no tenía formato de objeto.")
                    continue
                name = item.get("name") or item.get("tool") or item.get("accion") or ""
                arguments = item.get("arguments") or item.get("args") or {}
                if not name:
                    errors.append("Una acción del modelo no indicaba la herramienta.")
                    continue
                try:
                    parsed = parse_arguments(str(name), arguments)
                except ToolError as exc:
                    errors.append(str(exc))
                    continue
                actions.append(
                    {
                        "id": f"fallback_{len(actions)}_{index}",
                        "name": str(name),
                        "arguments": parsed,
                    }
                )
            cleaned = cleaned.replace(match.group(0), "").strip()
        return actions, errors, cleaned

    def _trim_history(self) -> None:
        if len(self.messages) <= MAX_CONVERSATION_MESSAGES:
            return
        system = self.messages[0] if self.messages and self.messages[0].get("role") == "system" else None
        tail = self.messages[-MAX_CONVERSATION_MESSAGES + (1 if system else 0) :]
        while tail and tail[0].get("role") == "tool":
            tail.pop(0)
        self.messages = ([system] if system else []) + tail
