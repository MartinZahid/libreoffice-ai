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
            normalize_base_url("https://opencode.ai/zen/go/v1/chat/completions"),
            "https://opencode.ai/zen/go/v1",
        )

    def test_strips_trailing_slash(self):
        self.assertEqual(
            normalize_base_url("https://opencode.ai/zen/go/v1/"),
            "https://opencode.ai/zen/go/v1",
        )

    def test_rejects_invalid_url(self):
        with self.assertRaises(ConfigError):
            normalize_base_url("opencode.ai")
        with self.assertRaises(ConfigError):
            normalize_base_url("")


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        config = Config().validate()
        self.assertEqual(config.model, "deepseek-v4.1-flash")
        self.assertEqual(config.base_url, "https://opencode.ai/zen/go/v1")

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
                config = Config(api_key="key-123", model="deepseek-v4.1-flash")
                save_config(config)
                path = Path(directory) / "LibreOffice" / "4" / "user" / "LibreOfficeAI" / "config.json"
                self.assertTrue(path.exists())
                loaded = load_config()
                self.assertEqual(loaded.api_key, "key-123")
                self.assertEqual(loaded.model, "deepseek-v4.1-flash")
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


if __name__ == "__main__":
    unittest.main()
