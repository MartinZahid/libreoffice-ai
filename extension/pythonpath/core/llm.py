"""Small OpenAI-compatible client using only the Python standard library."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from .config import Config


class LLMError(RuntimeError):
    """A user-facing error raised while talking to the model provider."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        data = self._request("POST", "/chat/completions", payload)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("El proveedor devolvió una respuesta sin resultados.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMError("El proveedor devolvió un mensaje con formato inesperado.")
        return message

    def list_models(self) -> list[str]:
        data = self._request("GET", "/models", None)
        entries = data.get("data")
        if not isinstance(entries, list):
            return []
        models = []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id"):
                models.append(str(entry["id"]))
        return sorted(models)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        config = self.config.require_api_key()
        url = self.base_url + path
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + config.api_key,
            "User-Agent": "LibreOffice-AI/1.0",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = self._read_error(exc)
            raise LLMError(self._http_message(exc.code, detail), status=exc.code) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, socket.timeout):
                raise LLMError("La petición tardó demasiado. Revisa tu conexión o aumenta el tiempo de espera.") from exc
            raise LLMError(f"No se pudo conectar con el proveedor: {reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMError("La petición tardó demasiado. Revisa tu conexión o aumenta el tiempo de espera.") from exc

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMError("El proveedor devolvió una respuesta que no es JSON válido.") from exc
        if not isinstance(parsed, dict):
            raise LLMError("El proveedor devolvió una respuesta con formato inesperado.")
        return parsed

    @staticmethod
    def _read_error(exc: urllib.error.HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            return ""
        try:
            data = json.loads(raw)
            error = data.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or "")
            if error:
                return str(error)
            if isinstance(data.get("message"), str):
                return data["message"]
        except (ValueError, AttributeError):
            pass
        return raw[:500].strip()

    @staticmethod
    def _http_message(status: int, detail: str) -> str:
        suffix = f" Detalle: {detail}" if detail else ""
        if status == 401:
            return "Clave de API inválida o no autorizada. Revísala en Ajustes." + suffix
        if status == 403:
            return "El proveedor denegó el acceso. Comprueba tu suscripción o permisos." + suffix
        if status == 404:
            return "No se encontró el endpoint o el modelo. Revisa la URL base y el modelo en Ajustes." + suffix
        if status == 429:
            return "Demasiadas peticiones o límite de uso alcanzado. Espera un momento e inténtalo de nuevo." + suffix
        if status >= 500:
            return "El proveedor tuvo un error interno. Inténtalo de nuevo más tarde." + suffix
        return f"Error HTTP {status} del proveedor.{suffix}"
