"""
gedcom_theme.py

Theme constants, customtkinter appearance mapping, and the Tooltip widget helper.
"""

from CTkToolTip import CTkToolTip as _CTkToolTip
from customtkinter import ThemeManager, CTkFont, CTkLabel

THEME_NAMES = ('System', 'Light', 'Dark', 'Blue', 'Green')

# Maps stored theme name → (ctk_appearance_mode, ctk_color_theme)
CTK_THEME_MAP = {
    'System': ('system', 'blue'),
    'Light':  ('light',  'blue'),
    'Dark':   ('dark',   'blue'),
    'Blue':   ('light',  'blue'),
    'Green':  ('light',  'green'),
}

# Accent-aware colors for flagged rows and hyperlinks per mode/theme
_FLAG_BG = {'Light': '#fff4cc', 'Dark': '#3d3000'}
_LINK_COL = {'Light': '#1155bb', 'Dark': '#6bbfff', 'Green': '#2e8b57'}


def get_flag_bg(is_dark: bool) -> str:
    """Return the background colour used to highlight DNA-flagged Treeview rows."""
    return _FLAG_BG['Dark'] if is_dark else _FLAG_BG['Light']


def get_link_color(is_dark: bool, theme_name: str = None) -> str:
    """Return the foreground colour used for person-link text tags."""
    if theme_name in _LINK_COL:
        return _LINK_COL[theme_name]
    return _LINK_COL['Dark'] if is_dark else _LINK_COL['Light']


def ttk_colors(is_dark: bool, theme_name=None) -> dict:
    """Return a colour dict for styling ttk Treeview / Spinbox / PanedWindow."""
    if is_dark:
        return {
            'bg':         '#2b2b2b',
            'fg':         '#DCE4EE',
            'field_bg':   '#343638',
            'select_bg':  '#4a7fa5',
            'select_fg':  '#DCE4EE',
            'heading_bg': '#3a3a3a',
            'trough':     '#1e1e1e',
        }
    if theme_name == 'Blue':
        return {
            'bg':         '#EBF0FA',
            'fg':         '#1a1a1a',
            'field_bg':   '#F8FAFE',
            'select_bg':  '#3B8ED0',
            'select_fg':  '#FFFFFF',
            'heading_bg': '#D8E1F0',
            'trough':     '#B9C7DF',
        }
    if theme_name == 'Green':
        return {
            'bg':         '#EBF5EB',
            'fg':         '#1a1a1a',
            'field_bg':   '#F8FCF8',
            'select_bg':  '#2E8B57',
            'select_fg':  '#FFFFFF',
            'heading_bg': '#D5E6D5',
            'trough':     '#B8D2B8',
        }
    return {
        'bg':         '#EBEBEB',
        'fg':         '#1a1a1a',
        'field_bg':   '#F9F9FA',
        'select_bg':  '#3B8ED0',
        'select_fg':  '#FFFFFF',
        'heading_bg': '#D1D1D1',
        'trough':     '#C5C5C5',
    }


class _SizedToolTip(_CTkToolTip):
    """
    CTkToolTip with some customizations.
    """

    def __init__(self, widget, message="", *args, **kwargs):
        self._base_font = CTkFont(**ThemeManager.theme["CTkFont"])
        self._bold_font = CTkFont(
            family=self._base_font.cget("family"),
            size=self._base_font.cget("size")+2,
            weight="bold",
        )
        super().__init__(widget, message="", font=self._base_font, *args, **kwargs)
        self._full_message = message
        self.bg_color = ThemeManager.theme.get(
            'CTkToplevel', {}).get('tooltip_bg_color', "#EEEEEE")
        self.text_color = ThemeManager.theme.get(
            'CTkToplevel', {}).get('tooltip_text_color', "#000000")
        self.frame.configure(border_width=2)

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
        if self.winfo_exists():
            self.minsize(0, 0)
            self.update_idletasks()
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()
            if w > 10 and h > 10:
                geom = self.geometry()
                pos = geom[geom.index('+'):] if '+' in geom else ''
                if pos:
                    self.geometry(f"{w}x{h}{pos}")
                self._sync_frame_size(w, h)
        if self.winfo_exists():
            self.after_idle(self._redraw_frame)
        super()._show()
        self.configure(bg_color=self.bg_color,
                       text_color=self.text_color, padx=4, pady=8)
        if "\n" not in self._full_message:
            self.configure(message=self._full_message, font=self._base_font)
            return
        first, rest = self._full_message.split("\n", 1)
        self.configure(message=first, font=self._bold_font,anchor="w")
        if not hasattr(self, "_rest_label"):
            self._rest_label = CTkLabel(
                self.message_label.master,   # same parent frame
                text=rest,
                font=self._base_font,
                text_color=self.text_color,
                justify="left",
                anchor="w",
                wraplength=self.message_label.cget("wraplength"),
            )
            self._rest_label.pack(padx=8,pady=(8,8),anchor="w")
        else:
            self._rest_label.configure(text=rest)

    def _sync_frame_size(self, w, h):
        # Directly update CTkFrame's internal dimension tracking and force a
        # full redraw before deiconify.  On Windows, withdraw() can reset
        # _current_width to ~0 via a Configure event, so a later
        # _set_appearance_mode() draws a 0×0 rounded rect (transparent).
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
            widget, message=text, wraplength=360, justify='left', follow=False
        )
        if not Tooltip._enabled:
            self._impl.hide()
        Tooltip._instances.append(self)
