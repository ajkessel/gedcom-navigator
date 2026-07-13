"""GEDCOM Navigator — Toga application (Phase 3: core UI complete).

Main window with an async (non-blocking) GEDCOM load, a searchable/filterable person
list, a detail pane, preferences persisted to the *same* settings.json as the tkinter
app (via ConfigManager), recent-file reopen, and a per-file home person. Graph + rich
results views arrive in Phase 4 (see spike/ for the proven approaches).

Run:  PYTHONPATH=src python -m gedcom_toga
"""
import asyncio
from pathlib import Path

import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_config import ConfigManager
from gedcom_data_model import GedcomDataModel

from . import person_detail as pd
from . import person_list as pl

# (stored value, menu label) for the name-order preference
NAME_ORDER_ITEMS = [("first_last", "Given name first"), ("last_first", "Surname first")]


class GedcomNavigatorToga(toga.App):
    def startup(self):
        self.config = ConfigManager(ConfigManager.default_path())
        self.model = GedcomDataModel()
        self.sorted_ids = []
        self._display_ids = []
        self.current_path = None

        # preferences (shared with the tkinter app's settings.json)
        self.fuzzy = bool(self.config.load_value("fuzzy_search", False))
        self.fuzzy_threshold = self.config.get_fuzzy_threshold()
        self.max_display = self.config.get_max_display()
        self.name_order = self.config.get_name_order()
        self.dna_keyword = self.config.get_tag_keyword()
        self.page_marker = self.config.get_page_marker()
        self.detection_fields = self.config.get_detection_fields()

        self.search = toga.TextInput(
            placeholder="Search people (name or ID)…",
            on_change=self.on_search, style=Pack(flex=1))
        self.dna_switch = toga.Switch(
            "DNA only", on_change=self.on_toggle, style=Pack(margin=(0, 8)))
        self.id_switch = toga.Switch(
            "Show IDs", value=self.config.get_show_ids(),
            on_change=self.on_toggle, style=Pack(margin=(0, 8)))
        self.people = toga.Table(
            columns=["Name", "Born", "Died"],
            on_select=self.on_person_select, style=Pack(flex=1))
        self.detail = toga.MultilineTextInput(readonly=True, style=Pack(flex=1))
        self.status = toga.Label("Open a GEDCOM file to begin.", style=Pack(margin=6))

        left = toga.Box(style=Pack(direction=COLUMN, flex=1), children=[
            toga.Box(style=Pack(direction=ROW, margin=6),
                     children=[self.search, self.dna_switch, self.id_switch]),
            self.people,
        ])
        split = toga.SplitContainer(content=[left, self.detail], style=Pack(flex=1))
        root = toga.Box(style=Pack(direction=COLUMN), children=[split, self.status])
        self.main_window = toga.MainWindow(title="GEDCOM Navigator (Toga)", size=(1100, 760))
        self.main_window.content = root

        self._build_commands()
        self.main_window.show()

        # reopen the most recent file if it still exists
        recent = [p for p in self.config.get_recent_files() if Path(p).exists()]
        if recent:
            asyncio.create_task(self._load(Path(recent[0])))

    # ---- menus ----------------------------------------------------------
    def _build_commands(self):
        self.cmd_set_home = toga.Command(
            self.on_set_home, "Set as Home Person",
            group=toga.Group.FILE, section=1, enabled=False)
        self.cmd_go_home = toga.Command(
            self.on_go_home, "Go to Home Person",
            group=toga.Group.FILE, section=1, enabled=False)
        self.commands.add(
            toga.Command(self.on_open, "Open GEDCOM…",
                         shortcut=toga.Key.MOD_1 + "o", group=toga.Group.FILE, order=1),
            toga.Command(self.on_preferences, "Preferences…",
                         shortcut=toga.Key.MOD_1 + ",", group=toga.Group.SETTINGS),
            self.cmd_set_home,
            self.cmd_go_home,
        )

    # ---- file loading ---------------------------------------------------
    async def on_open(self, widget, **kw):
        path = await self.main_window.dialog(
            toga.OpenFileDialog("Open GEDCOM", file_types=["ged", "GED", "zip"]))
        if path:
            await self._load(Path(path))

    async def _load(self, path):
        self.status.text = f"Loading {path.name}…"
        cache = self.paths.cache
        cache.mkdir(parents=True, exist_ok=True)
        try:
            from_cache, warning, error = await asyncio.to_thread(
                self.model.load, str(path),
                self.dna_keyword, self.page_marker, str(cache), self.detection_fields)
        except Exception as exc:  # noqa: BLE001 — surface any parse/IO failure
            self.status.text = f"Load failed: {exc}"
            return
        if error:
            self.status.text = f"Could not parse {path.name}: {error}"
            return
        self.current_path = path
        self.config.set_recent_files(
            pl.updated_recent(self.config.get_recent_files(), path))
        self.sorted_ids = pl.sorted_person_ids(self.model.individuals)
        self.search.value = ""
        self._refresh_people()
        note = " (from cache)" if from_cache else ""
        warn = f"   ⚠ {warning}" if warning else ""
        self.status.text = f"Loaded {len(self.model.individuals)} people{note}.{warn}"

        home = self.config.get_home_person(str(path))
        has_home = bool(home and home in self.model.individuals)
        self.cmd_go_home.enabled = has_home
        if has_home:
            self._select_person(home)

    # ---- person list ----------------------------------------------------
    def _refresh_people(self):
        ids, truncated = pl.visible_ids(
            self.model.individuals, self.search.value, self.sorted_ids,
            fuzzy=self.fuzzy, fuzzy_threshold=self.fuzzy_threshold,
            max_display=self.max_display, dna_only=self.dna_switch.value)
        self._display_ids = ids
        show_id = self.id_switch.value
        self.people.data = [
            pl.person_row(self.model.individuals, iid,
                          show_id=show_id, name_order=self.name_order)
            for iid in ids
        ]
        total, shown = len(self.model.individuals), len(ids)
        msg = f"Showing {shown} of {total} people"
        if truncated:
            msg += " — narrow your search"
        self.status.text = msg

    def _select_person(self, iid):
        """Scroll to a person in the current list and show their detail."""
        if iid in self._display_ids:
            try:
                self.people.scroll_to_row(self._display_ids.index(iid))
            except Exception:  # noqa: BLE001 — scrolling is best-effort
                pass
        self.detail.value = pd.detail_text(
            self.model.individuals, self.model.families, iid, show_id=self.id_switch.value)
        self.cmd_set_home.enabled = True

    def on_search(self, widget, **kw):
        if self.model.individuals:
            self._refresh_people()

    def on_toggle(self, widget, **kw):
        if self.model.individuals:
            self._refresh_people()
            self.on_person_select(self.people)   # reflect Show-IDs in the open detail

    def on_person_select(self, widget, **kw):
        row = self.people.selection
        iid = getattr(row, "id", None) if row else None
        if iid is None:
            self.detail.value = ""
            self.cmd_set_home.enabled = False
            return
        self.detail.value = pd.detail_text(
            self.model.individuals, self.model.families, iid, show_id=self.id_switch.value)
        self.cmd_set_home.enabled = True

    # ---- home person ----------------------------------------------------
    def on_set_home(self, widget, **kw):
        row = self.people.selection
        iid = getattr(row, "id", None) if row else None
        if iid and self.current_path:
            self.config.set_home_person(str(self.current_path), iid)
            self.cmd_go_home.enabled = True
            self.status.text = f"Home person set: {self.model.individuals[iid]['name']}"

    def on_go_home(self, widget, **kw):
        if not self.current_path:
            return
        home = self.config.get_home_person(str(self.current_path))
        if home and home in self.model.individuals:
            self.search.value = ""
            self._refresh_people()
            self._select_person(home)

    # ---- preferences ----------------------------------------------------
    def on_preferences(self, widget, **kw):
        fuzzy = toga.Switch("Fuzzy search", value=self.fuzzy)
        threshold = toga.NumberInput(min=0, max=1, step=0.01, value=self.fuzzy_threshold)
        maxdisp = toga.NumberInput(min=10, max=100000, step=100, value=self.max_display)
        order = toga.Selection(
            items=[label for _v, label in NAME_ORDER_ITEMS],
            value=dict(NAME_ORDER_ITEMS)[self.name_order])
        keyword = toga.TextInput(value=self.dna_keyword)
        marker = toga.TextInput(value=self.page_marker)
        win = toga.Window(title="Preferences", size=(480, 320))

        def field(label, widget):
            return toga.Box(style=Pack(direction=ROW, margin=(4, 8)), children=[
                toga.Label(label, style=Pack(width=170)), widget])

        def save(w):
            self.fuzzy = fuzzy.value
            self.fuzzy_threshold = float(threshold.value or self.fuzzy_threshold)
            self.max_display = int(maxdisp.value or self.max_display)
            self.name_order = next(v for v, label in NAME_ORDER_ITEMS if label == order.value)
            new_keyword = (keyword.value or "").strip() or "DNA"
            new_marker = (marker.value or "").strip()
            dna_changed = (new_keyword != self.dna_keyword or new_marker != self.page_marker)
            self.dna_keyword, self.page_marker = new_keyword, new_marker

            self.config.save_value("fuzzy_search", self.fuzzy)
            self.config.set_fuzzy_threshold(self.fuzzy_threshold)
            self.config.set_max_display(self.max_display)
            self.config.set_name_order(self.name_order)
            self.config.set_tag_keyword(self.dna_keyword)
            self.config.set_page_marker(self.page_marker)

            if self.model.individuals:
                if dna_changed:
                    self.model.reflag(self.dna_keyword, self.page_marker, self.detection_fields)
                self._refresh_people()
            win.close()

        win.content = toga.Box(style=Pack(direction=COLUMN, margin=10), children=[
            field("Fuzzy search", fuzzy),
            field("Fuzzy threshold (0–1)", threshold),
            field("Max results", maxdisp),
            field("Name order", order),
            field("DNA tag keyword", keyword),
            field("DNA page marker", marker),
            toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("Cancel", on_press=lambda w: win.close(),
                            style=Pack(flex=1, margin=(0, 4))),
                toga.Button("Save", on_press=save, style=Pack(flex=1, margin=(0, 4))),
            ]),
        ])
        self._prefs_window = win   # keep a reference so it isn't GC'd
        win.show()


def main():
    return GedcomNavigatorToga("GEDCOM Navigator", "com.ajkessel.gedcom-navigator")


if __name__ == "__main__":
    main().main_loop()
