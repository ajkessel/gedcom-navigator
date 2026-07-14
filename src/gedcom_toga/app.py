"""GEDCOM Navigator — Toga application (Phase 5 in progress).

tkinter-faithful layout: a persistent left person-list pane + a right display pane that
switches modes (Profile / Matches / Paths), with Profile sub-modes (Bio / Pedigree /
Descendants / Graph). Features: async GEDCOM load, searchable/filterable person list,
clickable HTML person links, canvas graph, preferences persisted to the *same*
settings.json as the tkinter app, recent-file reopen, and per-file home person.

Run:  PYTHONPATH=src python -m gedcom_toga
"""
import asyncio
import json
import os
import threading
from pathlib import Path

import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_config import ConfigManager
from gedcom_data_model import GedcomDataModel

try:
    from gedcom_search import SearchCancelled
except Exception:  # noqa: BLE001 — fall back to a broad guard if the name moves
    class SearchCancelled(Exception):
        pass

from . import native_table as nt
from . import person_list as pl
from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)

from .bio_view import BioView
from .display_pane import DisplayPane
from .family_graph_window import FamilyGraphWindow
from .matches_view import MatchesView
from .path_graph_window import PathGraphWindow
from .paths_view import PathsView
from .person_picker import PersonPicker
from .results_view import ResultsView

# Fixed pixel widths for the year columns; Name (None) absorbs the remaining space.
PEOPLE_COLUMN_WIDTHS = [None, 64, 64]

# (stored value, menu label) for the name-order preference
NAME_ORDER_ITEMS = [("first_last", "Given name first"), ("last_first", "Surname first")]


