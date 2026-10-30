"""Validate and execute proposed actions as one undoable group."""

from __future__ import annotations

from typing import Any

from .tools import TOOLS_BY_NAME

ACTION_LABELS = {
    "writer_insert_text": "Insertar texto",
    "writer_rewrite_selection": "Reescribir la selección",
    "writer_find_replace": "Buscar y reemplazar",
    "writer_insert_table": "Insertar tabla",
    "writer_insert_list": "Insertar lista",
    "writer_format": "Aplicar formato",
    "writer_insert_page_break": "Insertar salto de página",
    "writer_insert_image": "Insertar imagen",
    "writer_insert_toc": "Insertar índice",
    "calc_write_range": "Escribir celdas",
    "calc_create_table": "Crear tabla",
    "calc_insert_rows": "Insertar filas",
    "calc_insert_columns": "Insertar columnas",
    "calc_format_range": "Formatear rango",
    "calc_set_column_width": "Ajustar ancho de columnas",
    "calc_sort_range": "Ordenar rango",
    "calc_add_sheet": "Añadir hoja",
    "impress_add_slide": "Añadir diapositiva",
    "impress_set_title": "Cambiar título",
    "impress_add_text": "Añadir cuadro de texto",
    "impress_add_bullets": "Añadir viñetas",
    "impress_insert_image": "Insertar imagen",
    "impress_insert_table": "Insertar tabla",
}


def _short(value: Any, limit: int = 60) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def describe_action(action: dict[str, Any]) -> str:
    """Return a short Spanish summary used in the confirmation preview."""
    name = str(action.get("name") or "")
    arguments = action.get("arguments") or {}
    label = ACTION_LABELS.get(name, name)
    details = ""
    if name in ("writer_insert_text", "writer_rewrite_selection", "impress_add_text"):
        details = _short(arguments.get("text"))
    elif name == "writer_find_replace":
        details = f"“{_short(arguments.get('find'), 30)}” → “{_short(arguments.get('replace'), 30)}”"
    elif name in ("writer_insert_table", "calc_create_table", "impress_insert_table"):
        rows = arguments.get("data") or []
        columns = max((len(row) for row in rows if isinstance(row, list)), default=0)
        details = f"{len(rows)} filas × {columns} columnas"
    elif name == "writer_insert_list":
        details = f"{len(arguments.get('items') or [])} elementos"
    elif name == "calc_write_range":
        details = f"desde {arguments.get('start_cell', 'A1')}"
    elif name in ("calc_format_range", "calc_sort_range"):
        details = str(arguments.get("range", ""))
    elif name == "calc_set_column_width":
        details = f"columnas {arguments.get('columns', '')}"
    elif name == "calc_add_sheet":
        details = str(arguments.get("name", ""))
    elif name == "impress_add_slide":
        details = _short(arguments.get("title"), 40)
    elif name == "impress_set_title":
        details = f"diapositiva {arguments.get('slide_index', '')}: {_short(arguments.get('title'), 40)}"
    elif name == "impress_add_bullets":
        details = f"diapositiva {arguments.get('slide_index', '')}, {len(arguments.get('items') or [])} viñetas"
    elif name in ("writer_insert_image", "impress_insert_image"):
        details = str(arguments.get("path", ""))
    return f"{label}: {details}" if details else label


def _adapter_for(doc: Any, actions: list[dict[str, Any]]) -> Any:
    text_doc = _supports(doc, "com.sun.star.text.TextDocument") or _supports(doc, "com.sun.star.text.WebDocument")
    calc_doc = _supports(doc, "com.sun.star.sheet.SpreadsheetDocument")
    impress_doc = _supports(doc, "com.sun.star.presentation.PresentationDocument") or _supports(
        doc, "com.sun.star.drawing.DrawingDocument"
    )

    prefix = ""
    for action in actions:
        name = str(action.get("name") or "")
        if not prefix:
            prefix = name.split("_", 1)[0]
        if name.split("_", 1)[0] != prefix:
            raise ValueError("No se pueden mezclar acciones de distintos tipos de documento.")

    if prefix == "writer" and text_doc:
        from .adapters.writer import WriterAdapter

        return WriterAdapter(doc)
    if prefix == "calc" and calc_doc:
        from .adapters.calc import CalcAdapter

        return CalcAdapter(doc)
    if prefix == "impress" and impress_doc:
        from .adapters.impress import ImpressAdapter

        return ImpressAdapter(doc)
    raise ValueError("Las acciones no corresponden al tipo de documento activo.")


def _supports(doc: Any, service: str) -> bool:
    try:
        return bool(doc.supportsService(service))
    except Exception:
        return False


class Executor:
    """Execute actions on the main thread and group them into one undo step."""

    def __init__(self, ctx: Any = None):
        self.ctx = ctx

    def apply(self, doc: Any, actions: list[dict[str, Any]]) -> list[str]:
        if not actions:
            return []
        if doc is None:
            raise ValueError("No hay un documento abierto para aplicar los cambios.")

        for action in actions:
            name = str(action.get("name") or "")
            if name not in TOOLS_BY_NAME:
                raise ValueError(f"Acción desconocida: {name}")
            if not isinstance(action.get("arguments") or {}, dict):
                raise ValueError(f"Argumentos inválidos para {name}.")

        adapter = _adapter_for(doc, actions)
        descriptions = [describe_action(action) for action in actions]
        undo = None
        undo_open = False
        try:
            undo = doc.getUndoManager()
            undo.enterUndoContext("Asistente IA (vista previa)")
            undo_open = True
        except Exception:
            undo = None

        try:
            for action in actions:
                adapter.execute(action)
        except Exception:
            if undo is not None and undo_open:
                try:
                    undo.leaveUndoContext()
                except Exception:
                    pass
                try:
                    undo.undo()
                except Exception:
                    pass
            raise
        else:
            if undo is not None and undo_open:
                try:
                    undo.leaveUndoContext()
                except Exception:
                    pass
        return descriptions

    @staticmethod
    def revert(doc: Any) -> None:
        """Undo the last grouped preview as one step."""
        if doc is None:
            raise ValueError("No hay un documento abierto para deshacer la vista previa.")
        try:
            undo = doc.getUndoManager()
            undo.undo()
        except Exception as exc:
            raise ValueError("No se pudo deshacer la vista previa.") from exc
