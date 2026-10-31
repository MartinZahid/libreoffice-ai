"""Read-only Internet helpers built with the Python standard library.

The extension never sends the API key to these endpoints.  Every request is
validated before it is opened and private, loopback and link-local addresses
are rejected so the model cannot reach services on the local network.
"""

from __future__ import annotations

import html as html_module
import ipaddress
import json
import logging
import os
import re
import socket
import tempfile
import time
import uuid
from html.parser import HTMLParser
from typing import Any
from urllib import error, parse, request

from .adapters.common import IMAGE_EXTENSIONS, MAX_IMAGE_BYTES

_LOG = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MAX_SEARCH_BYTES = 800_000
MAX_FETCH_BYTES = 1_500_000
MAX_DOWNLOAD_BYTES = MAX_IMAGE_BYTES
MAX_REDIRECTS = 5
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

_CONTENT_TYPE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/tiff": ".tiff",
}
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".lan", ".home.arpa")
_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}
_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "footer",
    "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
    "main", "nav", "ol", "p", "pre", "section", "table", "td", "th",
    "tr", "ul",
}


class WebError(ValueError):
    """Raised when a web request cannot be made safely."""


def _validate_public_url(url: Any) -> str:
    text = str(url or "").strip()
    if not text:
        raise WebError("Falta la direccion web.")
    if any(character.isspace() for character in text):
        raise WebError("La direccion web no puede contener espacios.")
    try:
        parsed = parse.urlparse(text)
        port = parsed.port
    except ValueError as exc:
        raise WebError("La direccion web no es valida.") from exc
    if parsed.scheme not in ("http", "https"):
        raise WebError("Solo se permiten direcciones http:// o https://.")
    if parsed.username or parsed.password:
        raise WebError("La direccion web no debe incluir usuario ni contrasena.")
    if not parsed.hostname:
        raise WebError("La direccion web no indica un servidor.")
    if port not in (None, 80, 443):
        raise WebError("Solo se permiten los puertos 80 y 443.")

    host = parsed.hostname.lower().rstrip(".")
    if host in ("localhost", "localhost.localdomain", "0.0.0.0"):
        raise WebError("No se permite acceder a este equipo ni a la red local.")
    if host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise WebError("No se permite acceder a nombres de la red local.")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _ensure_public_address(literal)
        return text

    try:
        addresses = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WebError(f"No se pudo resolver el servidor {host}.") from exc
    if not addresses:
        raise WebError(f"No se pudo resolver el servidor {host}.")
    for entry in addresses:
        try:
            address = ipaddress.ip_address(entry[4][0])
        except (ValueError, IndexError):
            continue
        _ensure_public_address(address)
    return text


def _ensure_public_address(address: ipaddress._BaseAddress) -> None:
    if not address.is_global:
        raise WebError("No se permite acceder a direcciones privadas o locales.")


class _PublicRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = request.build_opener(_PublicRedirectHandler())


