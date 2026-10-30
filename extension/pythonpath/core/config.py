"""Persistent, local configuration for the LibreOffice AI assistant."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, replace
from typing import Any
from urllib.parse import urlparse

try:
    import uno
except ImportError:  # Allows pure-Python tests outside LibreOffice.
    uno = None


DEFAULT_BASE_URL = "https://opencode.ai/inference/go/openai/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash"
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_CONTEXT_CHARS = 12000

_LEGACY_BASE_URLS = {
    "https://opencode.ai/zen/go/v1": "https://opencode.ai/inference/go/openai/v1",
    "https://opencode.ai/zen/v1": "https://opencode.ai/inference/openai/v1",
    "https://opencode.ai/inference/go": "https://opencode.ai/inference/go/openai/v1",
    "https://opencode.ai/inference": "https://opencode.ai/inference/openai/v1",
}


class ConfigError(ValueError):
    """Raised when the user configuration is not usable."""


@dataclass
class Config:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""
    timeout: int = DEFAULT_TIMEOUT
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
    confirm_before_apply: bool = True

    def validate(self) -> "Config":
        self.base_url = normalize_base_url(self.base_url)
        self.model = (self.model or "").strip()
        self.api_key = (self.api_key or "").strip()
        if not self.model:
            raise ConfigError("El modelo no puede estar vacío.")
        if any(ord(character) < 32 for character in self.api_key):
            raise ConfigError("La clave de API contiene caracteres no válidos.")
        self.timeout = int(self.timeout)
        self.max_tokens = int(self.max_tokens)
        self.temperature = float(self.temperature)
        self.max_context_chars = int(self.max_context_chars)
        self.confirm_before_apply = _as_bool(self.confirm_before_apply)
        if not 1 <= self.timeout <= 600:
            raise ConfigError("El tiempo de espera debe estar entre 1 y 600 segundos.")
        if not 64 <= self.max_tokens <= 32768:
            raise ConfigError("max_tokens debe estar entre 64 y 32768.")
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigError("La temperatura debe estar entre 0 y 2.")
        if not 1000 <= self.max_context_chars <= 100000:
            raise ConfigError("El límite de contexto debe estar entre 1000 y 100000 caracteres.")
        return self

    def require_api_key(self) -> "Config":
        if not self.api_key:
            self.api_key = os.environ.get("OPENCODE_API_KEY", "").strip()
        if not self.api_key:
            raise ConfigError(
                "Falta la clave de API. Abre Ajustes y pega tu clave de OpenCode, "
                "o define la variable OPENCODE_API_KEY."
            )
        return self

    def as_dict(self, include_secret: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_secret:
            data["api_key"] = "***" if data.get("api_key") else ""
        return data


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "si", "sí")
    return bool(value)


def _clean_secret(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value.strip() if ord(character) >= 32)


def normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        raise ConfigError("La URL base no puede estar vacía.")
    if any(character.isspace() for character in value):
        raise ConfigError("La URL base no puede contener espacios.")
    if value.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
    value = _LEGACY_BASE_URLS.get(value, value)

    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError as exc:
        raise ConfigError("La URL base no es válida.") from exc

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError("La URL base debe empezar por https://.")
    if parsed.username or parsed.password:
        raise ConfigError("La URL base no debe incluir usuario ni contraseña.")
    if parsed.query or parsed.fragment:
        raise ConfigError("La URL base no debe incluir parámetros ni fragmentos.")
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ConfigError(
            "La URL base debe usar https://. Solo localhost o 127.0.0.1 pueden usar http://."
        )
    return value


def config_directory(ctx=None) -> str:
    """Return the per-user directory used to store the API key."""
    if ctx is not None and uno is not None:
        try:
            paths = ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.util.PathSettings", ctx
            )
            user_config = paths.UserConfig
            user_config_path = uno.fileUrlToSystemPath(user_config)
            base = os.path.dirname(os.path.normpath(user_config_path))
            return os.path.join(base, "LibreOfficeAI")
        except Exception:
            pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "LibreOffice", "4", "user", "LibreOfficeAI")

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return os.path.join(xdg_config, "libreoffice", "4", "user", "LibreOfficeAI")
    return os.path.join(os.path.expanduser("~"), ".config", "libreoffice", "4", "user", "LibreOfficeAI")


def config_path(ctx=None) -> str:
    return os.path.join(config_directory(ctx), "config.json")


def load_config(ctx=None) -> Config:
    path = config_path(ctx)
    data: dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            data = raw
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        data = {}

    config = Config(api_key=_clean_secret(data.get("api_key")))
    converters = {
        "base_url": str,
        "model": str,
        "timeout": int,
        "max_tokens": int,
        "temperature": float,
        "max_context_chars": int,
        "confirm_before_apply": _as_bool,
    }
    for name, converter in converters.items():
        if name not in data:
            continue
        try:
            candidate = replace(config, **{name: converter(data[name])})
            candidate.validate()
        except (ConfigError, TypeError, ValueError):
            continue
        config = candidate

    try:
        return config.validate()
    except (ConfigError, TypeError, ValueError):
        return Config(api_key=config.api_key).validate()


def save_config(config: Config, ctx=None) -> None:
    config.validate()
    directory = config_directory(ctx)
    path = os.path.join(directory, "config.json")
    os.makedirs(directory, exist_ok=True)

    if os.path.isfile(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass

    fd, temporary = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config.as_dict(include_secret=True), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
