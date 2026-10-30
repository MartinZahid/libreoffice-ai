"""OpenAI tool definitions and argument validation for document actions."""

from __future__ import annotations

import json
from typing import Any


class ToolError(ValueError):
    """Raised when a model tool call is malformed."""


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


_NUMBER = {"type": "number"}


TEXT_STYLE = {
    "type": "string",
    "enum": ["body", "title", "heading1", "heading2", "heading3", "quote"],
    "description": "Estilo de párrafo. Usa body para texto normal.",
}

POSITION = {
    "type": "string",
    "enum": ["selection", "cursor", "start", "end"],
    "description": "Dónde insertar. selection reemplaza la selección actual.",
}

ALIGN = {
    "type": "string",
    "enum": ["left", "center", "right", "justify"],
    "description": "Alineación horizontal.",
}

COLOR = {
    "type": "string",
    "description": "Color en formato hexadecimal #RRGGBB.",
}


TOOLS: list[dict[str, Any]] = [
    _tool(
        "writer_insert_text",
        "Inserta texto en un documento Writer. Puede crear párrafos y encabezados.",
        {
            "text": {"type": "string", "description": "Texto a insertar. Usa \\n para separar párrafos."},
            "position": POSITION,
            "style": TEXT_STYLE,
            "new_paragraph": {"type": "boolean", "description": "Añadir un párrafo nuevo antes de insertar."},
        },
        ["text"],
    ),
    _tool(
        "writer_rewrite_selection",
        "Reemplaza el texto seleccionado en Writer por una versión nueva.",
        {
            "text": {"type": "string", "description": "Texto nuevo que reemplaza la selección."},
            "style": TEXT_STYLE,
        },
        ["text"],
    ),
    _tool(
        "writer_find_replace",
        "Busca texto en Writer y lo reemplaza, en todo el documento o solo en la selección.",
        {
            "find": {"type": "string"},
            "replace": {"type": "string"},
            "all": {"type": "boolean", "description": "True para reemplazar todas las apariciones."},
        },
        ["find", "replace"],
    ),
    _tool(
        "writer_insert_table",
        "Inserta una tabla en Writer a partir de una matriz de filas y columnas.",
        {
            "data": {
                "type": "array",
                "description": "Matriz de filas. Cada fila es una lista de celdas.",
                "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
            },
            "header": {"type": "boolean", "description": "Usar la primera fila como encabezado."},
            "style": {"type": "string", "description": "Nombre de estilo de tabla de LibreOffice, por ejemplo Default Style."},
            "position": POSITION,
        },
        ["data"],
    ),
    _tool(
        "writer_insert_list",
        "Inserta una lista con viñetas o numerada en Writer.",
        {
            "items": {"type": "array", "items": {"type": "string"}},
            "ordered": {"type": "boolean"},
            "position": POSITION,
        },
        ["items"],
    ),
    _tool(
        "writer_format",
        "Aplica formato a la selección, al párrafo actual o a todo el documento Writer.",
        {
            "target": {"type": "string", "enum": ["selection", "paragraph", "all"]},
            "bold": {"type": "boolean"},
            "italic": {"type": "boolean"},
            "underline": {"type": "boolean"},
            "font_name": {"type": "string"},
            "font_size": {"type": "number"},
            "color": COLOR,
            "align": ALIGN,
        },
    ),
    _tool(
        "writer_insert_page_break",
        "Inserta un salto de página en Writer.",
        {},
    ),
    _tool(
        "writer_insert_image",
        "Inserta una imagen local en Writer.",
        {
            "path": {"type": "string", "description": "Ruta absoluta del archivo de imagen."},
            "width_cm": _NUMBER,
            "height_cm": _NUMBER,
            "position": POSITION,
        },
        ["path"],
    ),
    _tool(
        "writer_insert_toc",
        "Inserta un índice de contenido al principio del documento Writer.",
        {},
    ),
    _tool(
        "calc_write_range",
        "Escribe valores o fórmulas en un rango de Calc.",
        {
            "sheet": {"type": "string", "description": "Hoja destino. Si se omite, la hoja activa."},
            "start_cell": {"type": "string", "description": "Celda inicial, por ejemplo A1."},
            "values": {
                "type": "array",
                "description": "Matriz de filas con valores. Las cadenas que empiezan por = se tratan como fórmulas.",
                "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
            },
        },
        ["start_cell", "values"],
    ),
    _tool(
        "calc_create_table",
        "Crea una tabla con encabezado en Calc y aplica un formato básico.",
        {
            "sheet": {"type": "string"},
            "start_cell": {"type": "string"},
            "data": {
                "type": "array",
                "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
            },
            "header": {"type": "boolean"},
        },
        ["start_cell", "data"],
    ),
    _tool(
        "calc_insert_rows",
        "Inserta filas en una hoja de Calc.",
        {
            "sheet": {"type": "string"},
            "index": {"type": "number", "description": "Número de fila 1-based donde insertar."},
            "count": {"type": "number"},
        },
        ["index"],
    ),
    _tool(
        "calc_insert_columns",
        "Inserta columnas en una hoja de Calc.",
        {
            "sheet": {"type": "string"},
            "index": {"type": "number", "description": "Número de columna 1-based donde insertar."},
            "count": {"type": "number"},
        },
        ["index"],
    ),
    _tool(
        "calc_format_range",
        "Aplica formato a un rango de Calc.",
        {
            "sheet": {"type": "string"},
            "range": {"type": "string", "description": "Rango, por ejemplo A1:C10."},
            "bold": {"type": "boolean"},
            "italic": {"type": "boolean"},
            "font_size": _NUMBER,
            "font_color": COLOR,
            "background_color": COLOR,
            "number_format": {"type": "string"},
            "align": ALIGN,
            "border": {"type": "boolean"},
        },
        ["range"],
    ),
    _tool(
        "calc_set_column_width",
        "Ajusta el ancho de una o varias columnas de Calc.",
        {
            "sheet": {"type": "string"},
            "columns": {"type": "string", "description": "Letras de columna, por ejemplo A o A:C."},
            "width_cm": _NUMBER,
        },
        ["columns", "width_cm"],
    ),
    _tool(
        "calc_sort_range",
        "Ordena un rango de Calc por una columna.",
        {
            "sheet": {"type": "string"},
            "range": {"type": "string"},
            "column": {"type": "number", "description": "Columna 1-based dentro del rango."},
            "ascending": {"type": "boolean"},
        },
        ["range", "column"],
    ),
    _tool(
        "calc_add_sheet",
        "Añade una hoja nueva a un libro de Calc.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "impress_add_slide",
        "Añade una diapositiva nueva a Impress.",
        {
            "layout": {"type": "string", "enum": ["title", "title_content", "title_only", "blank"]},
            "title": {"type": "string"},
            "content": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"},
        },
    ),
    _tool(
        "impress_set_title",
        "Cambia el título de una diapositiva de Impress.",
        {
            "slide_index": {"type": "number", "description": "Número de diapositiva 1-based."},
            "title": {"type": "string"},
        },
        ["slide_index", "title"],
    ),
    _tool(
        "impress_add_text",
        "Añade un cuadro de texto libre a una diapositiva de Impress.",
        {
            "slide_index": {"type": "number"},
            "text": {"type": "string"},
            "x_cm": _NUMBER,
            "y_cm": _NUMBER,
            "width_cm": _NUMBER,
            "height_cm": _NUMBER,
            "style": {"type": "string", "enum": ["body", "title"]},
        },
        ["slide_index", "text"],
    ),
    _tool(
        "impress_add_bullets",
        "Añade una lista de viñetas a una diapositiva de Impress.",
        {
            "slide_index": {"type": "number"},
            "items": {"type": "array", "items": {"type": "string"}},
            "title": {"type": "string"},
            "x_cm": _NUMBER,
            "y_cm": _NUMBER,
            "width_cm": _NUMBER,
            "height_cm": _NUMBER,
        },
        ["slide_index", "items"],
    ),
    _tool(
        "impress_insert_image",
        "Inserta una imagen local en una diapositiva de Impress.",
        {
            "slide_index": {"type": "number"},
            "path": {"type": "string"},
            "x_cm": _NUMBER,
            "y_cm": _NUMBER,
            "width_cm": _NUMBER,
            "height_cm": _NUMBER,
        },
        ["slide_index", "path"],
    ),
    _tool(
        "impress_insert_table",
        "Inserta una tabla en una diapositiva de Impress.",
        {
            "slide_index": {"type": "number"},
            "data": {
                "type": "array",
                "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
            },
            "x_cm": _NUMBER,
            "y_cm": _NUMBER,
            "width_cm": _NUMBER,
            "height_cm": _NUMBER,
        },
        ["slide_index", "data"],
    ),
]


