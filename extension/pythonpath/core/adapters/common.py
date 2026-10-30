"""Helpers shared by the Writer, Calc and Impress adapters."""

from __future__ import annotations

import re
from typing import Any


CELL_RE = re.compile(r"^\$?([A-Za-z]+)\$?(\d+)$")


def cm_to_100mm(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return int(round(float(value) * 1000))


def coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "si", "sí")
    return bool(value)


def parse_color(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"Color inválido: {value}. Usa #RRGGBB.")
    return int(text, 16)


def set_optional(obj: Any, name: str, value: Any) -> None:
    if value is None:
        return
    try:
        setattr(obj, name, value)
    except Exception:
        pass


def column_letters(index: int) -> str:
    if index < 0:
        raise ValueError("La columna no puede ser negativa.")
    letters = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def cell_name(column: int, row: int) -> str:
    return f"{column_letters(column)}{row + 1}"


def parse_cell(value: str) -> tuple[int, int]:
    match = CELL_RE.match((value or "").strip())
    if not match:
        raise ValueError(f"Celda inválida: {value}. Usa el formato A1.")
    letters, row = match.groups()
    column = 0
    for char in letters.upper():
        column = column * 26 + (ord(char) - 64)
    return column - 1, int(row) - 1


def parse_range(value: str) -> tuple[str, str]:
    text = (value or "").replace("$", "").strip()
    if ":" in text:
        start, end = text.split(":", 1)
    else:
        start = end = text
    parse_cell(start)
    parse_cell(end)
    return start.upper(), end.upper()


def find_style(doc: Any, family_name: str, candidates: list[str]) -> str | None:
    try:
        family = doc.getStyleFamilies().getByName(family_name)
    except Exception:
        return None
    for candidate in candidates:
        try:
            if family.hasByName(candidate):
                return candidate
        except Exception:
            continue
    return None
