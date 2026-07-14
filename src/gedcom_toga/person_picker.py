"""Modal person picker (Phase 5.2) — choose a target person for path search.

Replicates the tkinter `_pick_person` (gedcom_gui_dialogs.py): a window with a search
box + person table; double-click or Select resolves the choice, Cancel/close resolves
None. Exposed as an awaitable: `chosen = await PersonPicker(model, ...).pick()`.
Reuses the toolkit-free person_list helpers for ordering/search/rows.
"""
import asyncio

import toga
from toga.sources import AccessorColumn
from toga.style.pack import COLUMN, ROW, Pack

from . import native_table as nt
from . import person_list as pl

COLUMN_WIDTHS = [None, 64, 64]


class PersonPicker:
    def __init__(self, model, *, name_order="first_last", max_display=2000,
                 title="Select a person"):
        self.model = model
        self.name_order = name_order
        self.max_display = max_display
        self._future = None
        self._ids = []
        self._sorted = pl.sorted_person_ids(model.individuals)

        self.search = toga.TextInput(
            placeholder="Search people (name or ID)…",
            on_change=self._refresh, style=Pack(flex=1, margin=6))
        self.table = toga.Table(
            columns=[
                AccessorColumn("Name", "name"),
                AccessorColumn("Born", "born"),
                AccessorColumn("Died", "died"),
            ],
            on_activate=self._on_activate, style=Pack(flex=1))
        select_btn = toga.Button("Select", on_press=self._on_select,
                                 style=Pack(flex=1, margin=(0, 4)))
        cancel_btn = toga.Button("Cancel", on_press=self._on_cancel,
                                 style=Pack(flex=1, margin=(0, 4)))
        self.window = toga.Window(title=title, size=(460, 560),
                                  on_close=self._on_window_close)
        self.window.content = toga.Box(style=Pack(direction=COLUMN, flex=1), children=[
            self.search,
            self.table,
            toga.Box(style=Pack(direction=ROW, margin=6),
                     children=[cancel_btn, select_btn]),
        ])

    async def pick(self):
        """Show the picker and await the chosen id (or None if cancelled)."""
        self._future = asyncio.get_event_loop().create_future()
        self.window.show()
        self._refresh()
        try:
            return await self._future
        finally:
            try:
                self.window.close()
            except Exception:  # noqa: BLE001 — already closed
                pass

    def _refresh(self, *args, **kw):
        ids, _trunc = pl.visible_ids(
            self.model.individuals, self.search.value, self._sorted,
            max_display=self.max_display)
        self._ids = ids
        self.table.data = [
            pl.person_row(self.model.individuals, iid, name_order=self.name_order)
            for iid in ids
        ]
        nt.apply_column_widths(self.table, COLUMN_WIDTHS)

    def _selected_id(self):
        row = self.table.selection
        return getattr(row, "id", None) if row else None

    def _resolve(self, value):
        if self._future is not None and not self._future.done():
            self._future.set_result(value)

    def _on_select(self, widget):
        self._resolve(self._selected_id())

    def _on_activate(self, widget, row=None, **kw):
        iid = getattr(row, "id", None) if row else self._selected_id()
        if iid:
            self._resolve(iid)

    def _on_cancel(self, widget):
        self._resolve(None)

    def _on_window_close(self, window, **kw):
        # Window closed via the title-bar control → treat as cancel.
        self._resolve(None)
        return True
