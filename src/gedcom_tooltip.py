"""
gedcom_tooltip.py

Tooltip widget helper for customtkinter controls.
"""

import sys
import tkinter as tk
from weakref import WeakKeyDictionary
from time import time

from CTkToolTip import CTkToolTip as _CTkToolTip
from customtkinter import CTkFont, CTkLabel, ScalingTracker, ThemeManager

from gedcom_debug import log_exception, log_exception_once


# Custom tooltip implementation to support multi-line messages with the first line bolded.
# I'd like to replace this with a more robust solution that doesn't rely on internal
# CTkToolTip implementation details--and ideally renders tooltips with an OS-native
# method (e.g. Cocoa on Mac), but this will do for now.


class _SizedToolTip(_CTkToolTip):
    """
    CTkToolTip with some customizations.
    """

    def __init__(self, widget, *args, message="", **kwargs):
        self._base_font = CTkFont(**ThemeManager.theme["CTkFont"])
        # start with an empty message since we will be customizing the display
        # in _show() to support multi-line text with different fonts
        super().__init__(widget, message="", font=self._base_font, *args, **kwargs)
        self._configure_macos_window_behavior()
        # when user starts typing in text entry box, tooltip should disappear as if
        # the mouse pointer had left the window
        self.widget.bind("<Key>", self.on_leave, add="+")
        self._bold_font = CTkFont(
            family=self._base_font.cget("family"),
            size=self._base_font.cget("size") + 2,
            weight="bold",
        )
        self._full_message = message
        self._rest_label = None  # placeholder for multiline tooltip labels
        # save original y_offset in case tooltip near edge of display
        self.original_y_offset = self.y_offset
        self.original_x_offset = self.x_offset
        self.bg_color = ThemeManager.theme.get(
            'CTkToplevel', {}).get('tooltip_bg_color', "#EEEEEE")
        self.text_color = ThemeManager.theme.get(
            'CTkToplevel', {}).get('tooltip_text_color', "#000000")
        self.scaling = ScalingTracker.get_widget_scaling(self)
        self.frame.configure(border_width=2, corner_radius=10)
        self.configure(bg_color=self.bg_color,
                       text_color=self.text_color,
                       padx=4, pady=8)

    # CTkToolTip subclasses a plain tkinter.Toplevel but fills itself with CTk
    # widgets (CTkFrame/CTkLabel). Those widgets register *this* window with
    # customtkinter's ScalingTracker, whose check_dpi_scaling loop calls
    # block/unblock_update_dimensions_event() on the window when it detects a
    # monitor DPI change (Windows only). Those methods only exist on
    # CTk/CTkToplevel, so a bare Toplevel raises AttributeError intermittently.
    # Provide them as no-ops matching CTk's own implementation; the surrounding
    # update_scaling_callbacks_for_window() still runs and rescales the inner
    # widgets correctly.
    def block_update_dimensions_event(self):
        self._block_update_dimensions_event = False

    def unblock_update_dimensions_event(self):
        self._block_update_dimensions_event = False

    def _configure_macos_window_behavior(self):
        if sys.platform != 'darwin':
            return
        try:
            owner = self.widget.winfo_toplevel()
            if owner is not self:
                self.transient(owner)
        except tk.TclError:
            pass
        try:
            self.tk.call(
                "::tk::unsupported::MacWindowStyle",
                "style",
                self,
                "help",
                "noActivates",
            )
        except tk.TclError:
            pass

    # currently not using any subclass of configure
    # def configure(self, message: str = None, delay: float = None, bg_color: str = None, **kwargs):
    #     super().configure(message, delay, bg_color, **kwargs)

    def hide(self) -> None:
        if not self.winfo_exists():
            return
        self.disable = True
        try:
            self.after_idle(self._deferred_withdraw)
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception_once(
                'tooltip-hide-after-idle',
                "scheduling tooltip hide",
            )
            pass

    def _deferred_withdraw(self):
        try:
            if self.winfo_exists():
                self.withdraw()
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception_once(
                'tooltip-deferred-withdraw',
                "withdrawing tooltip",
            )
            pass

    def _show(self):
        try:
            if not self.widget.winfo_exists():
                return
        except tk.TclError:
            return
        self.x_offset = self.original_x_offset
        self.y_offset = self.original_y_offset
        (pointer_x, pointer_y) = self.winfo_pointerxy()
        tooltip_width = 0
        tooltip_height = 0
        if "\n" not in self._full_message:
            self.configure(message=self._full_message, font=self._base_font)
            self.update_idletasks()
            tooltip_height = self.winfo_reqheight()
            tooltip_width = self.winfo_reqwidth()
        else:
            first, rest = self._full_message.split("\n", 1)
            self.configure(message=first, font=self._bold_font, anchor="w")
            if getattr(self, '_rest_label', None) is None:
                self._rest_label = CTkLabel(
                    self.message_label.master,
                    text=rest,
                    font=self._base_font,
                    text_color=self.text_color,
                    justify="left",
                    anchor="w",
                    wraplength=self.message_label.cget("wraplength"),
                )
                self._rest_label.pack(padx=8, pady=(8, 8), anchor="w")
            else:
                self._rest_label.configure(text=rest)
            width_first = self.winfo_reqwidth()
            width_rest = self._rest_label.winfo_reqwidth()
            self.update_idletasks()
            tooltip_width = max(width_first, width_rest)
            tooltip_height = self.winfo_reqheight()

        (screen_width, screen_height) = (
            self.widget.winfo_screenwidth() * self.scaling,
            self.widget.winfo_screenheight() * self.scaling,
        )

        if self.y_offset >= 0 and (pointer_y + tooltip_height + self.y_offset > screen_height):
            self.y_offset = -tooltip_height
        if self.x_offset >= 0 and (pointer_x + tooltip_width + self.x_offset > screen_width):
            self.x_offset = -tooltip_width
        super()._show()

    # override default on_enter event to remove offset calculation, since we perform that
    # separately in _show() to account for the actual tooltip size after rendering the message
    # this is a bit of an ugly solution but it allows us to support multi-line tooltips with
    # different font styles without needing to rewrite the entire tooltip implementation
    def on_enter(self, event) -> None:
        """
        Processes motion within the widget including entering and moving.
        """

        if self.disable:
            return
        self.last_moved = time()
        if self.status == "outside":
            self.status = "inside"
        if not self.follow:
            if self.status == "visible":
                return
            else:
                self.status = "inside"
        self.geometry(
            f"+{event.x_root + self.x_offset}+{event.y_root + self.y_offset}")
        self.after(int(self.delay * 1000), self._show)

    def _sync_frame_size(self, w, h):
        # Directly update CTkFrame's internal dimension tracking and force a
        # full redraw before deiconify.  On Windows, withdraw() can reset
        # _current_width to ~0 via a Configure event, so a later
        # _set_appearance_mode() draws a 0x0 rounded rect (transparent).
        # Setting _current_width = w/scale here ensures _draw() uses the
        # correct size regardless of the stale tracked value.
        try:
            if not (self.winfo_exists() and hasattr(self, 'frame')):
                return
            scale = self.frame._get_widget_scaling()
            self.frame._current_width = w / scale
            self.frame._current_height = h / scale
            self.frame._draw()
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception_once(
                'tooltip-sync-frame-size',
                "synchronizing tooltip frame size",
            )
            pass

    def _redraw_frame(self):
        # Second draw after deiconify: the real Configure event has now
        # updated _current_width to the actual rendered size.  Drop the
        # winfo_ismapped() guard so this also runs if the mouse left before
        # the idle callback fired (keeping the canvas correct for next show).
        try:
            if self.winfo_exists() and hasattr(self, 'frame'):
                self.frame._draw()
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception_once(
                'tooltip-redraw-frame',
                "redrawing tooltip frame",
            )
            pass


