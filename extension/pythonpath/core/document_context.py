"""Capture a compact, read-only description of the active document."""

from __future__ import annotations

from typing import Any

MAX_SELECTION_CHARS = 4000
MAX_PARAGRAPH_CHARS = 2000
MAX_CELL_ROWS = 8
MAX_CELL_COLUMNS = 8
MAX_SLIDE_SHAPES = 20


def _supports(doc: Any, service: str) -> bool:
    try:
        return bool(doc.supportsService(service))
    except Exception:
        return False


def _doc_type(doc: Any) -> str:
    if _supports(doc, "com.sun.star.text.TextDocument"):
        return "Writer"
    if _supports(doc, "com.sun.star.sheet.SpreadsheetDocument"):
        return "Calc"
    if _supports(doc, "com.sun.star.presentation.PresentationDocument"):
        return "Impress"
    if _supports(doc, "com.sun.star.drawing.DrawingDocument"):
        return "Draw"
    return "Documento"


def _title(doc: Any) -> str:
    try:
        title = doc.getTitle()
        if title:
            return str(title)
    except Exception:
        pass
    try:
        return str(doc.getURL() or "Sin título")
    except Exception:
        return "Sin título"


def _writer_context(doc: Any) -> list[str]:
    parts = []
    try:
        controller = doc.getCurrentController()
        selection = controller.getSelection()
        selected = ""
        if selection is not None and hasattr(selection, "getString"):
            selected = str(selection.getString() or "")
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
    doc_type = _doc_type(doc)
    parts = [f"Tipo de documento: {doc_type}", f"Título: {_title(doc)}"]
    if doc_type == "Writer":
        parts.extend(_writer_context(doc))
    elif doc_type == "Calc":
        parts.extend(_calc_context(doc))
    elif doc_type in ("Impress", "Draw"):
        parts.extend(_impress_context(doc))
    context = "\n\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars].rstrip() + "\n...[contexto truncado]"
    return context
