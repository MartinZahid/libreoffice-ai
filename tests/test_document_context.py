"""Tests for the compact document context sent to the model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extension" / "pythonpath"))

from core.document_context import build_document_context  # noqa: E402


class FakeDoc:
    def __init__(self, service, title="", url=""):
        self.service = service
        self.title = title
        self.url = url

    def supportsService(self, service):
        return service == self.service

    def getTitle(self):
        return self.title

    def getURL(self):
        return self.url

    def getCurrentController(self):
        raise RuntimeError("no controller")


class DocumentContextTests(unittest.TestCase):
    def test_title_uses_basename_not_local_path(self):
        doc = FakeDoc(
            "com.sun.star.text.TextDocument",
            title=r"C:\Users\Martin Aburto\Documento.odt",
        )
        context = build_document_context(doc)
        self.assertIn("Documento.odt", context)
        self.assertNotIn("Martin Aburto", context)
        self.assertNotIn("C:\\", context)

    def test_url_is_reduced_to_basename(self):
        doc = FakeDoc(
            "com.sun.star.text.TextDocument",
            url="file:///C:/Users/Martin/informe%20final.odt",
        )
        context = build_document_context(doc)
        self.assertIn("informe%20final.odt", context)
        self.assertNotIn("C:/Users", context)

    def test_missing_document(self):
        self.assertIn("No hay", build_document_context(None))

    def test_context_is_limited(self):
        doc = FakeDoc("com.sun.star.text.TextDocument", title="x" * 5000)
        context = build_document_context(doc, max_chars=10)
        self.assertIn("contexto truncado", context)
        self.assertLess(len(context), 60)


if __name__ == "__main__":
    unittest.main()
