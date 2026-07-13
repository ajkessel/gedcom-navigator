"""GEDCOM Navigator — Toga application shell (migration Phase 3).

Core UI: File→Open a GEDCOM, an async (non-blocking) load into `GedcomDataModel`, a
searchable/filterable person list, and a detail pane. Results graphs + rich results
view arrive in later phases (see spike/ for the proven approaches).

Run (needs a Toga backend installed):  PYTHONPATH=src python -m gedcom_toga
"""
import asyncio
from pathlib import Path

import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_data_model import GedcomDataModel
from gedcom_display import describe, lifespan

from . import person_list as pl

# DNA-flag detection defaults (mirrors CLI defaults); wire to ConfigManager later.
DEFAULT_DNA_KEYWORD = "DNA"
DEFAULT_PAGE_MARKER = "AncestryDNA Match"


class GedcomNavigatorToga(toga.App):
    def startup(self):
        self.model = GedcomDataModel()
        self.sorted_ids = []
        self._show_id = False

        self.search = toga.TextInput(
            placeholder="Search people (name or ID)…",
            on_change=self.on_search,
            style=Pack(flex=1),
        )
        self.people = toga.Table(
            headings=["Name", "Born", "Died"],
            accessors=["name", "born", "died"],
            on_select=self.on_person_select,
            style=Pack(flex=1),
        )
        self.detail = toga.MultilineTextInput(readonly=True, style=Pack(flex=1))
        self.status = toga.Label("Open a GEDCOM file to begin.", style=Pack(margin=6))

        left = toga.Box(
            style=Pack(direction=COLUMN, flex=1),
            children=[
                toga.Box(style=Pack(direction=ROW, margin=6), children=[self.search]),
                self.people,
            ],
        )
        split = toga.SplitContainer(content=[left, self.detail], style=Pack(flex=1))
        root = toga.Box(style=Pack(direction=COLUMN), children=[split, self.status])

        self.main_window = toga.MainWindow(title="GEDCOM Navigator (Toga)", size=(1100, 760))
        self.main_window.content = root

        self.commands.add(
            toga.Command(
                self.on_open, "Open GEDCOM…",
                shortcut=toga.Key.MOD_1 + "o", group=toga.Group.FILE,
            ),
        )
        self.main_window.show()

    # ---- file loading ---------------------------------------------------
    async def on_open(self, widget, **kw):
        path = await self.main_window.dialog(
            toga.OpenFileDialog("Open GEDCOM", file_types=["ged", "GED", "zip"]))
        if not path:
            return
        await self._load(Path(path))

    async def _load(self, path):
        self.status.text = f"Loading {path.name}…"
        cache = self.paths.cache
        cache.mkdir(parents=True, exist_ok=True)
        try:
            from_cache, warning, error = await asyncio.to_thread(
                self.model.load, str(path),
                DEFAULT_DNA_KEYWORD, DEFAULT_PAGE_MARKER, str(cache),
            )
        except Exception as exc:  # noqa: BLE001 — surface any parse/IO failure
            self.status.text = f"Load failed: {exc}"
            return
        if error:
            self.status.text = f"Could not parse {path.name}: {error}"
            return
        self.sorted_ids = pl.sorted_person_ids(self.model.individuals)
        self.search.value = ""
        self._refresh_people()
        note = " (from cache)" if from_cache else ""
        warn = f"   ⚠ {warning}" if warning else ""
        self.status.text = f"Loaded {len(self.model.individuals)} people{note}.{warn}"

    # ---- person list ----------------------------------------------------
    def _refresh_people(self):
        ids, truncated = pl.visible_ids(
            self.model.individuals, self.search.value, self.sorted_ids)
        self.people.data = [
            pl.person_row(self.model.individuals, iid, show_id=self._show_id)
            for iid in ids
        ]
        if truncated:
            self.status.text = (
                f"Showing first {len(self.people.data)} matches — narrow your search.")

    def on_search(self, widget, **kw):
        if self.model.individuals:
            self._refresh_people()

    def on_person_select(self, widget, **kw):
        row = self.people.selection
        if not row:
            self.detail.value = ""
            return
        iid = getattr(row, "id", None)
        indi = self.model.individuals.get(iid, {})
        span = lifespan(indi)
        lines = [describe(indi, show_id=True)]
        if span:
            lines.append(span)
        self.detail.value = "\n".join(lines)


def main():
    return GedcomNavigatorToga("GEDCOM Navigator", "com.ajkessel.gedcom-navigator")


if __name__ == "__main__":
    main().main_loop()
