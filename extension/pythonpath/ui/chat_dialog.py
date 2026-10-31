"""Native LibreOffice chat and settings dialogs."""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

import unohelper
from com.sun.star.awt import XActionListener, XCallback, XKeyListener, XTopWindowListener

from core.agent import Agent
from core.config import ConfigError, load_config
from core.document_context import build_document_context
from core.executor import Executor, describe_action
from core.llm import LLMClient
from core.query_tools import QueryRunner

_LOG = logging.getLogger(__name__)
PICK_COUNT = 10


def _model(ctx: Any, service: str) -> Any:
    return ctx.ServiceManager.createInstanceWithContext(service, ctx)


def _add_control(
    dialog_model: Any,
    service: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    layout: list[tuple[str, int, int, int, int]] | None = None,
    **properties: Any,
) -> Any:
    control_model = dialog_model.createInstance(service)
    for key, value in properties.items():
        try:
            control_model.setPropertyValue(key, value)
        except Exception as exc:
            _LOG.debug("Propiedad %s no admitida en %s: %s", key, name, exc)
    for key, value in (
        ("PositionX", x),
        ("PositionY", y),
        ("Width", width),
        ("Height", height),
    ):
        try:
            setattr(control_model, key, value)
        except Exception as exc:
            _LOG.debug("No se pudo situar el control %s: %s", name, exc)
    dialog_model.insertByName(name, control_model)
    if layout is not None:
        layout.append((name, x, y, width, height))
    return control_model


def _add_edit(
    model: Any,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    layout: list[tuple[str, int, int, int, int]] | None = None,
    **properties: Any,
) -> None:
    _add_control(
        model,
        "com.sun.star.awt.UnoControlEditModel",
        name,
        x,
        y,
        width,
        height,
        layout,
        **properties,
    )


def _add_label(
    model: Any,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    text: str,
    layout: list[tuple[str, int, int, int, int]] | None = None,
) -> None:
    _add_control(
        model,
        "com.sun.star.awt.UnoControlFixedTextModel",
        name,
        x,
        y,
        width,
        height,
        layout,
        Label=text,
    )


def _add_button(
    model: Any,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    label: str,
    layout: list[tuple[str, int, int, int, int]] | None = None,
    help_text: str = "",
    **properties: Any,
) -> None:
    _add_control(
        model,
        "com.sun.star.awt.UnoControlButtonModel",
        name,
        x,
        y,
        width,
        height,
        layout,
        Label=label,
        HelpText=help_text,
        **properties,
    )


def _add_checkbox(
    model: Any,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    label: str,
    checked: bool,
    layout: list[tuple[str, int, int, int, int]] | None = None,
    help_text: str = "",
    **properties: Any,
) -> None:
    _add_control(
        model,
        "com.sun.star.awt.UnoControlCheckBoxModel",
        name,
        x,
        y,
        width,
        height,
        layout,
        Label=label,
        State=1 if checked else 0,
        HelpText=help_text,
        **properties,
    )


