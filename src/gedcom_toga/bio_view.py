"""Bio view (Phase 5 refinement) — WebView profile for the selected person.

Replaces the plain MultilineTextInput Bio pane so it shares the same font/styling as the
Matches/Paths/Pedigree panes and, like them, renders family members as clickable links.
Shows the person header (name + lifespan [+ id]), a DNA-match marker, and immediate
family grouped by relation (Parents / Siblings / Spouses / Children).
"""
import asyncio
import html
import json

import toga
from toga.style.pack import COLUMN, Pack

from . import graph_geometry as gg
from . import person_detail as pd

ROOT_URL = "https://gedcom.local/"
POLL_INTERVAL = 0.15
POLL_JS = "(function(){var v=window.__nav||null;window.__nav=null;return v;})()"

STYLE = """<style>
  body{font:14px -apple-system,Segoe UI,sans-serif;margin:16px;color:#1b1f24;}
  h2{margin:0 0 2px;font-size:18px;}
  .star{color:#b35900;margin:2px 0 12px;font-weight:600;}
  .sub{color:#6a737d;margin:0 0 12px;}
  .group{font-weight:600;margin:14px 0 4px;color:#24292e;}
  .row{margin:2px 0 2px 18px;}
  a.person{color:#0969da;text-decoration:none;cursor:pointer;}
  a.person:hover{text-decoration:underline;}
  .years{color:#6a737d;}
  .id{color:#8a8f98;}
</style>"""


class BioView:
    def __init__(self, model, *, on_person_click=None):
        self.model = model
        self.on_person_click = on_person_click
        self.center = None
        self.show_id = False

        self.web = toga.WebView(style=Pack(flex=1))
        self.container = toga.Box(style=Pack(direction=COLUMN, flex=1), children=[self.web])
        self._poll_task = None
        self.set_content("<p class='sub'>Select a person.</p>")

    def set_center(self, iid, *, show_id=False):
        self.center = iid
        self.show_id = show_id
        self._render()

    def set_content(self, body_html):
        self.web.set_content(ROOT_URL, "<!doctype html><meta charset='utf-8'>"
                             + STYLE + body_html)

    def _label(self, iid):
        ind = self.model.individuals.get(iid, {})
        name = ind.get("name") or iid
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f" ({by or '?'}–{dy or ''})" if (by or dy) else ""
        return name, years

    def _person_link(self, iid):
        name, years = self._label(iid)
        idtag = f" <span class='id'>[{html.escape(iid.strip('@'))}]</span>" if self.show_id else ""
        onclick = html.escape(f"window.__nav={json.dumps(iid)};return false;", quote=True)
        return (f"<a class='person' href='#' onclick=\"{onclick}\">{html.escape(name)}</a>"
                f"<span class='years'>{html.escape(years)}</span>{idtag}")

    def _render(self):
        indi = self.model.individuals.get(self.center)
        if not indi:
            self.set_content("<p class='sub'>Select a person.</p>")
            return
        name, years = self._label(self.center)
        idtag = f" <span class='id'>[{html.escape(self.center.strip('@'))}]</span>" \
            if self.show_id else ""
        parts = [f"<h2>{html.escape(name)}<span class='years'>{html.escape(years)}"
                 f"</span>{idtag}</h2>"]
        if pd.is_dna_flagged(indi):
            parts.append("<div class='star'>★ DNA match</div>")
        fam = gg.family_members(self.center, self.model.individuals, self.model.families)
        for title, key in (("Parents", "parents"), ("Siblings", "siblings"),
                           ("Spouses", "spouses"), ("Children", "children")):
            ids = fam.get(key) or []
            if not ids:
                continue
            parts.append(f"<div class='group'>{title}</div>")
            for iid in ids:
                parts.append(f"<div class='row'>• {self._person_link(iid)}</div>")
        self.set_content("\n".join(parts))

    # ---- link poll -------------------------------------------------------
    def start_polling(self):
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll_clicks())

    def stop_polling(self):
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    async def _poll_clicks(self):
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                iid = await self.web.evaluate_javascript(POLL_JS)
            except Exception:  # noqa: BLE001 — webview not ready / eval hiccup
                continue
            if iid and iid in self.model.individuals and self.on_person_click:
                self.on_person_click(iid)
