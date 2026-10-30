"""UNO protocol handler used by the Asistente IA menu."""

from __future__ import annotations

import os
import sys
from typing import Any

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import uno
import unohelper
from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization

SCHEME = "org.libreofficeai:"
_CHATS: list[Any] = []


class ProtocolHandler(unohelper.Base, XDispatch, XDispatchProvider, XInitialization):
    def __init__(self, ctx: Any = None):
        self.ctx = ctx or uno.getComponentContext()
        self.frame = None
        self._chats = _CHATS

    def initialize(self, args: Any) -> None:
        for arg in args or ():
            if hasattr(arg, "getController"):
                self.frame = arg
            elif hasattr(arg, "Frame") and getattr(arg, "Frame", None) is not None:
                self.frame = arg.Frame

    def queryDispatch(self, url: Any, target: str, flags: int) -> Any:
        complete = str(getattr(url, "Complete", "") or "")
        if complete.startswith(SCHEME):
            return self
        return None

    def queryDispatches(self, requests: Any) -> tuple:
        result = []
        for request in requests:
            try:
                result.append(self.queryDispatch(request.URL, request.Target, request.Flags))
            except Exception:
                result.append(None)
        return tuple(result)

    def dispatch(self, url: Any, args: Any) -> None:
        complete = str(getattr(url, "Complete", "") or "")
        command = complete[len(SCHEME) :] if complete.startswith(SCHEME) else complete
        frame = self._frame()
        if frame is None:
            self._error("No hay una ventana de LibreOffice activa.")
            return
        try:
            if command == "settings":
                from ui.chat_settings import show_settings_dialog

                chat = self._find_chat(frame)
                parent = chat._dialog if chat is not None else None
                show_settings_dialog(self.ctx, parent)
                return

            chat = self._find_chat(frame)
            if chat is None:
                from ui.chat_dialog import ChatDialog

                chat = ChatDialog(self.ctx, frame)
                self._chats.append(chat)
            if command == "new":
                chat.reset_chat()
            chat.show()
        except Exception as exc:
            self._error(f"No se pudo abrir el Asistente IA: {exc}")

    def _frame(self) -> Any:
        if self.frame is not None:
            return self.frame
        try:
            desktop = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx
            )
            frame = desktop.getCurrentFrame()
            if frame is not None:
                return frame
            document = desktop.getCurrentComponent()
            if document is not None:
                return document.getCurrentController().getFrame()
            components = desktop.Components.createEnumeration()
            while components.hasMoreElements():
                component = components.nextElement()
                controller = component.getCurrentController()
                if controller is not None:
                    frame = controller.getFrame()
                    if frame is not None:
                        return frame
        except Exception:
            pass
        return None

    def _find_chat(self, frame: Any) -> Any:
        alive = []
        found = None
        for chat in self._chats:
            if getattr(chat, "_closed", False):
                continue
            alive.append(chat)
            if found is None:
                try:
                    if chat.frame == frame:
                        found = chat
                except Exception:
                    pass
        self._chats[:] = alive
        return found

    def _error(self, message: str) -> None:
        try:
            from ui.chat_dialog import _message

            _message(self.ctx, None, "Asistente IA", message, error=True)
        except Exception:
            pass

    def addStatusListener(self, listener: Any, url: Any) -> None:
        pass

    def removeStatusListener(self, listener: Any, url: Any) -> None:
        pass

    def addEventListener(self, listener: Any, url: Any) -> None:
        pass

    def removeEventListener(self, listener: Any, url: Any) -> None:
        pass


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    ProtocolHandler,
    "org.libreofficeai.ProtocolHandler",
    ("com.sun.star.frame.ProtocolHandler",),
)
