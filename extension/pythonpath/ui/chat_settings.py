"""Settings dialog for the LibreOffice AI assistant."""

from __future__ import annotations

import logging
import threading
from typing import Any

from core.config import Config, ConfigError, load_config, save_config
from core.llm import LLMClient

from ui.chat_dialog import (
    _ActionListener,
    _Callback,
    _WindowListener,
    _add_button,
    _add_checkbox,
    _add_edit,
    _add_label,
    _create_dialog,
    _message,
    _model,
)

_LOG = logging.getLogger(__name__)
_OPEN: list["SettingsDialog"] = []


class SettingsDialog:
    def __init__(self, ctx: Any, parent: Any = None, on_close: Any = None):
        self.ctx = ctx
        self._on_close = on_close
        self._base = load_config(ctx)
        self._closed = False
        self._saved = False
        self._testing = False
        model = _model(ctx, "com.sun.star.awt.UnoControlDialogModel")
        model.Width = 640
        model.Height = 460
        try:
            model.Title = "Ajustes del Asistente IA"
        except Exception:
            pass
        layout: list[tuple[str, int, int, int, int]] = []
        self._add_fields(model, layout)
        self._dialog = _create_dialog(ctx, model, layout)
        self._controls: dict[str, Any] = {}
        for name in (
            "base_url",
            "model",
            "api_key",
            "toggle_key",
            "timeout",
            "max_tokens",
            "temperature",
            "confirm",
            "local_files",
            "web_search",
            "test",
            "save",
            "cancel",
        ):
            try:
                self._controls[name] = self._dialog.getControl(name)
            except Exception as exc:
                _LOG.warning("No se pudo obtener el control %s: %s", name, exc)
        self._action_listeners = []
        self._window = _WindowListener(self._cancel, lambda: None)
        self._dialog.addTopWindowListener(self._window)
        for name in ("save", "cancel", "toggle_key", "test"):
            listener = _ActionListener(self._on_action, name)
            self._controls[name].addActionListener(listener)
            self._action_listeners.append(listener)
        self._callback = _Callback(self._on_test_result)
        self._async = _model(ctx, "com.sun.star.awt.AsyncCallback")

    def _add_fields(self, model: Any, layout: list[tuple[str, int, int, int, int]]) -> None:
        _add_label(model, "lbl_base", 16, 24, 140, 18, "URL base", layout)
        _add_edit(
            model, "base_url", 170, 20, 450, 26,
            layout, Text=self._base.base_url, TabIndex=1,
            HelpText="Dirección del proveedor compatible con OpenAI.",
        )
        _add_label(model, "lbl_model", 16, 64, 140, 18, "Modelo", layout)
        _add_edit(
            model, "model", 170, 60, 450, 26,
            layout, Text=self._base.model, TabIndex=2,
            HelpText="Identificador exacto del modelo, por ejemplo deepseek-v4.1-flash.",
        )
        _add_label(model, "lbl_key", 16, 104, 140, 18, "Clave de API", layout)
        _add_edit(
            model, "api_key", 170, 100, 390, 26,
            layout, EchoChar=42, Text=self._base.api_key, TabIndex=3,
            HelpText="Se guarda en tu perfil local, no se incluye en los documentos.",
        )
        _add_button(
            model, "toggle_key", 570, 100, 60, 26, "Mostrar", layout,
            help_text="Muestra u oculta la clave escrita.", TabIndex=4,
        )
        _add_label(
            model, "lbl_timeout", 16, 144, 140, 18,
            "Tiempo de espera (s)", layout,
        )
        _add_edit(
            model, "timeout", 170, 140, 100, 26,
            layout, Text=str(self._base.timeout), TabIndex=5,
            HelpText="Segundos antes de cancelar una petición (1 a 600).",
        )
        _add_label(model, "lbl_tokens", 290, 144, 110, 18, "Máx. tokens", layout)
        _add_edit(
            model, "max_tokens", 410, 140, 100, 26,
            layout, Text=str(self._base.max_tokens), TabIndex=6,
            HelpText="Límite de tokens de la respuesta (64 a 32768).",
        )
        _add_label(model, "lbl_temp", 16, 184, 140, 18, "Temperatura", layout)
        _add_edit(
            model, "temperature", 170, 180, 100, 26,
            layout, Text=str(self._base.temperature), TabIndex=7,
            HelpText="Creatividad del modelo, entre 0 y 2.",
        )
        _add_checkbox(
            model, "confirm", 16, 224, 600, 22,
            "Pedir Aceptar/Rechazar antes de mantener los cambios",
            self._base.confirm_before_apply, layout,
            help_text="Si está desmarcado, los cambios se aceptan automáticamente.",
            TabIndex=8,
        )
        _add_checkbox(
            model, "local_files", 16, 250, 600, 22,
            "Permitir listar imágenes de carpetas locales",
            self._base.enable_local_files, layout,
            help_text="Solo lee nombres, rutas y tamaños de imágenes; no envía su contenido.",
            TabIndex=9,
        )
        _add_checkbox(
            model, "web_search", 16, 276, 600, 22,
            "Permitir búsquedas y descargas desde Internet",
            self._base.enable_web_search, layout,
            help_text="Usa buscadores públicos y bloquea direcciones de la red local.",
            TabIndex=10,
        )
        _add_label(
            model, "hint", 16, 306, 608, 18,
            "La clave se guarda solo en tu perfil local de LibreOffice.", layout,
        )
        _add_label(
            model, "hint2", 16, 328, 608, 18,
            "También puedes usar la variable OPENCODE_API_KEY.", layout,
        )
        _add_label(
            model, "hint3", 16, 350, 608, 18,
            "Solo se permite https://; http:// únicamente para localhost.", layout,
        )
        _add_button(
            model, "test", 16, 404, 130, 30, "Probar conexión", layout,
            help_text="Comprueba la URL, la clave y el modelo con una llamada mínima.",
            TabIndex=11,
        )
        _add_button(
            model, "save", 350, 404, 120, 30, "Guardar", layout,
            help_text="Valida y guarda la configuración.", TabIndex=12,
        )
        _add_button(
            model, "cancel", 480, 404, 120, 30, "Cancelar", layout,
            help_text="Cierra sin guardar los cambios.", TabIndex=13,
        )

    def _text(self, name: str) -> str:
        try:
            return str(self._controls[name].Text or "").strip()
        except Exception:
            return ""

    def _set_enabled(self, name: str, enabled: bool) -> None:
        control = self._controls.get(name)
        if control is None:
            return
        try:
            control.setEnable(enabled)
            return
        except Exception:
            pass
        try:
            control.Enabled = enabled
        except Exception as exc:
            _LOG.debug("No se pudo habilitar %s: %s", name, exc)

    def _set_button_label(self, name: str, label: str) -> None:
        control = self._controls.get(name)
        if control is None:
            return
        try:
            control.getModel().Label = label
        except Exception:
            try:
                control.Label = label
            except Exception as exc:
                _LOG.debug("No se pudo cambiar la etiqueta %s: %s", name, exc)

    def _on_action(self, command: str) -> None:
        if command == "save":
            self._save()
        elif command == "cancel":
            self._cancel()
        elif command == "toggle_key":
            self._toggle_key()
        elif command == "test":
            self._test()

    def _toggle_key(self) -> None:
        control = self._controls.get("api_key")
        if control is None:
            return
        try:
            model = control.getModel()
            hidden = int(model.EchoChar) != 0
            model.EchoChar = 0 if hidden else 42
            self._set_button_label("toggle_key", "Ocultar" if hidden else "Mostrar")
        except Exception as exc:
            _LOG.debug("No se pudo cambiar la visibilidad de la clave: %s", exc)

    def _integer(self, name: str, label: str) -> int:
        text = self._text(name)
        try:
            number = float(text)
        except ValueError as exc:
            raise ConfigError(f"{label} debe ser un número entero.") from exc
        if not number.is_integer():
            raise ConfigError(f"{label} debe ser un número entero.")
        return int(number)

    def _decimal(self, name: str, label: str) -> float:
        text = self._text(name)
        try:
            return float(text)
        except ValueError as exc:
            raise ConfigError(f"{label} debe ser un número.") from exc

    def _read_config(self) -> Config:
        return Config(
            base_url=self._text("base_url"),
            model=self._text("model"),
            api_key=self._text("api_key"),
            timeout=self._integer("timeout", "El tiempo de espera"),
            max_tokens=self._integer("max_tokens", "El máximo de tokens"),
            temperature=self._decimal("temperature", "La temperatura"),
            max_context_chars=self._base.max_context_chars,
            confirm_before_apply=bool(self._controls["confirm"].State),
            enable_local_files=bool(self._controls["local_files"].State),
            enable_web_search=bool(self._controls["web_search"].State),
        ).validate()

    def _save(self) -> None:
        try:
            config = self._read_config()
            save_config(config, self.ctx)
        except (ValueError, ConfigError, OSError) as exc:
            _message(self.ctx, self._dialog, "Ajustes", str(exc), error=True)
            return
        self._saved = True
        self._close()

    def _test(self) -> None:
        if self._testing:
            return
        try:
            config = self._read_config().require_api_key()
        except (ValueError, ConfigError) as exc:
            _message(self.ctx, self._dialog, "Probar conexión", str(exc), error=True)
            return
        self._testing = True
        self._set_enabled("test", False)
        self._set_button_label("test", "Probando...")
        worker = threading.Thread(target=self._test_worker, args=(config,), daemon=True)
        worker.start()

    def _test_worker(self, config: Config) -> None:
        try:
            models = LLMClient(config).list_models()
            message = f"Conexión correcta. {len(models)} modelo(s) disponibles."
        except Exception as exc:
            message = str(exc)
        try:
            self._async.addCallback(self._callback, message)
        except Exception as exc:
            _LOG.debug("No se pudo devolver el resultado de la prueba: %s", exc)

    def _on_test_result(self, message: Any) -> None:
        self._testing = False
        if self._closed:
            return
        text = str(message)
        self._set_enabled("test", True)
        self._set_button_label("test", "Probar conexión")
        _message(
            self.ctx,
            self._dialog,
            "Probar conexión",
            text,
            error=not text.startswith("Conexión correcta"),
        )

    def _cancel(self) -> None:
        self._close()

    def show(self) -> None:
        if self._closed:
            return
        if self not in _OPEN:
            _OPEN.append(self)
        try:
            self._dialog.setVisible(True)
            self._dialog.toFront()
            self._dialog.setFocus()
            self._controls["base_url"].setFocus()
        except Exception as exc:
            _LOG.debug("No se pudo mostrar Ajustes: %s", exc)

    def _close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        try:
            self._async.removeCallback(self._callback)
        except Exception:
            pass
        try:
            self._dialog.setVisible(False)
        except Exception:
            pass
        try:
            self._dialog.dispose()
        except Exception:
            pass
        if self in _OPEN:
            _OPEN.remove(self)
        if self._saved and self._on_close is not None:
            try:
                self._on_close()
            except Exception as exc:
                _LOG.warning("No se pudo recargar la configuración: %s", exc)


def show_settings_dialog(ctx: Any, parent: Any = None, on_close: Any = None) -> SettingsDialog:
    dialog = SettingsDialog(ctx, parent, on_close)
    dialog.show()
    return dialog
