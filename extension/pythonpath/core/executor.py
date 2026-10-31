"""Validate and execute proposed actions as one undoable group."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .adapters.common import document_kind
from .tools import TOOLS_BY_NAME

_LOG = logging.getLogger(__name__)

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


def _table_details(arguments: dict[str, Any], formulas: bool = False) -> str:
    rows = arguments.get("data") or []
    columns = max((len(row) for row in rows if isinstance(row, list)), default=0)
    details = f"{len(rows)} filas × {columns} columnas"
    if formulas:
        found = _formula_list(rows)
        if found:
            details += f"; fórmulas: {', '.join(found[:5])}"
    return details


def _describe_text(arguments: dict[str, Any]) -> str:
    return _short(arguments.get("text"))


def _describe_rewrite(arguments: dict[str, Any]) -> str:
    return _short(arguments.get("text"))


def _describe_find_replace(arguments: dict[str, Any]) -> str:
    return (
        f"“{_short(arguments.get('find'), 30)}” → "
        f"“{_short(arguments.get('replace'), 30)}”"
    )


def _describe_writer_table(arguments: dict[str, Any]) -> str:
    return _table_details(arguments)


def _describe_list(arguments: dict[str, Any]) -> str:
    return f"{len(arguments.get('items') or [])} elementos"


def _describe_calc_table(arguments: dict[str, Any]) -> str:
    return _table_details(arguments, formulas=True)


def _describe_calc_range(arguments: dict[str, Any]) -> str:
    details = f"desde {arguments.get('start_cell', 'A1')}"
    formulas = _formula_list(arguments.get("values"))
    if formulas:
        details += f"; fórmulas: {', '.join(formulas[:5])}"
    return details


def _describe_range(arguments: dict[str, Any]) -> str:
    return str(arguments.get("range", ""))


def _describe_columns(arguments: dict[str, Any]) -> str:
    return f"columnas {arguments.get('columns', '')}"


def _describe_sheet(arguments: dict[str, Any]) -> str:
    return str(arguments.get("name", ""))


def _describe_slide(arguments: dict[str, Any]) -> str:
    return _short(arguments.get("title"), 40)


def _describe_set_title(arguments: dict[str, Any]) -> str:
    return f"diapositiva {arguments.get('slide_index', '')}: {_short(arguments.get('title'), 40)}"


def _describe_bullets(arguments: dict[str, Any]) -> str:
    return (
        f"diapositiva {arguments.get('slide_index', '')}, "
        f"{len(arguments.get('items') or [])} viñetas"
    )


def _describe_image(arguments: dict[str, Any]) -> str:
    return str(arguments.get("path", ""))


_DESCRIBERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "writer_insert_text": _describe_text,
    "writer_rewrite_selection": _describe_rewrite,
    "writer_find_replace": _describe_find_replace,
    "writer_insert_table": _describe_writer_table,
    "writer_insert_list": _describe_list,
    "calc_create_table": _describe_calc_table,
    "calc_write_range": _describe_calc_range,
    "calc_format_range": _describe_range,
    "calc_sort_range": _describe_range,
    "calc_set_column_width": _describe_columns,
    "calc_add_sheet": _describe_sheet,
    "impress_add_slide": _describe_slide,
    "impress_set_title": _describe_set_title,
    "impress_add_bullets": _describe_bullets,
    "impress_insert_table": _describe_writer_table,
    "impress_add_text": _describe_text,
    "writer_insert_image": _describe_image,
    "impress_insert_image": _describe_image,
}


def describe_action(action: dict[str, Any]) -> str:
    """Return a short Spanish summary used in the confirmation preview."""
    name = str(action.get("name") or "")
    arguments = action.get("arguments") or {}
    label = ACTION_LABELS.get(name, name)
    describer = _DESCRIBERS.get(name)
    details = describer(arguments) if describer else ""
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


def _undo_count(undo: Any) -> int | None:
    """Return the number of undoable actions, or None if unsupported."""
    try:
        titles = undo.getAllUndoActionTitles()
        return len(titles)
    except Exception as exc:
        _LOG.debug("No se pudo leer el historial de deshacer: %s", exc)
        return None


class Executor:
    """Execute actions on the main thread and group them into one undo step."""

    PREVIEW_TITLE = "Asistente IA (vista previa)"

    def __init__(self) -> None:
        self._preview_doc: Any = None
        self._preview_count: int | None = None

    @property
    def can_revert(self) -> bool:
        return self._preview_count is not None

    def _normalize(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for action in actions:
            name = str(action.get("name") or "")
            if name not in TOOLS_BY_NAME:
                raise ValueError(f"Acción desconocida: {name}")
            arguments = action.get("arguments")
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                raise ValueError(f"Argumentos inválidos para {name}.")
            normalized.append(
                {"id": action.get("id"), "name": name, "arguments": arguments}
            )
        return normalized

    def apply(self, doc: Any, actions: list[dict[str, Any]]) -> list[str]:
        if not actions:
            return []
        if doc is None:
            raise ValueError("No hay un documento abierto para aplicar los cambios.")

        normalized = self._normalize(actions)
        adapter = _adapter_for(doc, normalized)
        descriptions = [describe_action(action) for action in normalized]

        try:
            undo = doc.getUndoManager()
        except Exception as exc:
            raise ValueError("No se pudo acceder al historial de deshacer del documento.") from exc
        if undo is None:
            raise ValueError("El documento no permite agrupar los cambios para deshacerlos.")

        before = _undo_count(undo)
        if before is None:
            raise ValueError("No se pudo verificar el historial de deshacer del documento.")

        try:
            undo.enterUndoContext(self.PREVIEW_TITLE)
        except Exception as exc:
            raise ValueError("No se pudo iniciar el grupo de deshacer de la vista previa.") from exc

        applied = 0
        try:
            for action in normalized:
                adapter.execute(action)
                applied += 1
        except Exception as exc:
            rollback_error = self._rollback(undo, True, applied, before)
            if rollback_error:
                raise ValueError(
                    f"Error al aplicar los cambios: {exc}. "
                    f"Es posible que el documento quede parcialmente modificado: {rollback_error}"
                ) from exc
            raise
        except BaseException:
            self._rollback(undo, True, applied, before)
            raise

        try:
            undo.leaveUndoContext()
        except Exception as exc:
            rollback_error = self._rollback(undo, True, applied, before)
            detail = f" {rollback_error}" if rollback_error else ""
            raise ValueError(
                "Los cambios se aplicaron, pero no se pudo cerrar el grupo de deshacer. "
                "Revisa el documento antes de continuar." + detail
            ) from exc

        after = _undo_count(undo)
        self._preview_doc = doc
        self._preview_count = after if after is not None and after > before else None
        if self._preview_count is None:
            _LOG.warning("La vista previa no añadió una acción de deshacer verificable.")
        return descriptions

    def _rollback(self, undo: Any, undo_open: bool, applied: int, before: int) -> str:
        problems = []
        if undo_open:
            try:
                undo.leaveUndoContext()
            except Exception as exc:
                problems.append(f"no se pudo cerrar el grupo de deshacer ({exc})")

        after = _undo_count(undo)
        if applied and after is None:
            problems.append("no se pudo verificar la vista previa en el historial")
        elif applied and after is not None and after > before:
            try:
                undo.undo()
            except Exception as exc:
                problems.append(f"no se pudo deshacer ({exc})")
        elif applied:
            problems.append("la vista previa no quedó registrada para deshacer")
        return "; ".join(problems)

    def accept(self) -> None:
        """Forget the preview after the user decides to keep it."""
        self._preview_doc = None
        self._preview_count = None

    def revert(self, doc: Any) -> None:
        """Undo only the grouped preview, never later user edits."""
        if doc is None:
            raise ValueError("No hay un documento abierto para deshacer la vista previa.")
        if self._preview_doc is None or self._preview_count is None:
            raise ValueError(
                "No hay una vista previa registrada por este chat. "
                "Deshaz manualmente si es necesario."
            )
        try:
            same_document = doc == self._preview_doc
        except Exception:
            same_document = False
        if not same_document:
            raise ValueError("La vista previa pertenece a otro documento.")
        try:
            undo = doc.getUndoManager()
        except Exception as exc:
            raise ValueError("No se pudo acceder al historial de deshacer.") from exc
        current = _undo_count(undo)
        if current is None or current != self._preview_count:
            raise ValueError(
                "No se puede rechazar la vista previa porque hay cambios posteriores "
                "o ya no está disponible en el historial. Deshaz manualmente si es necesario."
            )
        try:
            undo.undo()
        except Exception as exc:
            raise ValueError("No se pudo deshacer la vista previa.") from exc
        self.accept()
