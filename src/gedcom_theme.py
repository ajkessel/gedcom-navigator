"""
gedcom_theme.py

Theme constants, customtkinter appearance mapping, and the Tooltip widget helper.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont


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
_FLAG_BG  = {'Light': '#fff4cc', 'Dark': '#3d3000'}
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


class Tooltip:
    """Small hover tooltip attached to a Tkinter widget."""

    _active: 'Tooltip | None' = None  # class-level: currently visible tooltip

    def __init__(self, widget, text):
        """Bind tooltip display behaviour to widget hover events."""
        self._widget = widget
        self._text = text
        self._tip = None
        self._hide_after = None  # pending after() id for debounced hide (macOS)
        self._cursor_x = None   # cursor position captured at Enter time (macOS)
        self._cursor_y = None
        widget.bind('<Enter>', self._show)
        widget.bind('<Leave>', self._on_leave)
        widget.bind('<ButtonPress>', self._hide)
        widget.bind('<KeyPress>', self._hide)

    def _apply_window_style(self):
        """Make the tooltip popup behave like a native transient helper."""
        if sys.platform == 'darwin':
            try:
                self._tip.tk.call(
                    'tk::unsupported::MacWindowStyle', 'style',
                    self._tip._w, 'help', 'noActivates',
                )
            except tk.TclError:
                pass
        else:
            try:
                self._tip.wm_attributes('-topmost', True)
            except tk.TclError:
                pass
            if sys.platform == 'win32':
                try:
                    self._tip.wm_attributes('-toolwindow', True)
                except tk.TclError:
                    pass
        # Always set overrideredirect so the tooltip window never intercepts
        # mouse events — on macOS omitting this caused <Leave> events to be
        # missed, leaving multiple stale tooltips on screen simultaneously.
        self._tip.wm_overrideredirect(True)

    def _style_tip_widget(self, widget, *, outer=False):
        """Apply platform-native tooltip colours to a widget."""
        is_frame = isinstance(widget, tk.Frame)
        if sys.platform == 'win32':
            kw = {'background': 'SystemInfoBackground'}
            if not is_frame:
                kw['foreground'] = 'SystemInfoText'
            if outer:
                kw.update(relief='solid', borderwidth=1)
            widget.configure(**kw)
        elif sys.platform == 'darwin':
            for bg_name in ('systemHelpBackgroundColor', 'systemWindowBackgroundColor'):
                try:
                    widget.configure(background=bg_name)
                    break
                except tk.TclError:
                    pass
            if not is_frame:
                try:
                    widget.configure(foreground='systemTextColor')
                except tk.TclError:
                    pass

    def _create_label(self):
        """Create tooltip content with the first line bold when a newline is present."""
        parts = self._text.split('\n', 1)

        if len(parts) == 1:
            label = tk.Label(self._tip, text=self._text, justify='left',
                             wraplength=360, padx=6, pady=3)
            self._style_tip_widget(label, outer=True)
            return label

        title, body = parts
        try:
            base = tkfont.nametofont('TkTooltipFont')
        except tk.TclError:
            base = tkfont.nametofont('TkDefaultFont')
        bold_font = tkfont.Font(family=base.cget('family'),
                                size=base.cget('size'), weight='bold')

        frame = tk.Frame(self._tip)
        self._style_tip_widget(frame, outer=True)

        title_lbl = tk.Label(frame, text=title, font=bold_font, justify='left',
                             wraplength=360, padx=6, anchor='w')
        self._style_tip_widget(title_lbl)
        title_lbl.pack(fill='x', pady=(3, 0))

        body_lbl = tk.Label(frame, text=body, justify='left',
                            wraplength=360, padx=6, anchor='w')
        self._style_tip_widget(body_lbl)
        body_lbl.pack(fill='x', pady=(0, 3))

        return frame

    def _position_tip(self):
        """Place the tooltip near the widget without running off screen.

        On macOS: prefer above the cursor so the popup doesn't land on widgets
        in the row directly below (e.g. filter entry below the search row),
        which causes spurious Enter events and flicker.  Fall back to below
        the cursor only when above would clip the menu bar.

        On other platforms: prefer below the widget; flip above when below
        would overflow the screen.  Never clamp vertically into the widget's
        own bounds — that causes a Leave event on Windows (flicker loop).
        """
        self._tip.update_idletasks()
        req_w = self._tip.winfo_reqwidth()
        req_h = self._tip.winfo_reqheight()
        screen_w = self._tip.winfo_screenwidth()
        screen_h = self._tip.winfo_screenheight()
        wx = self._widget.winfo_rootx()
        wy = self._widget.winfo_rooty()
        wh = self._widget.winfo_height()
        x = max(0, min(wx + 20, screen_w - req_w - 4))
        if sys.platform == 'darwin' and self._cursor_y is not None:
            # Position above the cursor so the popup stays in the same UI row.
            _MENU_BAR_H = 28
            y_above = self._cursor_y - req_h - 8
            y_below = self._cursor_y + 20
            y = y_above if y_above >= _MENU_BAR_H else min(y_below, screen_h - req_h - 4)
        else:
            y_below = wy + wh + 4
            y_above = wy - req_h - 4
            if y_below + req_h <= screen_h - 4:
                y = y_below
            else:
                y = max(0, y_above)
        self._tip.wm_geometry(f'+{x}+{y}')

    def _on_leave(self, _event=None):
        """Handle <Leave>: debounce on macOS to ignore spurious events."""
        if sys.platform == 'darwin' and self._tip is not None:
            if self._hide_after is None:
                self._hide_after = self._widget.after(150, self._hide_if_outside)
        else:
            self._hide()

    def _hide_if_outside(self):
        """Debounced hide: only destroy the tooltip if the pointer is truly gone."""
        self._hide_after = None
        if self._tip is None:
            return
        px = self._widget.winfo_pointerx()
        py = self._widget.winfo_pointery()
        wx = self._widget.winfo_rootx()
        wy = self._widget.winfo_rooty()
        ww = self._widget.winfo_width()
        wh = self._widget.winfo_height()
        if not (wx <= px <= wx + ww and wy <= py <= wy + wh):
            self._hide()

    def _poll_mouse(self):
        """macOS only: catch missed <Leave> events via periodic position check."""
        if self._tip is None:
            return
        px = self._widget.winfo_pointerx()
        py = self._widget.winfo_pointery()
        wx = self._widget.winfo_rootx()
        wy = self._widget.winfo_rooty()
        ww = self._widget.winfo_width()
        wh = self._widget.winfo_height()
        inside = wx <= px <= wx + ww and wy <= py <= wy + wh
        if not inside and self._hide_after is None:
            self._hide_after = self._widget.after(150, self._hide_if_outside)
        elif inside and self._hide_after is not None:
            self._widget.after_cancel(self._hide_after)
            self._hide_after = None
        self._widget.after(100, self._poll_mouse)

    def _show(self, event=None):
        """Create and position the tooltip window."""
        # Cancel any pending debounced hide (spurious <Leave>/<Enter> pair).
        if self._hide_after is not None:
            self._widget.after_cancel(self._hide_after)
            self._hide_after = None
        # Dismiss any other tooltip left visible due to a missed <Leave>.
        if Tooltip._active is not None and Tooltip._active is not self:
            Tooltip._active._hide()
        if self._tip is not None:
            return
        # Capture cursor position for macOS above-cursor placement.
        self._cursor_x = getattr(event, 'x_root', None)
        self._cursor_y = getattr(event, 'y_root', None)
        Tooltip._active = self
        self._tip = tk.Toplevel(self._widget)
        self._tip.withdraw()
        self._apply_window_style()
        label = self._create_label()
        label.pack()
        self._position_tip()
        self._tip.deiconify()
        if sys.platform == 'darwin':
            self._widget.after(100, self._poll_mouse)

    def _hide(self, _event=None):
        """Destroy the tooltip window if it is visible."""
        if self._hide_after is not None:
            self._widget.after_cancel(self._hide_after)
            self._hide_after = None
        if self._tip:
            self._tip.destroy()
            self._tip = None
        if Tooltip._active is self:
            Tooltip._active = None
