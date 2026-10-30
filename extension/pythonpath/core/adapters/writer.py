"""Writer actions implemented with the LibreOffice UNO API."""

from __future__ import annotations

from typing import Any

import uno

from .common import (
    bounded_float,
    cell_name,
    cm_to_100mm,
    coerce_bool,
    find_style,
    first_selection_range,
    parse_color,
    selection_text,
    set_optional,
    validate_image_path,
)


def _constant(name: str, default: Any = None) -> Any:
    try:
        return uno.getConstantByName(name)
    except Exception:
        return default


PARAGRAPH_BREAK = _constant("com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK", 0)
PAGE_BEFORE = _constant("com.sun.star.style.BreakType.PAGE_BEFORE", 4)
AS_CHARACTER = _constant("com.sun.star.text.TextContentAnchorType.AS_CHARACTER", 1)
BOLD = 150.0
NORMAL = 100.0
ITALIC = 2
SLANT_NONE = 0
UNDERLINE_SINGLE = 1
UNDERLINE_NONE = 0
ALIGN = {"left": 0, "right": 1, "justify": 2, "center": 3}


STYLE_CANDIDATES = {
    "body": ["Standard", "Default Paragraph Style", "Estándar"],
    "title": ["Title", "Título"],
    "heading1": ["Heading 1", "Encabezado 1"],
    "heading2": ["Heading 2", "Encabezado 2"],
    "heading3": ["Heading 3", "Encabezado 3"],
    "quote": ["Quotations", "Citas", "Block Text"],
}

LIST_STYLE_CANDIDATES = ["List 1", "Lista 1", "Numbering 1", "Numeración 1"]