def _fit_dialog(
    dialog: Any,
    toolkit: Any,
    width: int,
    height: int,
    anchor: str = "center",
) -> None:
    """Keep the dialog at its pixel size.

    LibreOffice 26.8 treats UnoControlDialogModel dimensions as pixels but can
    apply a 1/100 mm conversion while creating the peer, doubling the window.
    Setting the final rectangle after createPeer avoids that.
    """
    if width <= 0 or height <= 0:
        return
    x, y = 100, 100
    try:
        area = toolkit.getWorkArea()
        if area.Width > 0 and area.Height > 0:
            if anchor == "right":
                x = area.X + max(0, area.Width - width - 12)
                y = area.Y + 12
            else:
                x = area.X + max(0, (area.Width - width) // 2)
                y = area.Y + max(0, (area.Height - height) // 2)
    except Exception:
        pass
    try:
        dialog.setPosSize(x, y, width, height, 15)
    except Exception as exc:
        _LOG.warning("No se pudo fijar el tamaño del diálogo: %s", exc)


def _create_dialog(
    ctx: Any,
    model: Any,
    layout: list[tuple[str, int, int, int, int]] | None = None,
    anchor: str = "center",
) -> Any:
    try:
        width = int(model.Width)
        height = int(model.Height)
    except Exception:
        width = height = 0
    dialog = _model(ctx, "com.sun.star.awt.UnoControlDialog")
    dialog.setModel(model)
    toolkit = _model(ctx, "com.sun.star.awt.Toolkit")
    dialog.createPeer(toolkit, None)
    if layout:
        for name, left, top, control_width, control_height in layout:
            try:
                dialog.getControl(name).setPosSize(
                    left, top, control_width, control_height, 15
                )
            except Exception as exc:
                _LOG.debug("No se pudo recolocar el control %s: %s", name, exc)
    _fit_dialog(dialog, toolkit, width, height, anchor)
    return dialog


def _message(ctx: Any, parent: Any, title: str, message: str, error: bool = False) -> None:
    try:
        toolkit = _model(ctx, "com.sun.star.awt.Toolkit")
        box_type = 3 if error else 1
        buttons = 1
        parent_peer = None
        if parent is not None:
            try:
                parent_peer = parent.getPeer()
            except Exception:
                parent_peer = None
        box = toolkit.createMessageBox(parent_peer, box_type, buttons, title, message)
        box.execute()
        box.dispose()
    except Exception as exc:
        _LOG.warning("No se pudo mostrar el mensaje «%s»: %s", title, exc)


class _Callback(unohelper.Base, XCallback):
    def __init__(self, handler: Any):
        self._handler = handler

    def notify(self, data: Any) -> None:
        self._handler(data)


class _WindowListener(unohelper.Base, XTopWindowListener):
    def __init__(self, on_closing: Any, on_closed: Any):
        self._on_closing = on_closing
        self._on_closed = on_closed

    def windowOpened(self, event: Any) -> None:
        pass

    def windowClosing(self, event: Any) -> None:
        self._on_closing()

    def windowClosed(self, event: Any) -> None:
        self._on_closed()

    def windowMinimized(self, event: Any) -> None:
        pass

    def windowNormalized(self, event: Any) -> None:
        pass

    def windowActivated(self, event: Any) -> None:
        pass

    def windowDeactivated(self, event: Any) -> None:
        pass

    def disposing(self, event: Any) -> None:
        pass


class _ActionListener(unohelper.Base, XActionListener):
    def __init__(self, handler: Any, command: str):
        self._handler = handler
        self._command = command

    def actionPerformed(self, event: Any) -> None:
        self._handler(self._command)


class _KeyListener(unohelper.Base, XKeyListener):
    def __init__(self, handler: Any):
        self._handler = handler

    def keyPressed(self, event: Any) -> None:
        if int(getattr(event, "KeyCode", 0)) == 1280 and int(getattr(event, "Modifiers", 0)) & 2:
            self._handler()

    def keyReleased(self, event: Any) -> None:
        pass


class ChatDialog:
    """Modeless chat window bound to one frame."""

    def __init__(self, ctx: Any, frame: Any):
        self.ctx = ctx
        self.frame = frame
        self._closed = False
        self._running = False
        self._generation = 0
        self._stop_event: threading.Event | None = None
        self._lock = threading.Lock()
        self._events: deque[tuple[int, str, Any]] = deque()
        self._pending: list[dict[str, Any]] = []
        self._applied = False
        self._executor: Executor | None = None
        self._history = ""
        self._session_id: str | None = None
        self._agent: Agent | None = None
        self._config = load_config(ctx)
        self._controls: dict[str, Any] = {}
        self._build()
        self._window_listener = _WindowListener(self._hide, self._hide)
        self._action_listeners = []
        self._callback = _Callback(self._on_async)
        self._async = _model(ctx, "com.sun.star.awt.AsyncCallback")
        self._key_listener = _KeyListener(lambda: self._on_action("send"))
        self._dialog.addTopWindowListener(self._window_listener)
        for name in ("send", "stop", "apply", "discard", "new", "settings"):
            control = self._controls[name]
            listener = _ActionListener(self._on_action, name)
            control.addActionListener(listener)
            self._action_listeners.append(listener)
        try:
            self._controls["input"].addKeyListener(self._key_listener)
        except Exception as exc:
            _LOG.debug("No se pudo activar Ctrl+Enter: %s", exc)
        self._controls["history"].Text = "Asistente IA listo. Pide cambios para el documento activo.\n"
        self._set_running(False)
        self._render_pending()

    def _build(self) -> None:
        model = _model(self.ctx, "com.sun.star.awt.UnoControlDialogModel")
        model.Width = 420
        model.Height = 700
        try:
            model.Title = "Asistente IA"
        except Exception:
            pass
        layout: list[tuple[str, int, int, int, int]] = []
        _add_edit(
            model, "history", 10, 10, 400, 400,
            layout, MultiLine=True, ReadOnly=True, VScroll=True,
            Tabstop=False, TabIndex=0,
            HelpText="Historial de la conversación con el asistente.",
        )
        _add_label(
            model, "pending_label", 10, 414, 400, 16,
            "Cambios propuestos (marca los que conservar)", layout,
        )
        _add_edit(
            model, "pending", 10, 432, 400, 42,
            layout, MultiLine=True, ReadOnly=True, VScroll=True,
            Tabstop=False, TabIndex=0,
            HelpText="Resumen de los cambios aplicados como vista previa.",
        )
        for index in range(PICK_COUNT):
            _add_checkbox(
                model, f"pick{index + 1}", 10 + index * 39, 478, 38, 18,
                str(index + 1), True, layout,
                help_text=f"Conservar el cambio {index + 1}.",
                TabIndex=9 + index,
            )
        _add_edit(
            model, "input", 10, 500, 400, 76,
            layout, MultiLine=True, VScroll=True, Tabstop=True, TabIndex=1,
            HelpText="Escribe tu petición. Ctrl+Enter para enviar.",
        )
        _add_label(
            model, "hint", 10, 580, 400, 14,
            "Ctrl+Enter envía · Enter añade una línea", layout,
        )
        _add_label(model, "status", 10, 596, 400, 16, "Listo", layout)
        _add_checkbox(
            model, "context", 10, 616, 400, 20,
            "Incluir contexto del documento", True, layout,
            help_text="Envía un resumen del documento activo al modelo.",
            TabIndex=2,
        )
        buttons = (
            ("send", "Enviar", "Envía la petición al modelo.", 3),
            ("stop", "Parar", "Detiene la espera de la respuesta.", 4),
            ("apply", "Aceptar", "Conserva los cambios marcados.", 5),
            ("discard", "Rechazar", "Deshace toda la vista previa.", 6),
            ("new", "Nuevo", "Inicia una conversación nueva.", 7),
            ("settings", "Ajustes", "Configura proveedor, modelo y clave.", 8),
        )
        for index, (name, label, help_text, tab_index) in enumerate(buttons):
            row = index // 3
            column = index % 3
            _add_button(
                model, name, 10 + column * 132, 644 + row * 30, 126, 26,
                label, layout=layout, help_text=help_text, TabIndex=tab_index,
            )
        self._dialog = _create_dialog(self.ctx, model, layout, "right")
        names = ["history", "pending", "input", "status", "context"]
        names.extend(name for name, _, _, _ in buttons)
        names.extend(f"pick{index + 1}" for index in range(PICK_COUNT))
        for name in names:
            try:
                self._controls[name] = self._dialog.getControl(name)
            except Exception as exc:
                _LOG.warning("No se pudo obtener el control %s: %s", name, exc)
        try:
            self._dialog.Title = "Asistente IA"
        except Exception:
            pass

    def show(self) -> None:
        if self._closed:
            return
        try:
            self._dialog.setVisible(True)
            self._dialog.toFront()
            self._dialog.setFocus()
            self._controls["input"].setFocus()
        except Exception:
            pass

    def _hide(self) -> None:
        self._reject_pending(silent=True)
        try:
            self._dialog.setVisible(False)
        except Exception:
            pass

    def dispose(self) -> None:
        if self._closed:
            return
        self._reject_pending(silent=True)
        self._closed = True
        self._generation += 1
        if self._stop_event is not None:
            self._stop_event.set()
        try:
            self._async.removeCallback(self._callback)
        except Exception:
            pass
        try:
            self._dialog.dispose()
        except Exception:
            pass

    def _on_action(self, command: str) -> None:
        if command == "send":
            self._send()
        elif command == "stop":
            self._stop()
        elif command == "apply":
            self._accept_pending()
        elif command == "discard":
            self._reject_pending()
        elif command == "new":
            self._new_chat()
        elif command == "settings":
            from ui.chat_settings import show_settings_dialog

            show_settings_dialog(self.ctx, self._dialog, on_close=self._reload_config)

    def _reload_config(self) -> None:
        self._config = load_config(self.ctx)
        self._set_status("Ajustes actualizados.")

    def _document(self) -> Any:
        try:
            controller = self.frame.getController()
            if controller is not None:
                return controller.getModel()
        except Exception:
            pass
        try:
            desktop = _model(self.ctx, "com.sun.star.frame.Desktop")
            return desktop.getCurrentComponent()
        except Exception:
            return None

    def _text(self, name: str) -> str:
        try:
            return str(self._controls[name].Text or "")
        except Exception:
            return ""

    def _set_text(self, name: str, value: str) -> None:
        try:
            self._controls[name].Text = value
        except Exception:
            pass

    def _set_checkbox(self, name: str, checked: bool) -> None:
        control = self._controls.get(name)
        if control is None:
            return
        try:
            control.getModel().State = 1 if checked else 0
        except Exception:
            try:
                control.State = 1 if checked else 0
            except Exception as exc:
                _LOG.debug("No se pudo cambiar la casilla %s: %s", name, exc)

    def _read_checkbox(self, name: str) -> bool:
        control = self._controls.get(name)
        if control is None:
            return False
        try:
            return bool(control.getModel().State)
        except Exception:
            try:
                return bool(control.State)
            except Exception:
                return False

    def _reset_picks(self) -> None:
        for index in range(PICK_COUNT):
            self._set_checkbox(f"pick{index + 1}", True)

    def _picked_actions(self) -> list[dict[str, Any]]:
        if len(self._pending) > PICK_COUNT:
            return list(self._pending)
        return [
            action
            for index, action in enumerate(self._pending)
            if self._read_checkbox(f"pick{index + 1}")
        ]

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
            control.Enable = enabled
        except Exception:
            pass

    def _set_status(self, message: str) -> None:
        control = self._controls.get("status")
        if control is None:
            return
        text = message[:300]
        try:
            control.getModel().Label = text
        except Exception:
            try:
                control.Label = text
            except Exception:
                pass

    def _append_history(self, label: str, text: str) -> None:
        block = f"\n──────── {label} ────────\n{text.strip()}\n"
        self._history = (self._history + block)[-30000:]
        self._set_text("history", self._history)

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._set_enabled("send", not running)
        self._set_enabled("stop", running)
        self._set_enabled("apply", bool(self._pending) and not running)
        self._set_enabled("discard", bool(self._pending) and not running)
        self._set_enabled("new", True)
        self._set_enabled("settings", not running)

    def _render_pending(self) -> None:
        for index in range(PICK_COUNT):
            name = f"pick{index + 1}"
            enabled = index < len(self._pending) and not self._running
            self._set_enabled(name, enabled)
            if index < len(self._pending):
                description = describe_action(self._pending[index])[:200]
                try:
                    self._controls[name].getModel().HelpText = description
                except Exception:
                    pass
        if not self._pending:
            self._set_text("pending", "")
            self._set_enabled("apply", False)
            self._set_enabled("discard", False)
            return
        header = "Vista previa aplicada:" if self._applied else "Cambios propuestos:"
        if len(self._pending) > PICK_COUNT:
            header += f" {len(self._pending)} cambios; se aplicarán todos."
        lines = [header]
        lines.extend(
            f"{index + 1}. {describe_action(action)}"
            for index, action in enumerate(self._pending)
        )
        self._set_text("pending", "\n".join(lines))
        self._set_enabled("apply", not self._running)
        self._set_enabled("discard", not self._running)

    def _send(self) -> None:
        if self._running:
            return
        if self._pending:
            self._reject_pending(silent=True)
            if self._pending:
                self._set_status(
                    "No se pudo rechazar la vista previa anterior. "
                    "Deshazla manualmente o revisa el documento."
                )
                return
        text = self._text("input").strip()
        if not text:
            self._set_status("Escribe una petición antes de enviar.")
            return
        config = load_config(self.ctx)
        try:
            config.require_api_key()
        except ConfigError as exc:
            self._set_status(str(exc))
            from ui.chat_settings import show_settings_dialog

            show_settings_dialog(self.ctx, self._dialog)
            config = load_config(self.ctx)
            try:
                config.require_api_key()
            except ConfigError:
                return
        self._config = config

        include_context = True
        try:
            include_context = bool(self._controls["context"].State)
        except Exception:
            pass
        document = self._document()
        context = build_document_context(document, config.max_context_chars) if include_context else ""

        self._set_text("input", "")
        self._append_history("Tú", text)
        self._pending = []
        self._applied = False
        self._executor = None
        self._reset_picks()
        self._render_pending()
        self._set_running(True)
        self._set_status("Consultando al modelo...")

        client = LLMClient(config, self._session_id)
        self._session_id = client.session_id
        runner = QueryRunner(config)
        if self._agent is None:
            self._agent = Agent(client, runner)
        else:
            self._agent.client = client
            self._agent.query_runner = runner
            self._agent.refresh_system_prompt()

        self._generation += 1
        token = self._generation
        self._stop_event = threading.Event()
        worker = threading.Thread(
            target=self._run_worker,
            args=(self._agent, token, text, context, self._stop_event),
            daemon=True,
        )
        progress = threading.Thread(
            target=self._progress_worker,
            args=(token, self._stop_event),
            daemon=True,
        )
        worker.start()
        progress.start()

    def _progress_worker(self, token: int, stop_event: threading.Event) -> None:
        dots = ("", ".", "..", "...")
        index = 0
        while not stop_event.wait(0.7):
            if self._closed:
                return
            self._post_event(token, "progress", dots[index % len(dots)])
            index += 1

    def _run_worker(self, agent: Agent, token: int, text: str, context: str, stop_event: threading.Event) -> None:
        try:
            result = agent.run(text, context)
        except Exception as exc:
            if stop_event.is_set():
                self._post_event(token, "stopped", None)
            else:
                self._post_event(token, "error", str(exc))
            return
        self._post_event(token, "stopped" if stop_event.is_set() else "done", result)

    def _post_event(self, token: int, kind: str, payload: Any) -> None:
        if self._closed:
            return
        with self._lock:
            self._events.append((token, kind, payload))
        try:
            self._async.addCallback(self._callback, "ui")
        except Exception as exc:
            _LOG.warning("No se pudo notificar a la interfaz: %s", exc)

    def _on_async(self, data: Any) -> None:
        while not self._closed:
            with self._lock:
                if not self._events:
                    return
                event = self._events.popleft()
            token, kind, payload = event
            if token != self._generation:
                continue
            if kind == "done":
                self._handle_done(payload)
            elif kind == "error":
                self._handle_error(str(payload))
            elif kind == "stopped":
                self._handle_stopped()
            elif kind == "progress":
                self._handle_progress(str(payload))

    def _handle_progress(self, dots: str) -> None:
        if self._running:
            self._set_status(f"Consultando al modelo{dots}" + ("..." if not dots else ""))

    def _handle_done(self, result: Any) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        self._set_running(False)
        self._stop_event = None
        if result.errors:
            self._append_history("Avisos", "\n".join(result.errors))
        if result.text:
            self._append_history("Asistente", result.text)
        self._pending = list(result.actions)
        self._applied = False
        self._executor = None
        self._reset_picks()
        if self._pending:
            self._apply_preview()
        else:
            self._render_pending()
            self._set_status("Respuesta recibida.")

    def _handle_error(self, message: str) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        self._set_running(False)
        self._stop_event = None
        self._set_status("No se pudo completar la petición.")
        self._append_history("Error", message)

    def _handle_stopped(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        self._set_running(False)
        self._stop_event = None
        self._set_status("Petición detenida.")

    def _stop(self) -> None:
        if not self._running:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        self._set_status("Deteniendo la petición...")

    def _apply_preview(self) -> None:
        if not self._pending or self._running:
            return
        document = self._document()
        try:
            self._executor = Executor()
            descriptions = self._executor.apply(document, self._pending)
        except Exception as exc:
            self._pending = []
            self._applied = False
            self._executor = None
            if self._agent is not None:
                self._agent.resolve_pending(False, "No se pudieron aplicar los cambios.")
            self._render_pending()
            self._set_status("No se pudieron aplicar los cambios.")
            self._append_history("Error al aplicar", str(exc))
            _message(self.ctx, self._dialog, "Asistente IA", str(exc), error=True)
            return
        self._applied = True
        self._append_history("Vista previa aplicada", "\n".join(descriptions))
        self._render_pending()
        self._set_status(
            f"Vista previa aplicada: {len(descriptions)} cambio(s). Acepta o rechaza."
        )
        if not self._config.confirm_before_apply:
            self._accept_pending()

    def _accept_pending(self) -> None:
        if not self._pending or self._running:
            return
        selected = self._picked_actions()
        if not selected:
            self._reject_pending()
            if not self._pending:
                self._set_status("No marcaste cambios: se rechazó la vista previa.")
            return
        total = len(self._pending)
        if len(selected) == total:
            if self._agent is not None:
                self._agent.resolve_pending(True)
            if self._executor is not None:
                self._executor.accept()
            self._pending = []
            self._applied = False
            self._executor = None
            self._render_pending()
            self._append_history("Cambios aceptados", f"{total} cambio(s) se mantienen.")
            self._set_status("Cambios aceptados. Se mantienen en el documento.")
            return

        document = self._document()
        try:
            if self._executor is None:
                raise ValueError("No hay una vista previa que se pueda filtrar.")
            self._executor.revert(document)
        except Exception as exc:
            self._set_status("No se pudo deshacer la vista previa para filtrar los cambios.")
            self._append_history("Error al aceptar", str(exc))
            _message(self.ctx, self._dialog, "Asistente IA", str(exc), error=True)
            return

        try:
            replacement = Executor()
            replacement.apply(document, selected)
            replacement.accept()
        except Exception as exc:
            self._pending = []
            self._applied = False
            self._executor = None
            if self._agent is not None:
                self._agent.resolve_pending(False, "No se pudieron conservar los cambios marcados.")
            self._render_pending()
            self._set_status("No se pudieron conservar los cambios marcados.")
            self._append_history("Error al aceptar", str(exc))
            _message(self.ctx, self._dialog, "Asistente IA", str(exc), error=True)
            return

        rejected = total - len(selected)
        if self._agent is not None:
            self._agent.resolve_pending(
                True,
                f"Se conservaron {len(selected)} de {total} cambios propuestos.",
            )
        self._pending = []
        self._applied = False
        self._executor = None
        self._render_pending()
        self._append_history(
            "Cambios aceptados",
            f"{len(selected)} cambio(s) se mantienen; {rejected} se descartaron.",
        )
        self._set_status(
            f"{len(selected)} cambio(s) aceptados; {rejected} descartados."
        )

    def _reject_pending(self, silent: bool = False) -> None:
        if self._running or not self._pending:
            return
        count = len(self._pending)
        if self._applied:
            try:
                if self._executor is None:
                    raise ValueError("No hay una vista previa registrada por este chat.")
                self._executor.revert(self._document())
            except Exception as exc:
                if not silent:
                    self._set_status("No se pudo deshacer la vista previa.")
                    self._append_history("Error al rechazar", str(exc))
                    _message(self.ctx, self._dialog, "Asistente IA", str(exc), error=True)
                return
            self._append_history("Cambios rechazados", f"Se deshicieron {count} cambio(s).")
        if self._agent is not None:
            self._agent.resolve_pending(False)
        self._pending = []
        self._applied = False
        self._executor = None
        self._reset_picks()
        self._render_pending()
        if not silent:
            self._set_status("Cambios rechazados y deshechos.")

    def reset_chat(self) -> None:
        self._new_chat()

    def _new_chat(self) -> None:
        self._generation += 1
        if self._running and self._stop_event is not None:
            self._stop_event.set()
        self._stop_event = None
        self._set_running(False)
        with self._lock:
            self._events.clear()
        if self._pending:
            self._reject_pending(silent=True)
            if self._pending:
                self._set_status("No se pudo rechazar la vista previa. Revisa el documento.")
                return
        self._agent = None
        self._session_id = None
        self._pending = []
        self._applied = False
        self._executor = None
        self._reset_picks()
        self._history = ""
        self._set_text("history", "Asistente IA listo. Pide cambios para el documento activo.\n")
        self._set_text("input", "")
        self._render_pending()
        self._set_running(False)
        self._set_status("Nuevo chat.")
        try:
            self._controls["input"].setFocus()
        except Exception:
            pass
