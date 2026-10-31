"""Capture a compact, read-only description of the active document."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from .adapters.common import document_kind, selection_text
from .config import DEFAULT_MAX_CONTEXT_CHARS

_LOG = logging.getLogger(__name__)

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
    except Exception as exc:
        _LOG.debug("No se pudo leer el título del documento: %s", exc)
    try:
        url = str(doc.getURL() or "")
        if url:
            return _safe_name(urlparse(url).path)
    except Exception as exc:
        _LOG.debug("No se pudo leer la URL del documento: %s", exc)
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
    except Exception as exc:
        _LOG.debug("No se pudo leer el contexto de Writer: %s", exc)
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
        limited_end_column = min(
            address.EndColumn, address.StartColumn + MAX_CELL_COLUMNS - 1
        )
        limited_end_row = min(address.EndRow, address.StartRow + MAX_CELL_ROWS - 1)
        limited = sheet.getCellRangeByPosition(
            address.StartColumn,
            address.StartRow,
            limited_end_column,
            limited_end_row,
        )
        preview = [list(row) for row in limited.getDataArray()]
        if preview:
            parts.append("Valores visibles:\n" + repr(preview))
    except Exception as exc:
        _LOG.debug("No se pudo leer el contexto de Calc: %s", exc)
    return parts


def _shape_text(shape: Any) -> str:
    try:
        return str(shape.String or "").strip()
    except Exception as exc:
        _LOG.debug("No se pudo leer el texto de una forma: %s", exc)
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
    except Exception as exc:
        _LOG.debug("No se pudo leer el contexto de Impress: %s", exc)
    return parts


def build_document_context(
    doc: Any, max_chars: int = DEFAULT_MAX_CONTEXT_CHARS
) -> str:
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
    marker = "\n...[contexto truncado]"
    if len(context) > max_chars:
        context = context[: max(0, max_chars - len(marker))].rstrip() + marker
    return context
