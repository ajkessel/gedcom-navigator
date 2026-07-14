"""Right-hand display pane for the tkinter-faithful layout (Phase 5).

Mirrors the tkinter "Display Pane": a mode selector (Profile / Matches / Paths), a
Profile sub-mode selector (Bio / Pedigree / Descendants / Graph), a swappable content
area, and a footer (Reverse / Copy / Save). Toga 0.5.6 has no segmented control, so the
selectors are button rows; the active button is marked with a leading "●" (backend-
independent) plus a highlight background where the backend honors it.

The content area shows exactly one view by swapping the content box's single child.
(Pack `display=NONE` does not reliably hide an already-realized widget on the Cocoa
backend, so we re-parent instead. Each view is re-populated when shown via the app's
_refresh_active_view, so a WebView reload on switch is harmless.)
"""
import toga
from toga.style.pack import COLUMN, ROW, Pack

MODES = [("profile", "Profile"), ("matches", "Matches"), ("paths", "Paths")]
PROFILE_SUBMODES = [
    ("bio", "Bio"), ("pedigree", "Pedigree"),
    ("descendants", "Descendants"), ("graph", "Graph"),
]
ACTIVE_BG = "#1f6feb"


class DisplayPane:
    def __init__(self, *, on_mode_change, on_submode_change,
                 on_reverse, on_copy, on_save):
        self._on_mode_change = on_mode_change
        self._on_submode_change = on_submode_change
        self.mode = "profile"
        self.submode = "bio"
        self._views = {}
        self._current_key = None

        self._mode_labels = dict(MODES)
        self._submode_labels = dict(PROFILE_SUBMODES)
        self._mode_buttons = {
            v: toga.Button(lbl, on_press=self._mode_handler(v),
                           style=Pack(margin=(0, 2)))
            for v, lbl in MODES
        }
        self.mode_row = toga.Box(
            style=Pack(direction=ROW, margin=(6, 6, 2, 6)),
            children=list(self._mode_buttons.values()))

        self._submode_buttons = {
            v: toga.Button(lbl, on_press=self._submode_handler(v),
                           style=Pack(margin=(0, 2)))
            for v, lbl in PROFILE_SUBMODES
        }
        self.submode_row = toga.Box(
            style=Pack(direction=ROW, margin=(0, 6, 4, 6)),
            children=list(self._submode_buttons.values()))
        # Holder so the sub-mode row can be shown/hidden without disturbing siblings.
        self._submode_holder = toga.Box(
            style=Pack(direction=COLUMN), children=[self.submode_row])

        self.content_box = toga.Box(style=Pack(direction=COLUMN, flex=1))

        self.reverse_btn = toga.Button(
            "Reverse", on_press=lambda w: on_reverse(),
            enabled=False, style=Pack(margin=(0, 4)))
        self.copy_btn = toga.Button(
            "Copy", on_press=lambda w: on_copy(), style=Pack(margin=(0, 4)))
        self.save_btn = toga.Button(
            "Save…", on_press=lambda w: on_save(), style=Pack(margin=(0, 4)))
        self.footer = toga.Box(
            style=Pack(direction=ROW, margin=6),
            children=[self.reverse_btn, self.copy_btn, self.save_btn])

        self.container = toga.Box(
            style=Pack(direction=COLUMN, flex=1),
            children=[self.mode_row, self._submode_holder, self.content_box, self.footer])

        self._refresh_selector_styles()
        self._sync_submode_visibility()

    # ---- view registration / swapping ----------------------------------
    def register_view(self, key, widget):
        """Register a view widget for `key` (added to the content box on demand)."""
        widget.style.flex = 1
        self._views[key] = widget

    def show_view(self, key):
        """Show the registered view for `key` by swapping the content box's child."""
        if key == self._current_key:
            return
        self.content_box.clear()
        widget = self._views.get(key)
        if widget is not None:
            self.content_box.add(widget)
        self._current_key = key

    # ---- selection state -------------------------------------------------
    def set_mode(self, mode, *, notify=False):
        self.mode = mode
        self._refresh_selector_styles()
        self._sync_submode_visibility()
        if notify:
            self._on_mode_change(mode)

    def set_submode(self, submode, *, notify=False):
        self.submode = submode
        self._refresh_selector_styles()
        if notify:
            self._on_submode_change(submode)

    def set_reverse_enabled(self, enabled):
        self.reverse_btn.enabled = enabled

    # ---- internals -------------------------------------------------------
    def _mode_handler(self, value):
        return lambda widget: self.set_mode(value, notify=True)

    def _submode_handler(self, value):
        return lambda widget: self.set_submode(value, notify=True)

    def _sync_submode_visibility(self):
        show = self.mode == "profile"
        present = self.submode_row in self._submode_holder.children
        if show and not present:
            self._submode_holder.add(self.submode_row)
        elif not show and present:
            self._submode_holder.remove(self.submode_row)

    def _refresh_selector_styles(self):
        for v, b in self._mode_buttons.items():
            self._style_button(b, self._mode_labels[v], v == self.mode)
        for v, b in self._submode_buttons.items():
            self._style_button(b, self._submode_labels[v], v == self.submode)

    @staticmethod
    def _style_button(button, label, active):
        button.text = f"● {label}" if active else label
        try:
            button.style.background_color = ACTIVE_BG if active else "transparent"
        except Exception:  # noqa: BLE001 — backend may reject the color
            pass
