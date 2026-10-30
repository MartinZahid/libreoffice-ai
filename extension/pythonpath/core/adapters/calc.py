"""Calc actions implemented with the LibreOffice UNO API."""

from __future__ import annotations

from typing import Any

import uno

from ..formula import validate_formula
from .common import (
    as_int,
    bounded_float,
    cm_to_100mm,
    coerce_bool,
    parse_cell,
    parse_color,
    parse_range,
    set_optional,
)

BOLD = 150.0
ITALIC = 2
SLANT_NONE = 0
ALIGN = {"left": 1, "center": 2, "right": 3, "justify": 4}


class CalcAdapter:
    def __init__(self, doc: Any):
        self.doc = doc

    def execute(self, action: dict[str, Any]) -> None:
        name = action["name"]
        args = action.get("arguments", {})
        handler = getattr(self, name, None)
        if handler is None:
            raise ValueError(f"Acción de Calc desconocida: {name}")
        handler(args)

    def _sheet(self, name: Any = None):
        if name:
            if not self.doc.Sheets.hasByName(str(name)):
                raise ValueError(f"No existe la hoja: {name}")
            return self.doc.Sheets.getByName(str(name))
        return self.doc.getCurrentController().getActiveSheet()

    @staticmethod
    def _set_cell(cell: Any, value: Any) -> None:
        if value is None:
            cell.setString("")
        elif isinstance(value, bool):
            cell.setValue(1.0 if value else 0.0)
        elif isinstance(value, (int, float)):
            cell.setValue(float(value))
        else:
            text = str(value)
            validate_formula(text)
            if text.startswith("="):
                cell.setFormula(text)
            else:
                cell.setString(text)

    def _write_values(self, sheet: Any, start_cell: str, values: Any) -> tuple[int, int, int, int]:
        if not isinstance(values, list) or not values:
            raise ValueError("values debe ser una matriz con al menos una fila.")
        for row in values:
            if not isinstance(row, list):
                raise ValueError("Cada fila de values debe ser una lista.")
            for value in row:
                if isinstance(value, str):
                    validate_formula(value)
        start_column, start_row = parse_cell(start_cell)
        max_columns = 0
        for row_index, row in enumerate(values):
            max_columns = max(max_columns, len(row))
            for column_index, value in enumerate(row):
                self._set_cell(
                    sheet.getCellByPosition(start_column + column_index, start_row + row_index),
                    value,
                )
        if max_columns == 0:
            raise ValueError("values necesita al menos una columna.")
        return start_column, start_row, max_columns, len(values)

    def _format_header(self, sheet: Any, start_column: int, start_row: int, columns: int) -> None:
        header = sheet.getCellRangeByPosition(
            start_column, start_row, start_column + columns - 1, start_row
        )
        set_optional(header, "CharWeight", BOLD)
        set_optional(header, "CellBackColor", 0xE8EEF7)
        for column in range(start_column, start_column + columns):
            set_optional(sheet.Columns.getByIndex(column), "OptimalWidth", True)

    def calc_write_range(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        self._write_values(sheet, str(args.get("start_cell", "A1")), args.get("values"))

    def calc_create_table(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        start_column, start_row, columns, _ = self._write_values(
            sheet, str(args.get("start_cell", "A1")), args.get("data")
        )
        if coerce_bool(args.get("header"), True):
            self._format_header(sheet, start_column, start_row, columns)

    def calc_insert_rows(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        count = max(1, min(as_int(args.get("count"), 1), 1000))
        index = max(1, as_int(args.get("index"), 1))
        index = min(index, sheet.Rows.getCount() + 1)
        sheet.Rows.insertByIndex(index - 1, count)

    def calc_insert_columns(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        count = max(1, min(as_int(args.get("count"), 1), 100))
        index = max(1, as_int(args.get("index"), 1))
        index = min(index, sheet.Columns.getCount() + 1)
        sheet.Columns.insertByIndex(index - 1, count)

    def _number_format_key(self, code: str, target: Any = None) -> int:
        formats = self.doc.getNumberFormats()
        try:
            locale = target.CharLocale if target is not None else None
        except Exception:
            locale = None
        if locale is None:
            locale = uno.createUnoStruct("com.sun.star.lang.Locale")
        key = formats.queryKey(code, locale, True)
        if key == -1:
            key = formats.addNew(code, locale)
        return key

    def calc_format_range(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        start, end = parse_range(str(args.get("range", "")))
        target = sheet.getCellRangeByName(f"{start}:{end}")

        if args.get("bold") is not None:
            set_optional(target, "CharWeight", BOLD if coerce_bool(args["bold"]) else 100.0)
        if args.get("italic") is not None:
            set_optional(target, "CharPosture", ITALIC if coerce_bool(args["italic"]) else SLANT_NONE)
        if args.get("font_size") is not None:
            size = bounded_float(args["font_size"], 12.0, 4.0, 200.0, "El tamaño de fuente")
            set_optional(target, "CharHeight", size)
        color = parse_color(args.get("font_color"))
        if color is not None:
            set_optional(target, "CharColor", color)
        background = parse_color(args.get("background_color"))
        if background is not None:
            set_optional(target, "CellBackColor", background)
        if args.get("align"):
            set_optional(target, "HoriJustify", ALIGN.get(str(args["align"]), 0))
        if args.get("number_format"):
            try:
                set_optional(target, "NumberFormat", self._number_format_key(str(args["number_format"]), target))
            except Exception:
                pass
        if coerce_bool(args.get("border"), False):
            border = uno.createUnoStruct("com.sun.star.table.BorderLine2")
            border.Color = 0x808080
            border.LineStyle = uno.getConstantByName("com.sun.star.table.BorderLineStyle.SOLID")
            border.LineWidth = 10
            border.OuterLineWidth = 10
            for name in ("TopBorder", "BottomBorder", "LeftBorder", "RightBorder"):
                set_optional(target, name, border)

    def calc_set_column_width(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        columns = str(args.get("columns", "")).replace("$", "").upper()
        if ":" in columns:
            first, last = columns.split(":", 1)
        else:
            first = last = columns
        start = parse_cell(first + "1")[0]
        end = parse_cell(last + "1")[0]
        if end < start:
            start, end = end, start
        width = cm_to_100mm(bounded_float(args.get("width_cm"), 0, 0.1, 100, "El ancho"))
        if width <= 0:
            raise ValueError("El ancho debe ser mayor que cero.")
        for index in range(start, end + 1):
            sheet.Columns.getByIndex(index).Width = width

    def calc_sort_range(self, args: dict[str, Any]) -> None:
        sheet = self._sheet(args.get("sheet"))
        start, end = parse_range(str(args.get("range", "")))
        target = sheet.getCellRangeByName(f"{start}:{end}")
        field = uno.createUnoStruct("com.sun.star.table.TableSortField")
        field.Field = max(0, as_int(args.get("column"), 1) - 1)
        field.IsAscending = coerce_bool(args.get("ascending"), True)
        field.IsCaseSensitive = False
        properties = []
        for name, value in (
            ("SortFields", (field,)),
            ("ContainsHeader", False),
            ("BindFormatsToContent", True),
        ):
            prop = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
            prop.Name = name
            prop.Value = value
            properties.append(prop)
        target.sort(tuple(properties))

    def calc_add_sheet(self, args: dict[str, Any]) -> None:
        name = str(args.get("name", "")).strip()
        if not name:
            raise ValueError("El nombre de la hoja no puede estar vacío.")
        if len(name) > 31 or any(character in name for character in "[]:*?/\\"):
            raise ValueError("El nombre de la hoja no es válido (máximo 31 caracteres sin []:*?/\\).")
        if self.doc.Sheets.hasByName(name):
            raise ValueError(f"Ya existe una hoja llamada {name}.")
        self.doc.Sheets.insertNewByName(name, self.doc.Sheets.getCount())
