#!/usr/bin/env python3
"""
gedcom_zoom.py

Shared zoom shortcut helpers for text and canvas-based views.
"""

import sys


_MOD_KEY = 'Command' if sys.platform == 'darwin' else 'Control'


def bind_zoom_shortcuts(target, zoom_in, zoom_out, zoom_reset):
    """Bind standard keyboard and mouse zoom shortcuts to a widget/window."""

    def _wrap(callback):
        def _handler(event=None):
            callback()
            return 'break'
        return _handler

    def _wheel(event):
        if getattr(event, 'delta', 0) > 0:
            zoom_in()
        else:
            zoom_out()
        return 'break'

    bindings = [
        (f'<{_MOD_KEY}-plus>', _wrap(zoom_in)),
        (f'<{_MOD_KEY}-equal>', _wrap(zoom_in)),
        (f'<{_MOD_KEY}-KP_Add>', _wrap(zoom_in)),
        (f'<{_MOD_KEY}-minus>', _wrap(zoom_out)),
        (f'<{_MOD_KEY}-KP_Subtract>', _wrap(zoom_out)),
        (f'<{_MOD_KEY}-0>', _wrap(zoom_reset)),
        (f'<{_MOD_KEY}-KP_0>', _wrap(zoom_reset)),
        (f'<{_MOD_KEY}-MouseWheel>', _wheel),
        (f'<{_MOD_KEY}-Button-4>', _wrap(zoom_in)),
        (f'<{_MOD_KEY}-Button-5>', _wrap(zoom_out)),
    ]
    for sequence, handler in bindings:
        target.bind(sequence, handler, add='+')


class TextZoomController:
    """Track point-size zoom for one text widget."""

    def __init__(self, widget, base_size, apply_size, *,
                 min_size=7, max_size=40, targets=None):
        self.widget = widget
        self.base_size = int(base_size)
        self.delta = 0
        self.min_size = min_size
        self.max_size = max_size
        self._apply_size = apply_size
        for target in targets or (getattr(widget, '_textbox', widget),):
            bind_zoom_shortcuts(
                target, self.zoom_in, self.zoom_out, self.zoom_reset)

    def _clamp(self, size):
        return max(self.min_size, min(self.max_size, int(size)))

    def _current_size(self):
        return self._clamp(self.base_size + self.delta)

    def set_base_size(self, base_size):
        """Update the unzoomed size, preserving the user's zoom delta."""
        self.base_size = int(base_size)
        self._apply_size(self._current_size())

    def zoom_in(self):
        """Increase the text size by one point."""
        next_size = self._clamp(self._current_size() + 1)
        self.delta = next_size - self.base_size
        self._apply_size(next_size)

    def zoom_out(self):
        """Decrease the text size by one point."""
        next_size = self._clamp(self._current_size() - 1)
        self.delta = next_size - self.base_size
        self._apply_size(next_size)

    def zoom_reset(self):
        """Return to the base size for this widget."""
        self.delta = 0
        self._apply_size(self._current_size())
