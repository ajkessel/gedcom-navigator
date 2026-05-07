"""
gedcom_theme.py

Theme constants, customtkinter appearance mapping, and the Tooltip widget helper.
"""

import sys
import tkinter as tk


THEME_NAMES = ('System', 'Light', 'Dark', 'Blue', 'Green')

# Maps stored theme name → (ctk_appearance_mode, ctk_color_theme)
CTK_THEME_MAP = {
    'System': ('system', 'blue'),
    'Light':  ('light',  'blue'),
    'Dark':   ('dark',   'blue'),
    'Blue':   ('light',  'blue'),
    'Green':  ('light',  'green'),
}

# Accent-aware colors for flagged rows and hyperlinks per mode
_FLAG_BG  = {'Light': '#fff4cc', 'Dark': '#3d3000'}
_LINK_COL = {'Light': '#1155bb', 'Dark': '#6bbfff'}


def get_flag_bg(is_dark: bool) -> str:
    """Return the background colour used to highlight DNA-flagged Treeview rows."""
    return _FLAG_BG['Dark'] if is_dark else _FLAG_BG['Light']


def get_link_color(is_dark: bool) -> str:
    """Return the foreground colour used for person-link text tags."""
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

    def __init__(self, widget, text):
        """Bind tooltip display behaviour to widget hover events."""
        self._widget = widget
        self._text = text
        self._tip = None
        widget.bind('<Enter>', self._show)
        widget.bind('<Leave>', self._hide)

    def _show(self, _event=None):
        """Create and position the tooltip window."""
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        if sys.platform == 'darwin':
            try:
                self._tip.tk.call(
                    'tk::unsupported::MacWindowStyle', 'style',
                    self._tip._w, 'help', 'noActivates',
                )
            except tk.TclError:
                self._tip.wm_overrideredirect(True)
        else:
            self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f'+{x}+{y}')
        self._tip.configure(background='#ffffe0')
        tk.Label(
            self._tip, text=self._text, justify='left',
            background='#ffffe0', relief='solid', borderwidth=1,
            wraplength=360, padx=4, pady=2,
        ).pack(padx=3, pady=3)

    def _hide(self, _event=None):
        """Destroy the tooltip window if it is visible."""
        if self._tip:
            self._tip.destroy()
            self._tip = None
