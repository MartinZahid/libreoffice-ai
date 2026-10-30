"""Settings dialog for the LibreOffice AI assistant."""

from __future__ import annotations

from typing import Any

from core.config import Config, ConfigError, load_config, save_config

from ui.chat_dialog import (
    _ActionListener,
    _WindowListener,
    _add_button,
    _add_checkbox,
    _add_edit,
    _add_label,
    _create_dialog,
    _message,
    _model,
)

_OPEN: list["SettingsDialog"] = []


class SettingsDialog:
    def __init__(self, ctx: Any, parent: Any = None):
        self.ctx = ctx
        self._base = load_config(ctx)
        self._closed = False
        model = _model(ctx, "com.sun.star.awt.UnoControlDialogModel")
        model.Width = 640
        model.Height = 440
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
            "timeout",
            "max_tokens",
            "temperature",
            "confirm",
            "save",
            "cancel",
        ):
            try:
                self._controls[name] = self._dialog.getControl(name)
            except Exception:
                pass
        self._action_listeners = []
        self._window = _WindowListener(self._cancel, lambda: None)
        self._dialog.addTopWindowListener(self._window)
        for name in ("save", "cancel"):
            listener = _ActionListener(self._on_action, name)
            self._controls[name].addActionListener(listener)
            self._action_listeners.append(listener)

    def _add_fields(self, model: Any, layout: list[tuple[str, int, int, int, int]]) -> None:
        _add_label(model, "lbl_base", 16, 24, 140, 18, "URL base", layout)
        _add_edit(
            model, "base_url", 170, 20, 450, 26,
            layout, Text=self._base.base_url,
        )
        _add_label(model, "lbl_model", 16, 64, 140, 18, "Modelo", layout)
        _add_edit(
            model, "model", 170, 60, 450, 26,
            layout, Text=self._base.model,
        )
        _add_label(model, "lbl_key", 16, 104, 140, 18, "Clave de API", layout)
        _add_edit(
            model, "api_key", 170, 100, 450, 26,
            layout, EchoChar=42, Text=self._base.api_key,
        )
        _add_label(
            model, "lbl_timeout", 16, 144, 140, 18,
            "Tiempo de espera (s)", layout,
        )
        _add_edit(
            model, "timeout", 170, 140, 100, 26,
            layout, Text=str(self._base.timeout),
        )
        _add_label(model, "lbl_tokens", 290, 144, 110, 18, "Máx. tokens", layout)
        _add_edit(
            model, "max_tokens", 410, 140, 100, 26,
            layout, Text=str(self._base.max_tokens),
        )
        _add_label(model, "lbl_temp", 16, 184, 140, 18, "Temperatura", layout)
        _add_edit(
            model, "temperature", 170, 180, 100, 26,
            layout, Text=str(self._base.temperature),
        )
        _add_checkbox(
            model, "confirm", 16, 224, 600, 22,
            "Pedir Aceptar/Rechazar antes de mantener los cambios",
            self._base.confirm_before_apply, layout,
        )
        _add_label(
            model, "hint", 16, 260, 608, 18,
            "La clave se guarda solo en tu perfil local de LibreOffice.", layout,
        )
        _add_label(
            model, "hint2", 16, 282, 608, 18,
            "También puedes usar la variable OPENCODE_API_KEY.", layout,
        )
        _add_button(model, "save", 350, 380, 120, 30, "Guardar", layout=layout)
        _add_button(model, "cancel", 480, 380, 120, 30, "Cancelar", layout=layout)

    def _text(self, name: str) -> str:
        try:
            return str(self._controls[name].Text or "").strip()
        except Exception:
            return ""

    def _on_action(self, command: str) -> None:
        if command == "save":
            self._save()
        elif command == "cancel":
            self._cancel()

    def _number(self, name: str, label: str) -> str:
        text = self._text(name)
        try:
            float(text)
        except ValueError as exc:
            raise ConfigError(f"{label} debe ser un número.") from exc
        return text

    def _save(self) -> None:
        try:
            config = Config(
                base_url=self._text("base_url"),
                model=self._text("model"),
                api_key=self._text("api_key"),
                timeout=int(self._number("timeout", "El tiempo de espera")),
                max_tokens=int(self._number("max_tokens", "El máximo de tokens")),
                temperature=float(self._number("temperature", "La temperatura")),
                max_context_chars=self._base.max_context_chars,
                confirm_before_apply=bool(self._controls["confirm"].State),
            ).validate()
            save_config(config, self.ctx)
        except (ValueError, ConfigError, OSError) as exc:
            _message(self.ctx, self._dialog, "Ajustes", str(exc), error=True)
            return
        self._close()

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
        except Exception:
            pass

    def _close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
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


def show_settings_dialog(ctx: Any, parent: Any = None) -> SettingsDialog:
    dialog = SettingsDialog(ctx, parent)
    dialog.show()
    return dialog
