"""Tests for configuration loading and validation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.config import (  # noqa: E402
    Config,
    ConfigError,
    load_config,
    normalize_base_url,
    save_config,
)


class NormalizeBaseUrlTests(unittest.TestCase):
    def test_adds_no_slash_and_accepts_endpoint(self):
        self.assertEqual(
            normalize_base_url(
                "https://opencode.ai/inference/go/openai/v1/chat/completions"
            ),
            "https://opencode.ai/inference/go/openai/v1",
        )

    def test_strips_trailing_slash(self):
        self.assertEqual(
            normalize_base_url("https://opencode.ai/inference/go/openai/v1/"),
            "https://opencode.ai/inference/go/openai/v1",
        )

    def test_migrates_legacy_go_url(self):
        self.assertEqual(
            normalize_base_url("https://opencode.ai/zen/go/v1"),
            "https://opencode.ai/inference/go/openai/v1",
        )

    def test_adds_openai_path_to_inference_base(self):
        self.assertEqual(
            normalize_base_url("https://opencode.ai/inference/go"),
            "https://opencode.ai/inference/go/openai/v1",
        )
        self.assertEqual(
            normalize_base_url("https://opencode.ai/inference"),
            "https://opencode.ai/inference/openai/v1",
        )

    def test_rejects_invalid_url(self):
        with self.assertRaises(ConfigError):
            normalize_base_url("opencode.ai")
        with self.assertRaises(ConfigError):
            normalize_base_url("")

    def test_rejects_plain_http_except_localhost(self):
        with self.assertRaises(ConfigError):
            normalize_base_url("http://example.com/v1")
        self.assertEqual(
            normalize_base_url("http://localhost:8080/v1"),
            "http://localhost:8080/v1",
        )
        self.assertEqual(
            normalize_base_url("http://127.0.0.1:8080/v1"),
            "http://127.0.0.1:8080/v1",
        )

    def test_rejects_credentials_and_query(self):
        with self.assertRaises(ConfigError):
            normalize_base_url("https://user:pass@example.com/v1")
        with self.assertRaises(ConfigError):
            normalize_base_url("https://example.com/v1?x=1")


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        config = Config().validate()
        self.assertEqual(config.model, "deepseek-v4.1-flash")
        self.assertEqual(
            config.base_url, "https://opencode.ai/inference/go/openai/v1"
        )
        self.assertTrue(config.enable_local_files)
        self.assertTrue(config.enable_web_search)

    def test_validate_rejects_bad_values(self):
        with self.assertRaises(ConfigError):
            Config(model="").validate()
        with self.assertRaises(ConfigError):
            Config(timeout=0).validate()
        with self.assertRaises(ConfigError):
            Config(max_tokens=10).validate()
        with self.assertRaises(ConfigError):
            Config(temperature=3).validate()

    def test_require_api_key_uses_environment(self):
        with patch.dict(os.environ, {"OPENCODE_API_KEY": "  env-key  "}):
            config = Config(api_key="").require_api_key()
        self.assertEqual(config.api_key, "env-key")

    def test_require_api_key_raises_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                Config(api_key="").require_api_key()

    def test_secret_can_be_hidden(self):
        config = Config(api_key="secret")
        self.assertEqual(config.as_dict(include_secret=False)["api_key"], "***")

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}, clear=True):
                config = Config(
                    api_key="key-123",
                    model="deepseek-v4.1-flash",
                    enable_local_files=False,
                    enable_web_search=False,
                )
                save_config(config)
                path = Path(directory) / "LibreOffice" / "4" / "user" / "LibreOfficeAI" / "config.json"
                self.assertTrue(path.exists())
                loaded = load_config()
                self.assertEqual(loaded.api_key, "key-123")
                self.assertEqual(loaded.model, "deepseek-v4.1-flash")
                self.assertFalse(loaded.enable_local_files)
                self.assertFalse(loaded.enable_web_search)
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(raw["api_key"], "key-123")

    def test_invalid_config_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}, clear=True):
                path = Path(directory) / "LibreOffice" / "4" / "user" / "LibreOfficeAI"
                path.mkdir(parents=True)
                (path / "config.json").write_text("{bad json", encoding="utf-8")
                loaded = load_config()
                self.assertEqual(loaded.base_url, Config().base_url)
                self.assertEqual(loaded.api_key, "")
                self.assertFalse((path / "config.json").exists())
                self.assertEqual(
                    (path / "config.json.bak").read_text(encoding="utf-8"),
                    "{bad json",
                )

    def test_invalid_field_preserves_api_key_and_valid_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}, clear=True):
                path = Path(directory) / "LibreOffice" / "4" / "user" / "LibreOfficeAI"
                path.mkdir(parents=True)
                payload = {
                    "api_key": "keep-me",
                    "base_url": "http://example.com/v1",
                    "model": "custom-model",
                    "timeout": "not-a-number",
                    "max_tokens": 2048,
                }
                (path / "config.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                loaded = load_config()
                self.assertEqual(loaded.api_key, "keep-me")
                self.assertEqual(loaded.model, "custom-model")
                self.assertEqual(loaded.timeout, 120)
                self.assertEqual(loaded.max_tokens, 2048)
                self.assertEqual(loaded.base_url, Config().base_url)

    def test_invalid_api_key_characters_are_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}, clear=True):
                path = Path(directory) / "LibreOffice" / "4" / "user" / "LibreOfficeAI"
                path.mkdir(parents=True)
                (path / "config.json").write_text(
                    json.dumps({"api_key": "bad\nkey", "model": "custom-model"}),
                    encoding="utf-8",
                )
                loaded = load_config()
                self.assertEqual(loaded.api_key, "badkey")
                self.assertEqual(loaded.model, "custom-model")

    def test_save_creates_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}, clear=True):
                save_config(Config(api_key="first"))
                save_config(Config(api_key="second"))
                path = Path(directory) / "LibreOffice" / "4" / "user" / "LibreOfficeAI"
                backup = json.loads((path / "config.json.bak").read_text(encoding="utf-8"))
                self.assertEqual(backup["api_key"], "first")


if __name__ == "__main__":
    unittest.main()
