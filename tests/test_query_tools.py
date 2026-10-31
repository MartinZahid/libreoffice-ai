"""Tests for read-only local and web query tools."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.config import Config  # noqa: E402
from core.query_tools import (  # noqa: E402
    QueryError,
    QueryRunner,
    list_local_images,
)


class LocalImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.sub = os.path.join(self.root, "sub")
        os.makedirs(self.sub)
        for name in ("a.png", "b.JPG", "nota.txt"):
            Path(self.root, name).write_bytes(b"x")
        for name in ("c.webp", "otra.txt"):
            Path(self.sub, name).write_bytes(b"y")

    def tearDown(self):
        self.temp.cleanup()

    def test_lists_only_images_in_folder(self):
        result = list_local_images(self.root)
        names = [item["name"].lower() for item in result["images"]]
        self.assertEqual(result["count"], 2)
        self.assertEqual(names, ["a.png", "b.jpg"])
        self.assertFalse(result["truncated"])

    def test_recursive_includes_subfolders(self):
        result = list_local_images(self.root, recursive=True)
        names = [item["name"].lower() for item in result["images"]]
        self.assertIn("c.webp", names)
        self.assertNotIn("otra.txt", names)

    def test_limit_marks_truncated(self):
        result = list_local_images(self.root, limit=1)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["truncated"])

    def test_accepts_single_image_file(self):
        result = list_local_images(os.path.join(self.root, "a.png"))
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["images"][0]["name"], "a.png")

    def test_resolves_relative_folder_inside_home(self):
        real_expanduser = os.path.expanduser
        with patch(
            "core.query_tools.os.path.expanduser",
            side_effect=lambda value: self.root if value == "~" else real_expanduser(value),
        ):
            result = list_local_images("sub")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["images"][0]["name"], "c.webp")

    def test_rejects_missing_network_and_escaping_paths(self):
        with self.assertRaises(QueryError):
            list_local_images("no-such-folder-xyz")
        with self.assertRaises(QueryError):
            list_local_images(os.path.join(self.root, "missing"))
        with self.assertRaises(QueryError):
            list_local_images("\\\\server\\share")
        with self.assertRaises(QueryError):
            list_local_images("../outside")
        with self.assertRaises(QueryError):
            list_local_images(os.path.join(self.root, "nota.txt"))

    def test_empty_folder_has_message(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        result = list_local_images(empty)
        self.assertEqual(result["count"], 0)
        self.assertIn("message", result)


class QueryRunnerTests(unittest.TestCase):
    def test_disabled_tools_are_rejected(self):
        runner = QueryRunner(Config(enable_local_files=False, enable_web_search=False))
        self.assertEqual(runner.enabled_names(), [])
        with self.assertRaises(QueryError):
            runner.run("list_local_images", {})
        with self.assertRaises(QueryError):
            runner.run("search_web", {"query": "x"})

    def test_web_search_delegates(self):
        runner = QueryRunner(Config(enable_web_search=True))
        expected = [{"title": "A", "url": "https://example.com", "snippet": ""}]
        with patch("core.query_tools.search_web", return_value=expected) as search:
            result = runner.run("search_web", {"query": "hola", "max_results": 3})
        search.assert_called_once()
        self.assertEqual(result["results"], expected)

    def test_image_search_and_download_delegate(self):
        runner = QueryRunner(Config(enable_web_search=True))
        with patch("core.query_tools.search_images", return_value=[{"image_url": "https://x/y.jpg"}]):
            images = runner.run("search_images", {"query": "gato"})
        self.assertEqual(images["images"][0]["image_url"], "https://x/y.jpg")
        with patch("core.query_tools.download_image", return_value={"path": "C:/tmp/x.jpg"}):
            downloaded = runner.run("download_image", {"url": "https://x/y.jpg"})
        self.assertEqual(downloaded["path"], "C:/tmp/x.jpg")


if __name__ == "__main__":
    unittest.main()
