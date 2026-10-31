"""Impress actions implemented with the LibreOffice UNO API."""

from __future__ import annotations

import logging
from typing import Any, Iterable

import uno

from .common import (
    BOLD,
    IMPRESS_CONTENT_BOX,
    IMPRESS_TABLE_BOX,
    IMPRESS_TEXT_BOX,
    IMPRESS_TITLE_BOX,
    TITLE_FONT_SIZE,
    bounded_float,
    cm_to_100mm,
    set_optional,
    validate_image_path,
)

_LOG = logging.getLogger(__name__)

TITLE_NAME = "LibreOfficeAI_Title"
BODY_NAME = "LibreOfficeAI_Body"
BULLET_PREFIX = "• "
LAYOUTS = {"title": 0, "title_content": 1, "title_only": 19, "blank": 20}


class ImpressAdapter:
    """Apply presentation actions to a single Impress document."""

    def __init__(self, doc: Any):
        self.doc = doc

    def execute(self, action: dict[str, Any]) -> None:
        name = action["name"]
        args = action.get("arguments", {})
        handler = getattr(self, name, None)
        if handler is None:
            raise ValueError(f"Acción de Impress desconocida: {name}")
        handler(args)

    def _pages(self):
        return self.doc.getDrawPages()

    @staticmethod
    def _slide_index(index: Any) -> int:
        if isinstance(index, bool):
            raise ValueError("El número de diapositiva no es válido.")
        if isinstance(index, int):
            return index
        if isinstance(index, float):
            if not index.is_integer():
                raise ValueError("El número de diapositiva debe ser entero.")
            return int(index)
        if isinstance(index, str) and index.strip().isdigit():
            return int(index.strip())
        raise ValueError("El número de diapositiva no es válido.")

    def _page(self, index: Any):
        pages = self._pages()
        count = pages.getCount()
        if count == 0:
            raise ValueError("La presentación no tiene diapositivas.")
        position = self._slide_index(index)
        if position < 1 or position > count:
            raise ValueError(f"La diapositiva {position} no existe (hay {count}).")
        return pages.getByIndex(position - 1)

    def _new_page(self):
        pages = self._pages()
        return pages.insertNewByIndex(pages.getCount())

    @staticmethod
    def _point(x: int, y: int):
        point = uno.createUnoStruct("com.sun.star.awt.Point")
        point.X = x
        point.Y = y
        return point

    @staticmethod
    def _size(width: int, height: int):
        size = uno.createUnoStruct("com.sun.star.awt.Size")
        size.Width = width
        size.Height = height
        return size

    def _add_text_shape(
        self,
        page: Any,
        text: str,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        font_size: float | None = None,
        bold: bool = False,
        color: int | None = None,
        name: str = "",
    ) -> Any:
        shape = self.doc.createInstance("com.sun.star.drawing.TextShape")
        shape.Position = self._point(x, y)
        shape.Size = self._size(width, height)
        if name:
            shape.Name = name
        page.add(shape)
        shape.String = text
        if font_size is not None:
            set_optional(shape, "CharHeight", float(font_size))
        if bold:
            set_optional(shape, "CharWeight", BOLD)
        if color is not None:
            set_optional(shape, "CharColor", color)
        return shape

    def _add_title(self, page: Any, title: str) -> None:
        self._add_text_shape(
            page,
            title,
            *IMPRESS_TITLE_BOX,
            font_size=TITLE_FONT_SIZE,
            bold=True,
            name=TITLE_NAME,
        )

    def _add_bullets_shape(
        self,
        page: Any,
        items: Iterable[Any],
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        lines = [f"{BULLET_PREFIX}{item}" for item in items if str(item).strip()]
        if not lines:
            raise ValueError("La lista de viñetas está vacía.")
        self._add_text_shape(
            page,
            "\n".join(lines),
            x,
            y,
            width,
            height,
            font_size=20.0,
            name=BODY_NAME,
        )

    @staticmethod
    def _find_shape(page: Any, service: str) -> Any | None:
        for index in range(page.getCount()):
            shape = page.getByIndex(index)
            try:
                if shape.supportsService(service):
                    return shape
            except Exception as exc:
                _LOG.debug("No se pudo comprobar el servicio de una forma: %s", exc)
        return None

    def _set_title_text(self, page: Any, title: str) -> None:
        shape = self._find_shape(page, "com.sun.star.presentation.TitleTextShape")
        if shape is None:
            for index in range(page.getCount()):
                candidate = page.getByIndex(index)
                if getattr(candidate, "Name", "") == TITLE_NAME:
                    shape = candidate
                    break
        if shape is None:
            self._add_title(page, title)
            return
        shape.String = title
        set_optional(shape, "CharHeight", TITLE_FONT_SIZE)
        set_optional(shape, "CharWeight", BOLD)

    @staticmethod
    def _bullet_lines(items: Iterable[Any]) -> str:
        lines = [str(item).strip() for item in items if str(item).strip()]
        if not lines:
            raise ValueError("La lista de viñetas está vacía.")
        return "\n".join(lines)

    def _set_or_add_bullets(
        self,
        page: Any,
        items: Iterable[Any],
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        text = self._bullet_lines(items)
        outliner = self._find_shape(page, "com.sun.star.presentation.OutlinerShape")
        if outliner is not None:
            current = str(getattr(outliner, "String", "") or "").strip()
            outliner.String = f"{current}\n{text}" if current else text
            return
        self._add_bullets_shape(page, items, x, y, width, height)

    def _set_notes(self, page: Any, notes: str) -> None:
        if not notes:
            return
        try:
            notes_page = page.getNotesPage()
        except Exception as exc:
            _LOG.warning("No se pudo abrir la página de notas: %s", exc)
            return
        for index in range(notes_page.getCount()):
            shape = notes_page.getByIndex(index)
            try:
                if shape.supportsService("com.sun.star.presentation.NotesShape"):
                    shape.String = notes
                    return
            except Exception as exc:
                _LOG.debug("No se pudo escribir la nota: %s", exc)
        _LOG.warning("La diapositiva no tiene una forma de notas disponible.")

    def impress_add_slide(self, args: dict[str, Any]) -> None:
        layout_name = str(args.get("layout") or "title_content").strip().lower()
        if layout_name not in LAYOUTS:
            raise ValueError(f"Disposición desconocida: {layout_name}.")
        page = self._new_page()
        page.Layout = LAYOUTS[layout_name]
        title = str(args.get("title", "") or "").strip()
        content = args.get("content")
        if layout_name != "blank" and title:
            self._set_title_text(page, title)
        if layout_name == "title_content" and isinstance(content, list) and content:
            self._set_or_add_bullets(page, content, *IMPRESS_CONTENT_BOX)
        elif layout_name == "title" and isinstance(content, list) and content:
            self._set_or_add_bullets(page, content, *IMPRESS_CONTENT_BOX)
        self._set_notes(page, str(args.get("notes", "") or ""))

    def impress_set_title(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        title = str(args.get("title", "") or "")
        if not title.strip():
            raise ValueError("El título no puede estar vacío.")
        self._set_title_text(page, title)

    def impress_add_text(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        text = str(args.get("text", "") or "")
        if not text.strip():
            raise ValueError("El texto no puede estar vacío.")
        style = str(args.get("style", "body"))
        is_title = style == "title"
        self._add_text_shape(
            page,
            text,
            cm_to_100mm(args.get("x_cm"), IMPRESS_TEXT_BOX[0], label="La posición X"),
            cm_to_100mm(args.get("y_cm"), IMPRESS_TEXT_BOX[1], label="La posición Y"),
            cm_to_100mm(args.get("width_cm"), IMPRESS_TEXT_BOX[2], 0.1, 100.0, "El ancho"),
            cm_to_100mm(args.get("height_cm"), IMPRESS_TEXT_BOX[3], 0.1, 100.0, "La altura"),
            font_size=TITLE_FONT_SIZE if is_title else 20.0,
            bold=is_title,
        )

    def impress_add_bullets(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        items = args.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("La lista de viñetas está vacía.")
        title = str(args.get("title", "") or "").strip()
        if title:
            self._set_title_text(page, title)
        self._set_or_add_bullets(
            page,
            items,
            cm_to_100mm(args.get("x_cm"), IMPRESS_CONTENT_BOX[0], label="La posición X"),
            cm_to_100mm(args.get("y_cm"), IMPRESS_CONTENT_BOX[1], label="La posición Y"),
            cm_to_100mm(args.get("width_cm"), IMPRESS_CONTENT_BOX[2], 0.1, 100.0, "El ancho"),
            cm_to_100mm(args.get("height_cm"), IMPRESS_CONTENT_BOX[3], 0.1, 100.0, "La altura"),
        )

    def impress_insert_image(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        path = validate_image_path(args.get("path"))
        shape = self.doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
        shape.Position = self._point(
            cm_to_100mm(args.get("x_cm"), IMPRESS_TEXT_BOX[0], label="La posición X"),
            cm_to_100mm(args.get("y_cm"), IMPRESS_TEXT_BOX[1], label="La posición Y"),
        )
        shape.Size = self._size(
            cm_to_100mm(
                bounded_float(args.get("width_cm"), 12.0, 0.1, 100, "El ancho"),
                IMPRESS_TEXT_BOX[2],
                0.1,
                100.0,
                "El ancho",
            ),
            cm_to_100mm(
                bounded_float(args.get("height_cm"), 9.0, 0.1, 100, "La altura"),
                IMPRESS_TEXT_BOX[3],
                0.1,
                100.0,
                "La altura",
            ),
        )
        page.add(shape)
        shape.GraphicURL = uno.systemPathToFileUrl(path)

    @staticmethod
    def _cell_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Sí" if value else "No"
        return str(value)

    def _write_table(self, model: Any, data: list[list[str]], width: int) -> bool:
        rows = len(data)
        columns = len(data[0])
        try:
            if rows > 1:
                model.getRows().insertByIndex(0, rows - 1)
            if columns > 1:
                model.getColumns().insertByIndex(0, columns - 1)
        except Exception as exc:
            _LOG.warning("No se pudo ajustar el tamaño de la tabla de Impress: %s", exc)
            return False
        for row_index, row in enumerate(data):
            for column_index, value in enumerate(row):
                model.getCellByPosition(column_index, row_index).setString(value)
        try:
            column_width = max(1000, width // columns)
            for column_index in range(columns):
                model.getColumns().getByIndex(column_index).Width = column_width
        except Exception as exc:
            _LOG.debug("No se pudo ajustar el ancho de las columnas: %s", exc)
        return True

    def _add_fallback_table(self, page: Any, data: list[list[str]], x: int, y: int, width: int, height: int) -> None:
        text = "\n".join("\t".join(row) for row in data)
        self._add_text_shape(
            page,
            text,
            x,
            y,
            width,
            height,
            font_size=16.0,
            name=BODY_NAME,
        )

    def impress_insert_table(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        raw = args.get("data")
        if not isinstance(raw, list) or not raw:
            raise ValueError("La tabla necesita al menos una fila de datos.")
        data: list[list[str]] = []
        columns = 0
        for row in raw:
            if not isinstance(row, list):
                raise ValueError("Cada fila de la tabla debe ser una lista.")
            values = [self._cell_text(value) for value in row]
            data.append(values)
            columns = max(columns, len(values))
        if columns == 0:
            raise ValueError("La tabla necesita al menos una columna.")
        if len(data) > 30 or columns > 12:
            raise ValueError("La tabla es demasiado grande para una diapositiva (máximo 30x12).")
        data = [row + [""] * (columns - len(row)) for row in data]

        x = cm_to_100mm(args.get("x_cm"), IMPRESS_TABLE_BOX[0], label="La posición X")
        y = cm_to_100mm(args.get("y_cm"), IMPRESS_TABLE_BOX[1], label="La posición Y")
        width = cm_to_100mm(args.get("width_cm"), IMPRESS_TABLE_BOX[2], 0.1, 100.0, "El ancho")
        height = cm_to_100mm(args.get("height_cm"), IMPRESS_TABLE_BOX[3], 0.1, 100.0, "La altura")

        shape = None
        try:
            shape = self.doc.createInstance("com.sun.star.drawing.TableShape")
            shape.Position = self._point(x, y)
            shape.Size = self._size(width, height)
            page.add(shape)
            model = shape.Model
            if model is None:
                raise ValueError("La tabla nativa no está disponible.")
        except Exception as exc:
            _LOG.warning("Se usará texto con tabulaciones porque TableShape falló: %s", exc)
            if shape is not None:
                try:
                    page.remove(shape)
                except Exception as remove_error:
                    _LOG.debug("No se pudo retirar la tabla fallida: %s", remove_error)
            self._add_fallback_table(page, data, x, y, width, height)
            return

        if not self._write_table(model, data, width):
            try:
                page.remove(shape)
            except Exception as remove_error:
                _LOG.debug("No se pudo retirar la tabla incompleta: %s", remove_error)
            self._add_fallback_table(page, data, x, y, width, height)