def _open(url: str, timeout: float, headers: dict[str, str] | None = None):
    request_headers = {"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9,en;q=0.7"}
    if headers:
        request_headers.update(headers)
    req = request.Request(url, headers=request_headers, method="GET")
    try:
        return _OPENER.open(req, timeout=timeout)
    except error.HTTPError as exc:
        raise WebError(f"El servidor respondio con HTTP {exc.code}.") from exc
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise WebError("La conexion tardo demasiado.") from exc
        raise WebError(f"No se pudo conectar con el servidor: {reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise WebError("La conexion tardo demasiado.") from exc


def _read_response(response: Any, limit: int) -> bytes:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise WebError("La respuesta es demasiado grande.")
    return raw


def _fetch_text(
    url: str,
    timeout: float,
    limit: int,
    headers: dict[str, str] | None = None,
) -> str:
    _validate_public_url(url)
    request_headers = {"Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"}
    if headers:
        request_headers.update(headers)
    with _open(url, timeout, request_headers) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not any(
            item in content_type
            for item in ("text/", "application/xhtml", "application/json", "application/xml")
        ):
            raise WebError("La direccion no devuelve una pagina de texto.")
        raw = _read_response(response, limit)
        charset = response.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html_module.unescape(text)
    return " ".join(text.split())


def _unwrap_result_url(value: str) -> str:
    href = html_module.unescape(value or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    parsed = parse.urlparse(href)
    if (parsed.hostname or "").endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse.parse_qs(parsed.query).get("uddg")
        if target:
            href = target[0]
    return href


def _is_http_url(value: str) -> bool:
    try:
        parsed = parse.urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def _parse_duckduckgo(text: str, limit: int) -> list[dict[str, str]]:
    anchors = re.findall(
        r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not anchors:
        anchors = re.findall(
            r"<a[^>]+class=['\"]result-link['\"][^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",
            text,
            re.DOTALL | re.IGNORECASE,
        )
    snippets = re.findall(
        r"<td[^>]+class=['\"]result-snippet['\"][^>]*>(.*?)</td>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    results = []
    for index, (href, title) in enumerate(anchors):
        url = _unwrap_result_url(href)
        if not _is_http_url(url):
            continue
        results.append(
            {
                "title": _clean_text(title)[:200] or url,
                "url": url,
                "snippet": _clean_text(snippets[index])[:400] if index < len(snippets) else "",
            }
        )
        if len(results) >= limit:
            break
    return results


def _parse_bing(text: str, limit: int) -> list[dict[str, str]]:
    results = []
    for block in re.findall(r"<li[^>]+class=['\"][^'\"]*b_algo[^'\"]*['\"].*?</li>", text, re.DOTALL | re.IGNORECASE):
        match = re.search(
            r"<h2[^>]*>.*?<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>",
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            continue
        url = html_module.unescape(match.group(1))
        if not _is_http_url(url):
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL | re.IGNORECASE)
        results.append(
            {
                "title": _clean_text(match.group(2))[:200] or url,
                "url": url,
                "snippet": _clean_text(snippet_match.group(1))[:400] if snippet_match else "",
            }
        )
        if len(results) >= limit:
            break
    return results


def search_web(query: str, max_results: int = 5, timeout: float = 20) -> list[dict[str, str]]:
    text = _clean_text(query)
    if len(text) < 2:
        raise WebError("La busqueda es demasiado corta.")
    if len(text) > 300:
        raise WebError("La busqueda es demasiado larga.")
    limit = max(1, min(int(max_results), 8))
    encoded = parse.urlencode({"q": text})
    try:
        html = _fetch_text(
            "https://lite.duckduckgo.com/lite/?" + encoded,
            timeout,
            MAX_SEARCH_BYTES,
        )
        results = _parse_duckduckgo(html, limit)
    except WebError as exc:
        _LOG.debug("DuckDuckGo no respondio: %s", exc)
        results = []
    if not results:
        html = _fetch_text(
            "https://www.bing.com/search?" + parse.urlencode({"q": text}),
            timeout,
            MAX_SEARCH_BYTES,
        )
        results = _parse_bing(html, limit)
    if not results:
        raise WebError("No se encontraron resultados para esa busqueda.")
    return results


def search_images(query: str, max_results: int = 6, timeout: float = 20) -> list[dict[str, str]]:
    text = _clean_text(query)
    if len(text) < 2:
        raise WebError("La busqueda es demasiado corta.")
    if len(text) > 300:
        raise WebError("La busqueda es demasiado larga.")
    limit = max(1, min(int(max_results), 10))
    images = _duckduckgo_images(text, limit, timeout)
    if not images:
        images = _bing_images(text, limit, timeout)
    if not images:
        raise WebError("No se encontraron imagenes para esa busqueda.")
    return images


def _duckduckgo_images(text: str, limit: int, timeout: float) -> list[dict[str, str]]:
    try:
        landing = _fetch_text(
            "https://duckduckgo.com/?" + parse.urlencode({"q": text, "iax": "images", "ia": "images"}),
            timeout,
            MAX_SEARCH_BYTES,
        )
        token = re.search(r"vqd=[\"']([^\"']+)[\"']", landing)
        if token is None:
            token = re.search(r"vqd=([\d-]+)&", landing)
        if token is None:
            raise WebError("No se pudo obtener el token de imagenes.")
        endpoint = "https://duckduckgo.com/i.js?" + parse.urlencode(
            {
                "l": "es-es",
                "o": "json",
                "q": text,
                "vqd": token.group(1),
                "f": ",,,",
                "p": "1",
            }
        )
        raw = _fetch_text(
            endpoint,
            timeout,
            MAX_SEARCH_BYTES,
            {"Referer": "https://duckduckgo.com/", "Accept": "application/json"},
        )
        data = json.loads(raw)
    except (WebError, ValueError) as exc:
        _LOG.debug("DuckDuckGo Images no respondio: %s", exc)
        return []
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    images = []
    seen = set()
    for entry in results:
        if not isinstance(entry, dict):
            continue
        image_url = str(entry.get("image") or "")
        if not _is_http_url(image_url) or image_url in seen:
            continue
        seen.add(image_url)
        images.append(
            {
                "image_url": image_url,
                "title": _clean_text(str(entry.get("title") or ""))[:200],
                "page_url": str(entry.get("url") or ""),
                "source": str(entry.get("source") or ""),
            }
        )
        if len(images) >= limit:
            break
    return images


def _bing_images(text: str, limit: int, timeout: float) -> list[dict[str, str]]:
    try:
        html = _fetch_text(
            "https://www.bing.com/images/search?"
            + parse.urlencode({"q": text, "form": "HDRSC2", "first": 1}),
            timeout,
            MAX_SEARCH_BYTES,
        )
    except WebError as exc:
        _LOG.debug("Bing Images no respondio: %s", exc)
        return []
    raw_urls = re.findall(r"murl&quot;:&quot;(.*?)&quot;", html, re.IGNORECASE)
    if not raw_urls:
        raw_urls = re.findall(r'"murl"\s*:\s*"(.*?)"', html, re.IGNORECASE)
    images = []
    seen = set()
    for raw_url in raw_urls:
        image_url = html_module.unescape(raw_url).replace("\\/", "/")
        if not _is_http_url(image_url) or image_url in seen:
            continue
        seen.add(image_url)
        images.append({"image_url": image_url})
        if len(images) >= limit:
            break
    return images


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        return "\n".join(" ".join(line.split()) for line in raw.splitlines() if line.strip())

    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())


def fetch_web_page(url: str, max_chars: int = 8000, timeout: float = 20) -> dict[str, Any]:
    _validate_public_url(url)
    with _open(url, timeout, {"Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"}) as response:
        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not any(
            item in content_type
            for item in ("text/", "application/xhtml", "application/json", "application/xml")
        ):
            raise WebError("La direccion no devuelve una pagina de texto.")
        raw = _read_response(response, MAX_FETCH_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"
        final_url = response.geturl()
    try:
        decoded = raw.decode(charset, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    try:
        parser.feed(decoded)
        parser.close()
    except Exception as exc:
        raise WebError("No se pudo leer el contenido de la pagina.") from exc
    limit = max(1000, min(int(max_chars), 15000))
    text = parser.text()
    truncated = len(text) > limit
    return {
        "url": final_url,
        "title": parser.title()[:300],
        "text": text[:limit],
        "truncated": truncated,
    }


def _sniff_image_extension(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if raw.startswith(b"BM"):
        return ".bmp"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return ".webp"
    if raw.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    head = raw[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return ".svg"
    return ""


def _image_extension(url: str, content_type: str, raw: bytes) -> str:
    extension = os.path.splitext(parse.urlparse(url).path)[1].lower()
    if extension in IMAGE_EXTENSIONS:
        return extension
    if content_type in _CONTENT_TYPE_EXTENSIONS:
        return _CONTENT_TYPE_EXTENSIONS[content_type]
    extension = _sniff_image_extension(raw)
    if extension:
        return extension
    raise WebError("La direccion no parece contener una imagen compatible.")


def _cleanup_cache(directory: str) -> None:
    cutoff = time.time() - CACHE_MAX_AGE_SECONDS
    try:
        entries = os.scandir(directory)
    except OSError:
        return
    with entries:
        for entry in entries:
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.unlink(entry.path)
            except OSError:
                continue


def download_image(url: str, timeout: float = 30) -> dict[str, Any]:
    _validate_public_url(url)
    with _open(url, timeout, {"Accept": "image/*,*/*;q=0.5"}) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        length = response.headers.get("Content-Length")
        if length:
            try:
                if int(length) > MAX_DOWNLOAD_BYTES:
                    raise WebError("La imagen supera el limite de 20 MB.")
            except ValueError:
                pass
        raw = _read_response(response, MAX_DOWNLOAD_BYTES)
    if not raw:
        raise WebError("La imagen esta vacia.")
    if content_type and not content_type.startswith("image/"):
        raise WebError("La direccion no devuelve una imagen.")
    extension = _image_extension(url, content_type, raw)
    directory = os.path.join(tempfile.gettempdir(), "LibreOfficeAI", "images")
    os.makedirs(directory, exist_ok=True)
    _cleanup_cache(directory)
    path = os.path.join(directory, uuid.uuid4().hex + extension)
    try:
        with open(path, "wb") as handle:
            handle.write(raw)
    except OSError as exc:
        raise WebError("No se pudo guardar la imagen descargada.") from exc
    return {
        "path": path,
        "bytes": len(raw),
        "content_type": content_type or "desconocido",
        "source_url": url,
    }
