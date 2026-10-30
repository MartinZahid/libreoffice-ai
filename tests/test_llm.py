"""Tests for the HTTP client headers used by OpenCode."""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.config import Config  # noqa: E402
from core.llm import (  # noqa: E402
    LLMClient,
    LLMError,
    MAX_RESPONSE_BYTES,
    _SafeRedirectHandler,
)
from core.version import USER_AGENT  # noqa: E402


def response(content: str = "ok") -> io.BytesIO:
    payload = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def headers(request) -> dict[str, str]:
    return {key.lower(): value for key, value in request.header_items()}


class LLMClientTests(unittest.TestCase):
    def test_sends_opencode_session_header(self):
        config = Config(api_key="test-key")
        client = LLMClient(config, session_id="ses_test")
        with patch("core.llm._open_request", return_value=response()) as request:
            client.chat([{"role": "user", "content": "hola"}])
        sent = request.call_args.args[0]
        self.assertEqual(
            headers(sent)["x-opencode-session"],
            "ses_test",
        )
        self.assertEqual(
            headers(sent)["user-agent"],
            USER_AGENT,
        )
        self.assertTrue(sent.full_url.endswith("/chat/completions"))

    def test_models_endpoint_uses_inference_v1_path(self):
        config = Config(api_key="test-key")
        client = LLMClient(config, session_id="ses_test")
        payload = {"data": [{"id": "deepseek-v4.1-flash"}]}
        with patch(
            "core.llm._open_request",
            return_value=io.BytesIO(json.dumps(payload).encode("utf-8")),
        ) as request:
            models = client.list_models()
        sent = request.call_args.args[0]
        self.assertEqual(models, ["deepseek-v4.1-flash"])
        self.assertEqual(
            sent.full_url,
            "https://opencode.ai/inference/go/v1/models",
        )

    def test_session_is_stable_within_a_client(self):
        client = LLMClient(Config(api_key="test-key"))
        self.assertTrue(client.session_id.startswith("ses_"))
        with patch(
            "core.llm._open_request",
            side_effect=[response("one"), response("two")],
        ) as request:
            client.chat([{"role": "user", "content": "hola"}])
            client.chat([{"role": "user", "content": "otra"}])
        sessions = [
            headers(call.args[0])["x-opencode-session"]
            for call in request.call_args_list
        ]
        self.assertEqual(sessions, [client.session_id, client.session_id])

    def test_malformed_choices_are_rejected(self):
        client = LLMClient(Config(api_key="test-key"))
        with patch(
            "core.llm._open_request",
            return_value=io.BytesIO(b'{"choices": [null]}'),
        ):
            with self.assertRaises(LLMError):
                client.chat([{"role": "user", "content": "hola"}])

    def test_large_response_is_rejected(self):
        client = LLMClient(Config(api_key="test-key"))
        with patch(
            "core.llm._open_request",
            return_value=io.BytesIO(b"x" * (MAX_RESPONSE_BYTES + 1)),
        ):
            with self.assertRaises(LLMError):
                client.chat([{"role": "user", "content": "hola"}])

    def test_http_errors_are_friendly(self):
        self.assertIn("Clave", LLMClient._http_message(401, ""))
        self.assertIn("modelo", LLMClient._http_message(404, ""))
        self.assertIn("límite", LLMClient._http_message(429, ""))
        self.assertIn("interno", LLMClient._http_message(500, ""))

    def test_cross_origin_redirect_is_blocked(self):
        request = urllib.request.Request(
            "https://provider.example/v1/chat/completions",
            headers={"Authorization": "Bearer secret"},
        )
        with self.assertRaises(LLMError):
            _SafeRedirectHandler().redirect_request(
                request,
                None,
                307,
                "Temporary Redirect",
                {},
                "https://attacker.example/steal",
            )


if __name__ == "__main__":
    unittest.main()

