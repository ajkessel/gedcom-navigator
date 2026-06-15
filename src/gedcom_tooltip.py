"""
gedcom_tooltip.py

Tooltip widget helper for customtkinter controls.
"""

import tkinter as tk
from weakref import WeakKeyDictionary

from customtkinter.windows.widgets import CTkToolTip

from gedcom_debug import log_exception


def _split_message(message: str):
    """Return (title, text) splitting on the first newline; title is None if no newline."""
    if "\n" in message:
        title, body = message.split("\n", 1)
        return title, body
    return None, message


class _TooltipMeta(type):
    """Metaclass so `Tooltip.enabled = value` propagates to all live instances."""

    @property
    def enabled(cls):
        return cls._enabled

    @enabled.setter
    def enabled(cls, value):
        cls._enabled = bool(value)
        state = "normal" if cls._enabled else "disabled"
        for tip in cls._instances:
            tip._impl.configure(state=state)


class Tooltip(metaclass=_TooltipMeta):
    """Hover tooltip backed by CTkToolTip with global enable/disable support."""

    _enabled: bool = True
    _instances: list = []
    _widget_texts = WeakKeyDictionary()

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        title, body = _split_message(text)
        self._impl = CTkToolTip(widget, title=title, text=body, mode="live_mouse",
                                label={"wraplength": 360})
        if not Tooltip._enabled:
            self._impl.configure(state="disabled")
        Tooltip._instances.append(self)
        self._remember_widget_text(widget, text)

    def update_text(self, text: str) -> None:
        """Update the tooltip message text."""
        self.text = text
        title, body = _split_message(text)
        self._impl.configure(title=title, text=body)
        self._remember_widget_text(self.widget, text)

    @classmethod
    def _remember_widget_text(cls, widget, text: str) -> None:
        try:
            cls._widget_texts[widget] = text
        except TypeError:
            pass
        try:
            widget._gedcom_tooltip_text = text
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception("storing tooltip text on widget")
            pass

    @classmethod
    def text_for(cls, widget):
        """Return the registered tooltip text for a widget, if any."""
        try:
            return cls._widget_texts.get(widget)
        except TypeError:
            return getattr(widget, '_gedcom_tooltip_text', None)


class TextTagTooltip:
    """Hover tooltip for a specific tag inside a Tk Text widget."""

    def __init__(self, text_widget, text: str):
        self.text_widget = text_widget
        self._destroyed = False
        self._anchor = tk.Frame(text_widget)
        title, body = _split_message(text)
        self._impl = CTkToolTip(self._anchor, title=title, text=body, delay=-1, mode="mouse",
                                label={"wraplength": 360})
        if not Tooltip._enabled:
            self._impl.configure(state="disabled")
        Tooltip._instances.append(self)
        text_widget.bind("<Destroy>", self._on_destroy, add="+")

    def is_for(self, text_widget) -> bool:
        """Return whether this tooltip is still usable for the given Text widget."""
        if self._destroyed or self.text_widget is not text_widget:
            return False
        try:
            return self._anchor.winfo_exists()
        except tk.TclError:
            return False

    def on_enter(self, event=None) -> None:
        """Show the tooltip at the current mouse position."""
        self._impl.show()

    def on_leave(self, event=None) -> None:
        """Hide the tooltip."""
        self._impl.close()

    def _on_destroy(self, _event=None) -> None:
        self._destroyed = True
        try:
            Tooltip._instances.remove(self)
        except ValueError:
            pass
        try:
            self._impl.destroy()
        except tk.TclError:
            pass


class CanvasTagTooltip:
    """Hover tooltip for a specific item tag inside a Tk Canvas widget."""

    def __init__(self, canvas, text: str):
        self.canvas = canvas
        self._destroyed = False
        self._anchor = tk.Frame(canvas)
        title, body = _split_message(text)
        self._impl = CTkToolTip(self._anchor, title=title, text=body, delay=-1, mode="mouse",
                                label={"wraplength": 360})
        if not Tooltip._enabled:
            self._impl.configure(state="disabled")
        Tooltip._instances.append(self)
        canvas.bind("<Destroy>", self._on_destroy, add="+")

    def on_enter(self, event=None) -> None:
        """Show the tooltip at the current mouse position."""
        if self._destroyed:
            return
        self._impl.show()

    def on_leave(self, event=None) -> None:
        """Hide the tooltip."""
        if self._destroyed:
            return
        self._impl.close()

    def destroy(self) -> None:
        """Destroy this tooltip and remove it from the global tooltip list."""
        self._on_destroy()

    def _on_destroy(self, _event=None) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        try:
            Tooltip._instances.remove(self)
        except ValueError:
            pass
        try:
            self._impl.destroy()
        except tk.TclError:
            pass
