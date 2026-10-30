"""Helpers shared by the Writer, Calc and Impress adapters."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse


CELL_RE = re.compile(r"^\$?([A-Za-z]+)\$?(\d+)$")
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".svg",
    ".webp",
    ".tif",
    ".tiff",
}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Se esperaba un número entero, no {value!r}.") from exc


def bounded_float(value: Any, default: float, minimum: float, maximum: float, label: str) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} no es un número válido.") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} debe estar entre {minimum:g} y {maximum:g}.")
    return number


def validate_image_path(value: Any) -> str:
    """Accept only an existing local image with a supported extension."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("Falta la ruta de la imagen.")
    if text.startswith("\\\\") or text.startswith("//"):
        raise ValueError("Las rutas de red no están permitidas. Usa una imagen local.")
    parsed = urlparse(text)
    if parsed.scheme and len(parsed.scheme) > 1:
        raise ValueError("Usa una ruta local, no una URL.")
    if not os.path.isabs(text):
        raise ValueError("La ruta de la imagen debe ser absoluta.")
    path = os.path.realpath(text)
    if not os.path.isfile(path):
        raise ValueError(f"No existe la imagen: {path}")
    extension = os.path.splitext(path)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValueError(f"Formato de imagen no compatible: {extension or 'sin extensión'}.")
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise ValueError(f"No se pudo leer la imagen: {path}") from exc
    if size > MAX_IMAGE_BYTES:
        raise ValueError("La imagen es demasiado grande (máximo 20 MB).")
    return path


def supports_service(doc: Any, service: str) -> bool:
    try:
        return bool(doc.supportsService(service))
    except Exception:
        return False


def document_kind(doc: Any) -> str:
    if supports_service(doc, "com.sun.star.text.TextDocument") or supports_service(
        doc, "com.sun.star.text.WebDocument"
    ):
        return "writer"
    if supports_service(doc, "com.sun.star.sheet.SpreadsheetDocument"):
        return "calc"
    if supports_service(doc, "com.sun.star.presentation.PresentationDocument"):
        return "impress"
    if supports_service(doc, "com.sun.star.drawing.DrawingDocument"):
        return "draw"
    return "unknown"


def selection_text(selection: Any) -> str:
    if selection is None:
        return ""
    try:
        return str(selection.getString() or "")
    except Exception:
        pass
    try:
        count = int(selection.getCount())
    except Exception:
        return ""
    parts = []
    for index in range(count):
        try:
            part = selection.getByIndex(index)
            text = str(part.getString() or "")
        except Exception:
            continue
        if text:
            parts.append(text)
    return "\n".join(parts)


def first_selection_range(selection: Any) -> Any | None:
    if selection is None:
        return None
    try:
        selection.getString()
        return selection
    except Exception:
        pass
    try:
        if int(selection.getCount()) >= 1:
            return selection.getByIndex(0)
    except Exception:
        pass
    return None


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