class WriterAdapter:
    def __init__(self, doc: Any):
        self.doc = doc

    def execute(self, action: dict[str, Any]) -> None:
        name = action["name"]
        args = action.get("arguments", {})
        handler = getattr(self, name, None)
        if handler is None:
            raise ValueError(f"Acción de Writer desconocida: {name}")
        handler(args)

    def _view_cursor(self):
        controller = self.doc.getCurrentController()
        try:
            cursor = controller.getViewCursor()
            if cursor is not None:
                return cursor
        except Exception:
            pass
        return self.doc.getText().createTextCursor()

    def _text_cursor(self, at: str):
        cursor = self.doc.getText().createTextCursor()
        if at == "start":
            cursor.gotoStart(False)
        else:
            cursor.gotoEnd(False)
        return cursor

    def _paragraph_cursor(self):
        cursor = self.doc.getText().createTextCursorByRange(self._view_cursor())
        cursor.gotoStartOfParagraph(False)
        cursor.gotoEndOfParagraph(True)
        return cursor

    def _selection(self):
        try:
            selection = self.doc.getCurrentController().getSelection()
            return first_selection_range(selection)
        except Exception:
            return None

    def _target(self, position: str):
        if position == "start":
            return self._text_cursor("start"), False
        if position == "end":
            return self._text_cursor("end"), False
        if position in ("selection", "cursor"):
            selection = self._selection()
            if position == "selection" and selection is not None:
                return selection, bool(selection_text(selection))
            return self._view_cursor(), False
        return self._view_cursor(), False

    def _style_paragraph(self, cursor: Any, style: str) -> None:
        if style not in STYLE_CANDIDATES:
            return
        paragraph_style = find_style(self.doc, "ParagraphStyles", STYLE_CANDIDATES[style])
        if paragraph_style is not None and style != "body":
            set_optional(cursor, "ParaStyleName", paragraph_style)

    def _insert_text_parts(self, cursor: Any, text: str, style: str) -> None:
        self._style_paragraph(cursor, style)
        lines = str(text).split("\n")
        for index, line in enumerate(lines):
            cursor.getText().insertString(cursor, line, False)
            if index < len(lines) - 1:
                cursor.getText().insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
                self._style_paragraph(cursor, style)

    def writer_insert_text(self, args: dict[str, Any]) -> None:
        text = str(args.get("text", ""))
        if not text:
            raise ValueError("El texto no puede estar vacío.")
        cursor, replace = self._target(str(args.get("position", "cursor")))
        if replace:
            cursor.setString("")
        if coerce_bool(args.get("new_paragraph"), False):
            cursor.getText().insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
        self._insert_text_parts(cursor, text, str(args.get("style", "body")))

    def writer_rewrite_selection(self, args: dict[str, Any]) -> None:
        text = str(args.get("text", ""))
        if not text:
            raise ValueError("El texto no puede estar vacío.")
        selection = self._selection()
        cursor = selection if selection is not None else self._view_cursor()
        cursor.setString("")
        self._insert_text_parts(cursor, text, str(args.get("style", "body")))

    def writer_find_replace(self, args: dict[str, Any]) -> None:
        find = str(args.get("find", ""))
        replace = str(args.get("replace", ""))
        if not find:
            raise ValueError("El texto a buscar no puede estar vacío.")
        descriptor = self.doc.createSearchDescriptor()
        descriptor.SearchString = find
        descriptor.SearchCaseSensitive = False
        descriptor.SearchRegularExpression = False
        found = self.doc.findFirst(descriptor)
        if found is None:
            raise ValueError(f"No se encontró el texto: {find}")
        replace_all = coerce_bool(args.get("all"), False)
        while found is not None:
            found.setString(replace)
            if not replace_all:
                break
            found = self.doc.findNext(found.getEnd(), descriptor)

    def writer_insert_table(self, args: dict[str, Any]) -> None:
        data = args.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("La tabla necesita al menos una fila de datos.")
        rows = []
        for row in data:
            if not isinstance(row, list):
                raise ValueError("Cada fila de la tabla debe ser una lista.")
            rows.append(row)
        columns = max(len(row) for row in rows)
        if columns == 0:
            raise ValueError("La tabla necesita al menos una columna.")
        if len(rows) > 200 or columns > 40:
            raise ValueError("La tabla es demasiado grande (máximo 200x40).")
        rows = [row + [""] * (columns - len(row)) for row in rows]

        table = self.doc.createInstance("com.sun.star.text.TextTable")
        table.initialize(len(rows), columns)
        style = args.get("style")
        if style:
            set_optional(table, "TableStyleName", str(style))

        cursor, replace = self._target(str(args.get("position", "cursor")))
        if replace:
            cursor.setString("")
        self.doc.getText().insertTextContent(cursor, table, False)

        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                cell = table.getCellByName(cell_name(column_index, row_index))
                cell.setString("" if value is None else str(value))

        if coerce_bool(args.get("header"), False):
            for column_index in range(columns):
                cell = table.getCellByName(cell_name(column_index, 0))
                set_optional(cell, "CharWeight", BOLD)
                set_optional(cell, "CellBackColor", 0xE8EEF7)

    def writer_insert_list(self, args: dict[str, Any]) -> None:
        items = args.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("La lista necesita al menos un elemento.")
        cursor, replace = self._target(str(args.get("position", "cursor")))
        if replace:
            cursor.setString("")

        list_style = find_style(self.doc, "ParagraphStyles", LIST_STYLE_CANDIDATES)
        ordered = coerce_bool(args.get("ordered"), False)
        for index, item in enumerate(items):
            if index > 0:
                cursor.getText().insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
            if list_style is not None:
                set_optional(cursor, "ParaStyleName", list_style)
                prefix = ""
            else:
                prefix = f"{index + 1}. " if ordered else "• "
            cursor.getText().insertString(cursor, prefix + str(item), False)

    def writer_format(self, args: dict[str, Any]) -> None:
        target = str(args.get("target", "selection"))
        if target == "all":
            cursor = self.doc.getText().createTextCursor()
            cursor.gotoStart(False)
            cursor.gotoEnd(True)
        elif target == "paragraph":
            cursor = self._paragraph_cursor()
        else:
            cursor = self._selection()
            if cursor is None or not cursor.getString():
                cursor = self._paragraph_cursor()

        bold = args.get("bold")
        italic = args.get("italic")
        underline = args.get("underline")
        if bold is not None:
            set_optional(cursor, "CharWeight", BOLD if coerce_bool(bold) else NORMAL)
        if italic is not None:
            set_optional(cursor, "CharPosture", ITALIC if coerce_bool(italic) else SLANT_NONE)
        if underline is not None:
            set_optional(cursor, "CharUnderline", UNDERLINE_SINGLE if coerce_bool(underline) else UNDERLINE_NONE)
        if args.get("font_name"):
            set_optional(cursor, "CharFontName", str(args["font_name"]))
        if args.get("font_size") is not None:
            size = bounded_float(args["font_size"], 12.0, 4.0, 200.0, "El tamaño de fuente")
            set_optional(cursor, "CharHeight", size)
        color = parse_color(args.get("color"))
        if color is not None:
            set_optional(cursor, "CharColor", color)
        if args.get("align"):
            set_optional(cursor, "ParaAdjust", ALIGN.get(str(args["align"]), 0))

    def writer_insert_page_break(self, args: dict[str, Any]) -> None:
        cursor = self._paragraph_cursor()
        cursor.BreakType = PAGE_BEFORE

    def writer_insert_image(self, args: dict[str, Any]) -> None:
        path = validate_image_path(args.get("path"))
        graphic = self.doc.createInstance("com.sun.star.text.TextGraphicObject")
        graphic.GraphicURL = uno.systemPathToFileUrl(path)
        set_optional(graphic, "AnchorType", AS_CHARACTER)
        if args.get("width_cm") is not None:
            graphic.Width = cm_to_100mm(bounded_float(args["width_cm"], 0, 0.1, 100, "El ancho"))
        if args.get("height_cm") is not None:
            graphic.Height = cm_to_100mm(bounded_float(args["height_cm"], 0, 0.1, 100, "La altura"))
        cursor, replace = self._target(str(args.get("position", "cursor")))
        if replace:
            cursor.setString("")
        self.doc.getText().insertTextContent(cursor, graphic, False)

    def writer_insert_toc(self, args: dict[str, Any]) -> None:
        index = self.doc.createInstance("com.sun.star.text.ContentIndex")
        index.Title = "Índice"
        index.CreateFromOutline = True
        cursor = self._text_cursor("start")
        self.doc.getText().insertTextContent(cursor, index, False)
        try:
            self.doc.getDocumentIndexes().update()
        except Exception:
            pass
