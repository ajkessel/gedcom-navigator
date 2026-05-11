"""
gedcom_theme.py

Theme constants, customtkinter appearance mapping, and the Tooltip widget helper.
"""

from CTkToolTip import CTkToolTip as _CTkToolTip


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
        self._impl = _CTkToolTip(
            widget, message=text, wraplength=360, justify='left', follow=False,
        )
        if not Tooltip._enabled:
            self._impl.hide()
        Tooltip._instances.append(self)