TOOLS_BY_NAME = {tool["function"]["name"]: tool for tool in TOOLS}


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True


def _validate_value(name: str, value: Any, schema: dict[str, Any], path: str) -> None:
    expected = schema.get("type")
    if expected:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, item) for item in allowed):
            raise ToolError(f"El argumento {path} de {name} tiene un tipo inválido.")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolError(f"El argumento {path} de {name} no es un valor permitido.")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_value(name, item, schema["items"], f"{path}[{index}]")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ToolError(f"El argumento {path} de {name} contiene campos no permitidos: {', '.join(extra)}.")
        for key, item in value.items():
            if key in properties and item is not None:
                _validate_value(name, item, properties[key], f"{path}.{key}")


def parse_arguments(name: str, raw_arguments: Any) -> dict[str, Any]:
    """Parse and validate the JSON arguments of a tool call."""
    if name not in TOOLS_BY_NAME:
        raise ToolError(f"Herramienta desconocida: {name}")

    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ToolError(f"Argumentos JSON inválidos para {name}: {exc.msg}") from exc
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    elif raw_arguments is None:
        arguments = {}
    else:
        raise ToolError(f"Argumentos inválidos para {name}.")

    if not isinstance(arguments, dict):
        raise ToolError(f"Los argumentos de {name} deben ser un objeto JSON.")

    schema = TOOLS_BY_NAME[name]["function"]["parameters"]
    for required in schema.get("required", []):
        if required not in arguments or arguments[required] in (None, ""):
            raise ToolError(f"Falta el argumento obligatorio '{required}' en {name}.")

    _validate_value(name, arguments, schema, "arguments")
    return arguments
