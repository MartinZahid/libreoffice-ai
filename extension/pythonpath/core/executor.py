"""Validate and execute proposed actions as one undoable group."""

from __future__ import annotations

from typing import Any

from .adapters.common import document_kind
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


def _formula_list(values: Any) -> list[str]:
    formulas = []
    if isinstance(values, list):
        for row in values:
            if not isinstance(row, list):
                continue
            for value in row:
                if isinstance(value, str) and value.startswith("="):
                    formulas.append(_short(value, 80))
    return formulas


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
        if name == "calc_create_table":
            formulas = _formula_list(rows)
            if formulas:
                details += f"; fórmulas: {', '.join(formulas[:5])}"
    elif name == "writer_insert_list":
        details = f"{len(arguments.get('items') or [])} elementos"
    elif name == "calc_write_range":
        details = f"desde {arguments.get('start_cell', 'A1')}"
        formulas = _formula_list(arguments.get("values"))
        if formulas:
            details += f"; fórmulas: {', '.join(formulas[:5])}"
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
    kind = document_kind(doc)
    prefix = ""
    for action in actions:
        name = str(action.get("name") or "")
        if not prefix:
            prefix = name.split("_", 1)[0]
        if name.split("_", 1)[0] != prefix:
            raise ValueError("No se pueden mezclar acciones de distintos tipos de documento.")

    if prefix == "writer" and kind == "writer":
        from .adapters.writer import WriterAdapter

        return WriterAdapter(doc)
    if prefix == "calc" and kind == "calc":
        from .adapters.calc import CalcAdapter

        return CalcAdapter(doc)
    if prefix == "impress" and kind in ("impress", "draw"):
        from .adapters.impress import ImpressAdapter

        return ImpressAdapter(doc)
    raise ValueError("Las acciones no corresponden al tipo de documento activo.")


class Executor:
    """Execute actions on the main thread and group them into one undo step."""

    PREVIEW_TITLE = "Asistente IA (vista previa)"

    def apply(self, doc: Any, actions: list[dict[str, Any]]) -> list[str]:
        if not actions:
            return []
        if doc is None:
            raise ValueError("No hay un documento abierto para aplicar los cambios.")

        for action in actions:
            name = str(action.get("name") or "")
            if name not in TOOLS_BY_NAME:
                raise ValueError(f"Acción desconocida: {name}")
            arguments = action.get("arguments")
            if arguments is not None and not isinstance(arguments, dict):
                raise ValueError(f"Argumentos inválidos para {name}.")
            action["arguments"] = arguments or {}

        adapter = _adapter_for(doc, actions)
        descriptions = [describe_action(action) for action in actions]
        try:
            undo = doc.getUndoManager()
        except Exception as exc:
            raise ValueError("No se pudo acceder al historial de deshacer del documento.") from exc
        if undo is None:
            raise ValueError("El documento no permite agrupar los cambios para deshacerlos.")
        try:
            undo.enterUndoContext(self.PREVIEW_TITLE)
        except Exception as exc:
            raise ValueError("No se pudo iniciar el grupo de deshacer de la vista previa.") from exc

        applied = 0
        try:
            for action in actions:
                adapter.execute(action)
                applied += 1
        except Exception as exc:
            rollback_error = self._rollback(undo, True, applied)
            if rollback_error:
                raise ValueError(
                    f"Error al aplicar los cambios: {exc}. "
                    f"Es posible que el documento quede parcialmente modificado: {rollback_error}"
                ) from exc
            raise
        else:
            try:
                undo.leaveUndoContext()
            except Exception as exc:
                raise ValueError(
                    "Los cambios se aplicaron, pero no se pudo cerrar el grupo de deshacer. "
                    "Revisa el documento antes de continuar."
                ) from exc
        return descriptions

    @staticmethod
    def _rollback(undo: Any, undo_open: bool, applied: int) -> str:
        problems = []
        if undo_open:
            try:
                undo.leaveUndoContext()
            except Exception as exc:
                problems.append(f"no se pudo cerrar el grupo de deshacer ({exc})")
        if undo is not None and Executor._preview_is_on_top(undo):
            try:
                undo.undo()
            except Exception as exc:
                problems.append(f"no se pudo deshacer ({exc})")
        elif applied:
            problems.append("no se pudo verificar la vista previa en el historial")
        return "; ".join(problems)

    @staticmethod
    def _preview_is_on_top(undo: Any) -> bool:
        try:
            if not undo.isUndoPossible():
                return False
        except Exception:
            pass
        for method in (
            "getCurrentUndoActionTitle",
            "getCurrentUndoContextTitle",
            "getUndoActionTitle",
            "getUndoContextTitle",
        ):
            try:
                title = getattr(undo, method)()
            except Exception:
                continue
            if title and str(title).startswith("Asistente IA"):
                return True
        return False

    @classmethod
    def revert(cls, doc: Any) -> None:
        """Undo only the grouped preview, never later user edits."""
        if doc is None:
            raise ValueError("No hay un documento abierto para deshacer la vista previa.")
        try:
            undo = doc.getUndoManager()
        except Exception as exc:
            raise ValueError("No se pudo acceder al historial de deshacer.") from exc
        if not cls._preview_is_on_top(undo):
            raise ValueError(
                "No se puede rechazar la vista previa porque hay cambios posteriores "
                "o ya no está disponible en el historial. Deshaz manualmente si es necesario."
            )
        try:
            undo.undo()
        except Exception as exc:
            raise ValueError("No se pudo deshacer la vista previa.") from exc
