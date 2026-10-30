"""Capture a compact, read-only description of the active document."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from .adapters.common import document_kind, selection_text

MAX_SELECTION_CHARS = 4000
MAX_PARAGRAPH_CHARS = 2000
MAX_CELL_ROWS = 8
MAX_CELL_COLUMNS = 8
MAX_SLIDE_SHAPES = 20

DOCUMENT_NAMES = {
    "writer": "Writer",
    "calc": "Calc",
    "impress": "Impress",
    "draw": "Draw",
}


def _safe_name(value: str) -> str:
    name = os.path.basename(value.replace("\\", "/").rstrip("/"))
    return name or "Sin título"


def _title(doc: Any) -> str:
    try:
        title = str(doc.getTitle() or "").strip()
        if title:
            return _safe_name(title)
    except Exception:
        pass
    try:
        url = str(doc.getURL() or "")
        if url:
            return _safe_name(urlparse(url).path)
    except Exception:
        pass
    return "Sin título"


def _writer_context(doc: Any) -> list[str]:
    parts = []
    try:
        controller = doc.getCurrentController()
        selected = selection_text(controller.getSelection())
        if selected:
            parts.append("Texto seleccionado:\n" + selected[:MAX_SELECTION_CHARS])

        view_cursor = controller.getViewCursor()
        if view_cursor is not None:
            paragraph = doc.getText().createTextCursorByRange(view_cursor)
            paragraph.gotoStartOfParagraph(False)
            paragraph.gotoEndOfParagraph(True)
            text = str(paragraph.getString() or "")
            if text:
                parts.append("Párrafo actual:\n" + text[:MAX_PARAGRAPH_CHARS])
    except Exception:
        pass
    return parts


def _calc_context(doc: Any) -> list[str]:
    parts = []
    try:
        controller = doc.getCurrentController()
        sheet = controller.getActiveSheet()
        parts.append(f"Hoja activa: {sheet.Name}")
        selection = controller.getSelection()
        if selection is None:
            return parts
        address = selection.getRangeAddress()
        start_column = address.StartColumn + 1
        start_row = address.StartRow + 1
        end_column = address.EndColumn + 1
        end_row = address.EndRow + 1
        parts.append(f"Rango seleccionado: {start_column},{start_row} a {end_column},{end_row}")
        data = selection.getDataArray()
        rows = min(len(data), MAX_CELL_ROWS)
        preview = []
        for row in data[:rows]:
            preview.append(list(row[:MAX_CELL_COLUMNS]))
        if preview:
            parts.append("Valores visibles:\n" + repr(preview))
    except Exception:
        pass
    return parts


def _shape_text(shape: Any) -> str:
    try:
        return str(shape.String or "").strip()
    except Exception:
        return ""


def _impress_context(doc: Any) -> list[str]:
    parts = []
    try:
        pages = doc.getDrawPages()
        parts.append(f"Número de diapositivas: {pages.getCount()}")
        current_page = doc.getCurrentController().getCurrentPage()
        current_index = None
        for index in range(pages.getCount()):
            if pages.getByIndex(index) == current_page:
                current_index = index + 1
                break
        if current_index is not None:
            parts.append(f"Diapositiva actual: {current_index}")
            shapes = []
            for shape_index in range(current_page.getCount()):
                if shape_index >= MAX_SLIDE_SHAPES:
                    break
                text = _shape_text(current_page.getByIndex(shape_index))
                if text:
                    shapes.append(text[:1000])
            if shapes:
                parts.append("Textos de la diapositiva:\n" + "\n---\n".join(shapes))
    except Exception:
        pass
    return parts


def build_document_context(doc: Any, max_chars: int = 12000) -> str:
    """Return a short context block that is safe to send to the model."""
    if doc is None:
        return "No hay un documento abierto."
    kind = document_kind(doc)
    doc_type = DOCUMENT_NAMES.get(kind, "Documento")
    parts = [f"Tipo de documento: {doc_type}", f"Título: {_title(doc)}"]
    if kind == "writer":
        parts.extend(_writer_context(doc))
    elif kind == "calc":
        parts.extend(_calc_context(doc))
    elif kind in ("impress", "draw"):
        parts.extend(_impress_context(doc))
    context = "\n\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars].rstrip() + "\n...[contexto truncado]"
    return context