class _TooltipMeta(type):
    """Metaclass so `Tooltip.enabled = value` propagates to all live instances."""

    @property
    def enabled(cls):
        return cls._enabled

    @enabled.setter
    def enabled(cls, value):
        cls._enabled = bool(value)
        for tip in cls._instances:
            tip._impl.show() if value else tip._impl.hide()


class Tooltip(metaclass=_TooltipMeta):
    """Hover tooltip backed by CTkToolTip with global enable/disable support."""

    _enabled: bool = True
    _instances: list = []
    _widget_texts = WeakKeyDictionary()

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._impl = _SizedToolTip(
            widget, message=text, wraplength=360, justify='left', follow=True
        )
        if not Tooltip._enabled:
            self._impl.hide()
        Tooltip._instances.append(self)
        self._remember_widget_text(widget, text)

    def update_text(self, text: str) -> None:
        """Update the tooltip message text."""
        self.text = text
        self._impl._full_message = text
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
        self._impl = _SizedToolTip(
            self._anchor, message=text, wraplength=360, justify='left',
            follow=True
        )
        if not Tooltip._enabled:
            self._impl.hide()
        Tooltip._instances.append(self)
        text_widget.bind("<Destroy>", self._on_destroy, add="+")

    def is_for(self, text_widget) -> bool:
        """Return whether this tooltip is still usable for the given Text widget."""
        if self._destroyed or self.text_widget is not text_widget:
            return False
        try:
            return self._anchor.winfo_exists() and self._impl.winfo_exists()
        except tk.TclError:
            return False

    def on_enter(self, event) -> None:
        """Show or move the tooltip from a Text tag event."""
        self._impl.on_enter(event)

    def on_leave(self, event=None) -> None:
        """Hide the tooltip when the pointer leaves the Text tag."""
        self._impl.on_leave(event)

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
        self._impl = _SizedToolTip(
            self._anchor, message=text, wraplength=360, justify='left',
            follow=True
        )
        if not Tooltip._enabled:
            self._impl.hide()
        Tooltip._instances.append(self)
        canvas.bind("<Destroy>", self._on_destroy, add="+")

    def on_enter(self, event) -> None:
        """Show or move the tooltip from a Canvas tag event."""
        if self._destroyed:
            return
        self._impl.on_enter(event)

    def on_leave(self, event=None) -> None:
        """Hide the tooltip when the pointer leaves the Canvas tag."""
        if self._destroyed:
            return
        self._impl.on_leave(event)

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
