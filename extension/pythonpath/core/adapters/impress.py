"""Impress actions implemented with the LibreOffice UNO API."""

from __future__ import annotations

import os
from typing import Any, Iterable

import uno

from .common import cm_to_100mm, set_optional

TITLE_NAME = "LibreOfficeAI_Title"
BODY_NAME = "LibreOfficeAI_Body"
BULLET_PREFIX = "• "


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

    def _page(self, index: Any):
        pages = self._pages()
        count = pages.getCount()
        if count == 0:
            raise ValueError("La presentación no tiene diapositivas.")
        try:
            position = int(index)
        except (TypeError, ValueError):
            raise ValueError("El número de diapositiva no es válido.")
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
            set_optional(shape, "CharWeight", 150.0)
        if color is not None:
            set_optional(shape, "CharColor", color)
        return shape

    def _add_title(self, page: Any, title: str) -> None:
        self._add_text_shape(
            page,
            title,
            2000,
            900,
            22000,
            3000,
            font_size=30.0,
            bold=True,
            name=TITLE_NAME,
        )

    def _add_bullets_shape(self, page: Any, items: Iterable[Any], x: int, y: int, width: int, height: int) -> None:
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
            except Exception:
                continue
        return None

    def _set_notes(self, page: Any, notes: str) -> None:
        if not notes:
            return
        try:
            notes_page = page.getNotesPage()
        except Exception:
            return
        for index in range(notes_page.getCount()):
            shape = notes_page.getByIndex(index)
            try:
                if shape.supportsService("com.sun.star.presentation.NotesShape"):
                    shape.String = notes
                    return
            except Exception:
                continue

    def impress_add_slide(self, args: dict[str, Any]) -> None:
        page = self._new_page()
        layout = str(args.get("layout", "title_content"))
        title = str(args.get("title", "") or "").strip()
        content = args.get("content")

        if layout != "blank" and title:
            self._add_title(page, title)
        if layout == "title_content" and isinstance(content, list) and content:
            self._add_bullets_shape(page, content, 2000, 4800, 22000, 13500)
        self._set_notes(page, str(args.get("notes", "") or ""))

    def impress_set_title(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        title = str(args.get("title", "") or "")
        if not title.strip():
            raise ValueError("El título no puede estar vacío.")
        shape = self._find_shape(page, "com.sun.star.presentation.TitleTextShape")
        if shape is None:
            for index in range(page.getCount()):
                candidate = page.getByIndex(index)
                if getattr(candidate, "Name", "") == TITLE_NAME:
                    shape = candidate
                    break
        if shape is not None:
            shape.String = title
            return
        self._add_title(page, title)

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
            cm_to_100mm(args.get("x_cm"), 2000),
            cm_to_100mm(args.get("y_cm"), 5000),
            cm_to_100mm(args.get("width_cm"), 22000),
            cm_to_100mm(args.get("height_cm"), 10000),
            font_size=28.0 if is_title else 20.0,
            bold=is_title,
        )

    def impress_add_bullets(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        items = args.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("La lista de viñetas está vacía.")
        title = str(args.get("title", "") or "").strip()
        if title:
            self._add_title(page, title)
        self._add_bullets_shape(
            page,
            items,
            cm_to_100mm(args.get("x_cm"), 2000),
            cm_to_100mm(args.get("y_cm"), 5000),
            cm_to_100mm(args.get("width_cm"), 22000),
            cm_to_100mm(args.get("height_cm"), 12000),
        )

    def impress_insert_image(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        path = os.path.abspath(str(args.get("path", "")))
        if not os.path.isfile(path):
            raise ValueError(f"No existe la imagen: {path}")
        shape = self.doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
        shape.Position = self._point(
            cm_to_100mm(args.get("x_cm"), 2000),
            cm_to_100mm(args.get("y_cm"), 5000),
        )
        shape.Size = self._size(
            cm_to_100mm(args.get("width_cm"), 12000),
            cm_to_100mm(args.get("height_cm"), 9000),
        )
        page.add(shape)
        shape.GraphicURL = uno.systemPathToFileUrl(path)

    def impress_insert_table(self, args: dict[str, Any]) -> None:
        page = self._page(args.get("slide_index"))
        data = args.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("La tabla necesita al menos una fila de datos.")
        rows = []
        columns = 0
        for row in data:
            if not isinstance(row, list):
                raise ValueError("Cada fila de la tabla debe ser una lista.")
            rows.append(["" if value is None else str(value) for value in row])
            columns = max(columns, len(row))
        if columns == 0:
            raise ValueError("La tabla necesita al menos una columna.")
        if len(rows) > 30 or columns > 12:
            raise ValueError("La tabla es demasiado grande para una diapositiva (máximo 30x12).")
        rows = [row + [""] * (columns - len(row)) for row in rows]

        text = "\n".join("\t".join(row) for row in rows)
        self._add_text_shape(
            page,
            text,
            cm_to_100mm(args.get("x_cm"), 2000),
            cm_to_100mm(args.get("y_cm"), 5000),
            cm_to_100mm(args.get("width_cm"), 22000),
            cm_to_100mm(args.get("height_cm"), 12000),
            font_size=16.0,
            name=BODY_NAME,
        )


