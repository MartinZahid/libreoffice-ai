"""Tests for safe web helpers."""

from __future__ import annotations

import json
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.web import (  # noqa: E402
    WebError,
    _clean_text,
    _sniff_image_extension,
    _TextExtractor,
    _parse_bing,
    _parse_duckduckgo,
    _validate_public_url,
    search_images,
    search_web,
)


class UrlValidationTests(unittest.TestCase):
    def test_accepts_public_https_url(self):
        self.assertEqual(
            _validate_public_url("https://8.8.8.8/path"),
            "https://8.8.8.8/path",
        )

    def test_accepts_resolved_public_hostname(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("core.web.socket.getaddrinfo", return_value=addresses):
            self.assertEqual(
                _validate_public_url("https://example.com/page"),
                "https://example.com/page",
            )

    def test_rejects_private_and_local_addresses(self):
        for url in (
            "http://localhost/",
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://192.168.1.5/",
            "http://[::1]/",
            "http://169.254.169.254/",
            "http://printer.local/",
        ):
            with self.subTest(url=url), self.assertRaises(WebError):
                _validate_public_url(url)

    def test_rejects_resolved_private_hostname(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]
        with patch("core.web.socket.getaddrinfo", return_value=addresses):
            with self.assertRaises(WebError):
                _validate_public_url("https://internal.example/page")

    def test_rejects_unsafe_url_parts(self):
        for url in (
            "file:///C:/secret.txt",
            "ftp://example.com/a",
            "https://user:pass@example.com/",
            "https://example.com:8080/",
            "https://example.com/a b",
            "not a url",
        ):
            with self.subTest(url=url), self.assertRaises(WebError):
                _validate_public_url(url)


class ParsingTests(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(_clean_text("<b>Hola</b>   mundo &amp; sol"), "Hola mundo & sol")

    def test_sniffs_image_formats(self):
        self.assertEqual(_sniff_image_extension(b"\x89PNG\r\n\x1a\nrest"), ".png")
        self.assertEqual(_sniff_image_extension(b"\xff\xd8\xffrest"), ".jpg")
        self.assertEqual(_sniff_image_extension(b"GIF89arest"), ".gif")
        self.assertEqual(_sniff_image_extension(b"<svg xmlns='x'></svg>"), ".svg")
        self.assertEqual(_sniff_image_extension(b"not an image"), "")

    def test_parses_duckduckgo_results(self):
        html = (
            "<a rel='nofollow' href=\"//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=1\""
            " class='result-link'>Example <b>one</b></a>"
            "<td class='result-snippet'>First <b>snippet</b></td>"
        )
        results = _parse_duckduckgo(html, 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.com/a")
        self.assertEqual(results[0]["title"], "Example one")
        self.assertEqual(results[0]["snippet"], "First snippet")

    def test_parses_bing_results(self):
        html = (
            '<li class="b_algo"><h2><a href="https://example.com/b">Bing title</a></h2>'
            "<p>Bing description</p></li>"
        )
        results = _parse_bing(html, 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.com/b")
        self.assertEqual(results[0]["title"], "Bing title")

    def test_extracts_page_text_without_scripts(self):
        parser = _TextExtractor()
        parser.feed(
            "<html><head><title>Mi página</title><style>x{}</style></head>"
            "<body><h1>Hola</h1><p>Mundo <b>feliz</b></p><script>alert(1)</script></body></html>"
        )
        parser.close()
        self.assertEqual(parser.title(), "Mi página")
        self.assertIn("Hola", parser.text())
        self.assertIn("Mundo feliz", parser.text())
        self.assertNotIn("alert", parser.text())


class SearchTests(unittest.TestCase):
    def test_search_web_uses_duckduckgo_first(self):
        html = (
            "<a href=\"//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa\""
            " class='result-link'>Example</a>"
            "<td class='result-snippet'>Snippet</td>"
        )
        with patch("core.web._fetch_text", return_value=html) as fetch:
            results = search_web("consulta", 2)
        self.assertEqual(results[0]["url"], "https://example.com/a")
        self.assertEqual(fetch.call_count, 1)

    def test_search_web_falls_back_to_bing(self):
        bing = (
            '<li class="b_algo"><h2><a href="https://example.com/b">Bing</a></h2>'
            "<p>Description</p></li>"
        )
        with patch("core.web._fetch_text", side_effect=[WebError("blocked"), bing]):
            results = search_web("consulta", 2)
        self.assertEqual(results[0]["url"], "https://example.com/b")

    def test_search_images_uses_duckduckgo_json(self):
        landing = '<html><script>vqd="4-123456";</script></html>'
        payload = json.dumps(
            {
                "results": [
                    {
                        "image": "https://example.com/image.jpg",
                        "title": "Foto",
                        "url": "https://example.com/page",
                        "source": "Example",
                    }
                ]
            }
        )
        with patch("core.web._fetch_text", side_effect=[landing, payload]):
            images = search_images("consulta", 2)
        self.assertEqual(images[0]["image_url"], "https://example.com/image.jpg")
        self.assertEqual(images[0]["title"], "Foto")


if __name__ == "__main__":
    unittest.main()