class GedcomNavigatorToga(toga.App):
    def startup(self):
        self.config = ConfigManager(ConfigManager.default_path())
        self.model = GedcomDataModel()
        self.sorted_ids = []
        self._display_ids = []
        self.current_path = None
        self.current_person = None
        self._matches_cancel = None   # threading.Event for the in-flight DNA search
        self._matches_gen = 0         # generation counter to drop stale search results
        self._paths_cancel = None     # threading.Event for the in-flight path search
        self._paths_gen = 0
        self._path_target = None      # chosen destination person for path search

        # preferences (shared with the tkinter app's settings.json)
        self.fuzzy = bool(self.config.load_value("fuzzy_search", False))
        self.fuzzy_threshold = self.config.get_fuzzy_threshold()
        self.max_display = self.config.get_max_display()
        self.name_order = self.config.get_name_order()
        self.dna_keyword = self.config.get_tag_keyword()
        self.page_marker = self.config.get_page_marker()
        self.detection_fields = self.config.get_detection_fields()

        # List view (left pane + detail)
        self.search = toga.TextInput(
            placeholder="Search people (name or ID)…",
            on_change=self.on_search, style=Pack(flex=1))
        self.dna_switch = toga.Switch(
            "DNA only", on_change=self.on_toggle, style=Pack(margin=(0, 8)))
        self.id_switch = toga.Switch(
            "Show IDs", value=self.config.get_show_ids(),
            on_change=self.on_toggle, style=Pack(margin=(0, 8)))
        # AccessorColumn maps each heading to its data accessor. Toga has no public
        # column-width API (beeware/toga#4238) — widths are applied natively after
        # layout via nt.apply_column_widths(); see native_table.py.
        from toga.sources import AccessorColumn
        self.people = toga.Table(
            columns=[
                AccessorColumn("Name", "name"),
                AccessorColumn("Born", "born"),
                AccessorColumn("Died", "died"),
            ],
            on_select=self.on_person_select,
            style=Pack(flex=1)
        )
        left = toga.Box(style=Pack(direction=COLUMN, flex=1), children=[
            toga.Box(style=Pack(direction=ROW, margin=6),
                     children=[self.search, self.dna_switch, self.id_switch]),
            self.people,
        ])

        # ---- display-pane views ----
        # Bio (Profile → Bio): WebView profile with clickable family links.
        self.bio_view = BioView(
            self.model, on_person_click=self._on_results_person_click)
        # Family graph opens in its own window (see _open_graph_window); not a sub-mode.
        self._graph_window = None
        # Pedigree / Descendants (Profile sub-modes): WebView reports.
        self.pedigree_view = ResultsView(
            self.model.individuals, self.model.families,
            on_person_click=self._on_results_person_click)
        self.descendants_view = ResultsView(
            self.model.individuals, self.model.families,
            on_person_click=self._on_results_person_click)
        # Matches mode (5.1) + Paths mode (5.2).
        self.matches_view = MatchesView(
            self.model,
            on_person_click=self._on_results_person_click,
            on_params_change=self._trigger_matches,
            on_relationship_click=self._open_path_graph,
            top_n=self.config.get_top_n(), max_depth=self.config.get_max_depth())
        self.paths_view = PathsView(
            self.model,
            on_person_click=self._on_results_person_click,
            on_change_target=self._change_path_target,
            on_relationship_click=self._open_path_graph,
            on_params_change=self._trigger_paths,
            top_n=self.config.get_top_n(), max_depth=self.config.get_max_depth())
        self._path_graph_window = None

        # Current mode/sub-mode (mirrors the tkinter display_mode / profile_sub_mode).
        self.mode = "profile"
        self.submode = "bio"
        self.display = DisplayPane(
            on_mode_change=self._on_mode_change,
            on_submode_change=self._on_submode_change,
            on_reverse=self._on_reverse,
            on_copy=self._on_copy,
            on_save=self._on_save)
        self.display.register_view("bio", self.bio_view.container)
        self.display.register_view("pedigree", self.pedigree_view.container)
        self.display.register_view("descendants", self.descendants_view.container)
        self.display.register_view("matches", self.matches_view.container)
        self.display.register_view("paths", self.paths_view.container)
        self.display.show_view("bio")

        # Left list + right display pane, list always visible (tkinter-faithful).
        split = toga.SplitContainer(
            content=[(left, 2), (self.display.container, 3)], style=Pack(flex=1))

        self.status = toga.Label("Open a GEDCOM file to begin.", style=Pack(margin=6))
        root = toga.Box(style=Pack(direction=COLUMN), children=[split, self.status])
        self.main_window = toga.MainWindow(title="GEDCOM Navigator", size=(1100, 760))
        self.main_window.content = root

        self._build_commands()
        self.main_window.show()

        # Toga has no column-width API (beeware/toga#4238); set them natively now that
        # the table is realized. Reapplied after each data load in _refresh_people.
        nt.apply_column_widths(self.people, PEOPLE_COLUMN_WIDTHS)

        # Start polling for results/matches view link clicks
        self.bio_view.start_polling()
        self.pedigree_view.start_polling()
        self.descendants_view.start_polling()
        self.matches_view.start_polling()
        self.paths_view.start_polling()

        # reopen the most recent file if it still exists
        recent = [p for p in self.config.get_recent_files() if Path(p).exists()]
        if recent:
            asyncio.create_task(self._load(Path(recent[0])))

    @staticmethod
    def _placeholder(message):
        return toga.Box(style=Pack(direction=COLUMN, flex=1), children=[
            toga.Label(message, style=Pack(margin=12))])

    # ---- menus ----------------------------------------------------------
    def _build_commands(self):
        self.cmd_set_home = toga.Command(
            self.on_set_home, "Set as Home Person",
            group=toga.Group.FILE, section=1, enabled=False)
        self.cmd_go_home = toga.Command(
            self.on_go_home, "Go to Home Person",
            group=toga.Group.FILE, section=1, enabled=False)

        # View menu commands — modes + Profile sub-modes (mirrors tkinter shortcuts).
        view_group = toga.Group.VIEW
        self.commands.add(
            toga.Command(self.on_open, "Open GEDCOM…",
                         shortcut=toga.Key.MOD_1 + "o", group=toga.Group.FILE, order=1),
            toga.Command(self.on_preferences, "Preferences…",
                         shortcut=toga.Key.MOD_1 + ",", group=toga.Group.SETTINGS),
            self.cmd_set_home,
            self.cmd_go_home,
            toga.Command(lambda w: self._set_submode("bio"), "Profile: Bio",
                         shortcut=toga.Key.MOD_1 + "b", group=view_group, section=0),
            toga.Command(lambda w: self._set_submode("pedigree"), "Profile: Pedigree",
                         shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + "p",
                         group=view_group, section=0),
            toga.Command(lambda w: self._set_submode("descendants"), "Profile: Descendants",
                         shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + "d",
                         group=view_group, section=0),
            toga.Command(lambda w: self._set_mode("matches"), "DNA Matches",
                         shortcut=toga.Key.MOD_1 + "n", group=view_group, section=1),
            toga.Command(lambda w: self._set_mode("paths"), "Relationship Paths",
                         shortcut=toga.Key.MOD_1 + "p", group=view_group, section=1),
            toga.Command(lambda w: self._open_graph_window("tree"), "Show Family Tree",
                         shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + "t",
                         group=view_group, section=2),
            toga.Command(lambda w: self._open_graph_window("pedigree"), "Show Pedigree Graph",
                         shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + "g",
                         group=view_group, section=2),
            toga.Command(lambda w: self._open_graph_window("descendant"),
                         "Show Descendant Graph", group=view_group, section=2),
        )

    # ---- mode / view switching ------------------------------------------
    def _set_mode(self, mode):
        """Programmatically switch mode (updates selector UI + shown view)."""
        self.mode = mode
        self.display.set_mode(mode)
        self._show_mode()

    def _set_submode(self, submode):
        """Programmatically switch to a Profile sub-mode."""
        self.mode = "profile"
        self.submode = submode
        self.display.set_mode("profile")
        self.display.set_submode(submode)
        self._show_mode()

    def _on_mode_change(self, mode):
        """User clicked a mode button."""
        self.mode = mode
        self._show_mode()

    def _on_submode_change(self, submode):
        """User clicked a Profile sub-mode button."""
        self.submode = submode
        self._show_mode()

    def _active_view_key(self):
        return self.submode if self.mode == "profile" else self.mode

    def _show_mode(self):
        """Show the view for the active (mode, sub-mode) and refresh its content."""
        key = self._active_view_key()
        self.display.show_view(key)
        # Reverse only applies to result lists (matches/paths); disabled until 5.1/5.2.
        self.display.set_reverse_enabled(False)
        self._refresh_active_view()

    def _refresh_active_view(self):
        """Populate the currently-shown view for the current person."""
        if not self.current_person or not self.model.individuals:
            return
        key = self._active_view_key()
        cp = self.current_person
        if key == "bio":
            self.bio_view.set_center(cp, show_id=self.id_switch.value)
        elif key == "pedigree":
            self.pedigree_view.set_center(cp, mode="pedigree")
        elif key == "descendants":
            self.descendants_view.set_center(cp, mode="descendants")
        elif key == "matches":
            self._trigger_matches()
        elif key == "paths":
            asyncio.create_task(self._enter_paths_mode())

    # ---- family graph popup ---------------------------------------------
    def _open_graph_window(self, graph_type="pedigree"):
        """Open a family graph (tree / pedigree / descendant) centered on the current
        person, in its own window (created fresh each time)."""
        if not self.current_person or not self.model.individuals:
            return
        win = FamilyGraphWindow(
            self.model, self.current_person, self.current_path,
            graph_type=graph_type, on_person_select=self._on_graph_person_select)
        self._graph_window = win
        win.show()

    # ---- DNA matches (background search) --------------------------------
    def _trigger_matches(self):
        """Run (or re-run) the DNA-match search for the current person."""
        if self.current_person and self.model.individuals:
            self.config.set_top_n(self.matches_view.top_n)
            self.config.set_max_depth(self.matches_view.max_depth)
            asyncio.create_task(self._run_matches(self.current_person))

    async def _run_matches(self, start_id):
        # Cancel any in-flight search and stamp a new generation.
        if self._matches_cancel is not None:
            self._matches_cancel.set()
        cancel = threading.Event()
        self._matches_cancel = cancel
        self._matches_gen += 1
        gen = self._matches_gen
        top_n, max_depth = self.matches_view.top_n, self.matches_view.max_depth
        self.matches_view.set_status("Searching for DNA matches…")
        try:
            results = await asyncio.to_thread(
                self.model.find_dna_matches, start_id, top_n, max_depth, cancel)
        except SearchCancelled:
            return
        except Exception as exc:  # noqa: BLE001 — surface search/data failure
            if gen == self._matches_gen:
                self.matches_view.set_status(f"Search failed: {exc}")
            return
        if gen != self._matches_gen:
            return  # superseded by a newer search
        self.matches_view.render(start_id, results)
        self.matches_view.set_status(f"{len(results)} match(es) found.")

    # ---- relationship paths (background search) -------------------------
    async def _enter_paths_mode(self):
        """Ensure a target is chosen, then run the path search for the current person."""
        if not self.current_person or not self.model.individuals:
            return
        target = self._path_target
        if not target or target not in self.model.individuals:
            picker = PersonPicker(
                self.model, name_order=self.name_order,
                max_display=self.max_display, title="Select target person")
            target = await picker.pick()
            if not target:
                self.paths_view.set_status("No target selected.")
                return
            self._path_target = target
        await self._run_paths(self.current_person, target)

    def _change_path_target(self):
        """Clear the current target and prompt for a new one."""
        self._path_target = None
        asyncio.create_task(self._enter_paths_mode())

    def _trigger_paths(self):
        """Re-run the path search when the max-paths / max-depth controls change."""
        if (self.current_person and self._path_target
                and self._path_target in self.model.individuals):
            self.config.set_top_n(self.paths_view.top_n)
            self.config.set_max_depth(self.paths_view.max_depth)
            asyncio.create_task(self._run_paths(self.current_person, self._path_target))

    async def _run_paths(self, start_id, end_id):
        if self._paths_cancel is not None:
            self._paths_cancel.set()
        cancel = threading.Event()
        self._paths_cancel = cancel
        self._paths_gen += 1
        gen = self._paths_gen
        top_n = self.paths_view.top_n
        max_depth = self.paths_view.max_depth
        self.paths_view.set_status("Searching for paths…")
        try:
            paths, truncated = await asyncio.to_thread(
                self.model.find_all_paths, start_id, end_id, top_n, max_depth, cancel)
        except SearchCancelled:
            return
        except Exception as exc:  # noqa: BLE001 — surface search/data failure
            if gen == self._paths_gen:
                self.paths_view.set_status(f"Search failed: {exc}")
            return
        if gen != self._paths_gen:
            return
        self.paths_view.render(start_id, end_id, paths, truncated)
        self.paths_view.set_status(f"{len(paths)} path(s) found.")

    # ---- path graph popup -----------------------------------------------
    def _open_path_graph(self, path):
        """Open the relationship-path graph popup for a clicked relationship."""
        if not path:
            return
        start = path[0][0]
        anc = get_ancestor_depths(start, self.model.individuals, self.model.families)
        desc = get_descendant_depths(start, self.model.individuals, self.model.families)
        rel = describe_relationship(
            path, self.model.individuals, ancestors=anc, descendants=desc,
            families=self.model.families)
        self._path_graph_window = PathGraphWindow(
            self.model, path, rel,
            on_show_person=self._pg_show_person,
            on_find_matches=self._pg_find_matches,
            on_find_path=self._pg_find_path)
        self._path_graph_window.show()

    def _pg_show_person(self, iid):
        self.current_person = iid
        self._select_person(iid)
        self._set_submode("bio")

    def _pg_find_matches(self, iid):
        self.current_person = iid
        self._select_person(iid)
        self._set_mode("matches")

    def _pg_find_path(self, iid):
        # Find a path from the current start person to the clicked node.
        self._path_target = iid
        self._set_mode("paths")

    def _on_graph_person_select(self, person_id):
        """Handle person selection from graph view."""
        self.current_person = person_id
        self._select_person(person_id)

    def _on_results_person_click(self, person_id):
        """Handle person link clicks from results / matches views."""
        self.current_person = person_id
        self._select_person(person_id)
        self._refresh_active_view()

    # ---- results footer (stubs until 5.4) -------------------------------
    def _on_reverse(self):
        pass

    def _on_copy(self):
        pass

    def _on_save(self):
        pass

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

        # Update views that cache the data dicts (bio/matches/paths hold the model live).
        self.pedigree_view.update_data(self.model.individuals, self.model.families)
        self.descendants_view.update_data(self.model.individuals, self.model.families)

        home = self.config.get_home_person(str(path))
        has_home = bool(home and home in self.model.individuals)
        self.cmd_go_home.enabled = has_home
        if has_home:
            self.current_person = home
            self._select_person(home)
            self._refresh_active_view()

        self._dump_columns_if_diag()

    def _dump_columns_if_diag(self):
        """When GEDCOM_DIAG is set, print the realized native column widths + DPI scale
        as one JSON line (`GEDCOM_DIAG_COLUMNS {...}`) so the Windows test harness can
        verify column sizing quantitatively. No-op otherwise."""
        if not os.environ.get("GEDCOM_DIAG"):
            return
        info = nt.describe_columns(self.people)
        if info is not None:
            print("GEDCOM_DIAG_COLUMNS " + json.dumps(info), flush=True)

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
        nt.apply_column_widths(self.people, PEOPLE_COLUMN_WIDTHS)
        total, shown = len(self.model.individuals), len(ids)
        msg = f"Showing {shown} of {total} people"
        if truncated:
            msg += " — narrow your search"
        self.status.text = msg

    def _select_person(self, iid):
        """Scroll to a person in the current list; the active view renders their detail."""
        if iid in self._display_ids:
            try:
                self.people.scroll_to_row(self._display_ids.index(iid))
            except Exception:  # noqa: BLE001 — scrolling is best-effort
                pass
        self.cmd_set_home.enabled = True

    def on_search(self, widget, **kw):
        if self.model.individuals:
            self._refresh_people()

    def on_toggle(self, widget, **kw):
        if self.model.individuals:
            self._refresh_people()
            self._refresh_active_view()   # reflect Show-IDs in the open view

    def on_person_select(self, widget, **kw):
        row = self.people.selection
        iid = getattr(row, "id", None) if row else None
        if iid is None:
            self.cmd_set_home.enabled = False
            return
        self.current_person = iid
        self.cmd_set_home.enabled = True
        self._refresh_active_view()

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
            self.current_person = home
            self.search.value = ""
            self._refresh_people()
            self._select_person(home)
            self._refresh_active_view()

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
