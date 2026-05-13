"""
gedcom_tooltip.py

Tooltip widget helper for customtkinter controls.
"""

from time import time

from CTkToolTip import CTkToolTip as _CTkToolTip
from customtkinter import CTkFont, CTkLabel, ScalingTracker, ThemeManager


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

    def configure(self, **kwargs):
        super().configure(**kwargs)

    def hide(self) -> None:
        if not self.winfo_exists():
            return
        self.disable = True
        try:
            self.after_idle(self._deferred_withdraw)
        except Exception:
            pass

    def _deferred_withdraw(self):
        try:
            if self.winfo_exists():
                self.withdraw()
        except Exception:
            pass

    def _show(self):
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
        except Exception:
            pass

    def _redraw_frame(self):
        # Second draw after deiconify: the real Configure event has now
        # updated _current_width to the actual rendered size.  Drop the
        # winfo_ismapped() guard so this also runs if the mouse left before
        # the idle callback fired (keeping the canvas correct for next show).
        try:
            if self.winfo_exists() and hasattr(self, 'frame'):
                self.frame._draw()
        except Exception:
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

    def __init__(self, widget, text: str):
        self._impl = _SizedToolTip(
            widget, message=text, wraplength=360, justify='left', follow=True
        )
        if not Tooltip._enabled:
            self._impl.hide()
        Tooltip._instances.append(self)
