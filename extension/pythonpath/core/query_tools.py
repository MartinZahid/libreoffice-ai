"""Read-only tools used by the agent for local folders and Internet research."""

from __future__ import annotations

import logging
import os
from typing import Any

from .adapters.common import IMAGE_EXTENSIONS, MAX_IMAGE_BYTES, coerce_bool
from .web import (
    WebError,
    download_image,
    fetch_web_page,
    search_images,
    search_web,
)

_LOG = logging.getLogger(__name__)

LOCAL_TOOL = "list_local_images"
WEB_TOOL_NAMES = ("search_web", "search_images", "fetch_web_page", "download_image")
QUERY_TOOL_NAMES = (LOCAL_TOOL,) + WEB_TOOL_NAMES
MAX_LOCAL_RESULTS = 500
MAX_WALK_DEPTH = 5


class QueryError(ValueError):
    """A read-only query could not be completed."""


def _clamp(value: Any, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise QueryError("El limite debe ser un numero entero.") from exc
    return max(minimum, min(number, maximum))


def _default_pictures_folder() -> str:
    home = os.path.expanduser("~")
    pictures = os.path.join(home, "Pictures")
    return pictures if os.path.isdir(pictures) else home


def _resolve_folder(value: Any) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        text = _default_pictures_folder()
    if "\x00" in text:
        raise QueryError("La ruta contiene caracteres no validos.")
    if text.startswith(("\\\\", "//")):
        raise QueryError("Las rutas de red no estan permitidas.")
    text = os.path.expandvars(os.path.expanduser(text))
    if not os.path.isabs(text):
        home = os.path.realpath(os.path.expanduser("~"))
        candidate = os.path.realpath(os.path.join(home, text))
        try:
            inside_home = os.path.normcase(os.path.commonpath([home, candidate])) == os.path.normcase(home)
        except ValueError:
            inside_home = False
        if not inside_home:
            raise QueryError("La ruta relativa debe estar dentro de tu carpeta personal.")
        text = candidate
    path = os.path.realpath(text)
    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() not in IMAGE_EXTENSIONS:
            raise QueryError("El archivo indicado no es una imagen compatible.")
        return path
    if not os.path.isdir(path):
        raise QueryError(f"No existe la carpeta: {path}")
    return path


def _image_info(path: str) -> dict[str, Any] | None:
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size > MAX_IMAGE_BYTES:
        return None
    return {
        "path": path,
        "name": os.path.basename(path),
        "size_kb": round(size / 1024, 1),
    }


def _scan_folder(path: str, recursive: bool, limit: int) -> tuple[list[dict[str, Any]], bool]:
    images: list[dict[str, Any]] = []
    truncated = False
    if os.path.isfile(path):
        info = _image_info(path)
        return ([info] if info else []), False

    if recursive:
        base_depth = path.rstrip(os.sep).count(os.sep)
        for root, directories, files in os.walk(path):
            depth = root.rstrip(os.sep).count(os.sep) - base_depth
            if depth >= MAX_WALK_DEPTH:
                directories[:] = []
            for name in sorted(files, key=str.lower):
                if os.path.splitext(name)[1].lower() not in IMAGE_EXTENSIONS:
                    continue
                info = _image_info(os.path.join(root, name))
                if info is None:
                    continue
                if len(images) >= limit:
                    truncated = True
                    break
                images.append(info)
            if truncated:
                break
    else:
        try:
            with os.scandir(path) as entries:
                names = sorted(
                    (entry.name for entry in entries if entry.is_file()),
                    key=str.lower,
                )
        except OSError as exc:
            raise QueryError(f"No se pudo leer la carpeta: {path}") from exc
        for name in names:
            if os.path.splitext(name)[1].lower() not in IMAGE_EXTENSIONS:
                continue
            info = _image_info(os.path.join(path, name))
            if info is None:
                continue
            if len(images) >= limit:
                truncated = True
                break
            images.append(info)
    return images, truncated


def list_local_images(path: Any = "", recursive: bool = False, limit: Any = 200) -> dict[str, Any]:
    folder = _resolve_folder(path)
    count = _clamp(limit, 200, 1, MAX_LOCAL_RESULTS)
    images, truncated = _scan_folder(folder, bool(recursive), count)
    result: dict[str, Any] = {
        "folder": folder,
        "count": len(images),
        "truncated": truncated,
        "images": images,
    }
    if not images:
        result["message"] = (
            "No se encontraron imagenes compatibles. Formatos: "
            + ", ".join(sorted(IMAGE_EXTENSIONS))
        )
    return result


class QueryRunner:
    """Execute read-only queries on the worker thread."""

    def __init__(self, config: Any):
        self.config = config
        self.enable_local_files = bool(getattr(config, "enable_local_files", True))
        self.enable_web_search = bool(getattr(config, "enable_web_search", True))

    def allows(self, name: str) -> bool:
        if name == LOCAL_TOOL:
            return self.enable_local_files
        if name in WEB_TOOL_NAMES:
            return self.enable_web_search
        return False

    def enabled_names(self) -> list[str]:
        return [name for name in QUERY_TOOL_NAMES if self.allows(name)]

    def run(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self.allows(name):
            raise QueryError(
                "Esa herramienta esta desactivada. Activala en Ajustes del Asistente IA."
            )
        timeout = max(5.0, min(float(getattr(self.config, "timeout", 20) or 20), 30.0))
        if name == LOCAL_TOOL:
            return list_local_images(
                arguments.get("path", ""),
                coerce_bool(arguments.get("recursive"), False),
                arguments.get("limit", 200),
            )
        try:
            if name == "search_web":
                query = str(arguments.get("query") or "")
                return {
                    "query": query,
                    "results": search_web(
                        query,
                        _clamp(arguments.get("max_results"), 5, 1, 8),
                        timeout,
                    ),
                }
            if name == "search_images":
                query = str(arguments.get("query") or "")
                return {
                    "query": query,
                    "images": search_images(
                        query,
                        _clamp(arguments.get("max_results"), 6, 1, 10),
                        timeout,
                    ),
                }
            if name == "fetch_web_page":
                return fetch_web_page(
                    str(arguments.get("url") or ""),
                    _clamp(arguments.get("max_chars"), 8000, 1000, 15000),
                    timeout,
                )
            if name == "download_image":
                return download_image(str(arguments.get("url") or ""), timeout)
        except WebError as exc:
            raise QueryError(str(exc)) from exc
        except OSError as exc:
            _LOG.warning("Fallo de red en %s: %s", name, exc)
            raise QueryError("No se pudo completar la consulta de red.") from exc
        raise QueryError(f"Herramienta de consulta desconocida: {name}")
