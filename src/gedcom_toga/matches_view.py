"""DNA Matches view (Phase 5.1) — WebView rendering of find_dna_matches results.

Mirrors the tkinter `_render_results` (gedcom_gui_results.py): a ranked list of DNA-
flagged matches, each with a clickable name, the relationship to the start person, the
common ancestor(s), the match's DNA markers, and the connecting path. The actual search
(potentially slow) is run off-thread by the app; this view only renders + navigates.

Person links use the same public `window.__nav` + evaluate_javascript poll as
results_view.py (no navigation, no `_impl` reach). Top-N / max-depth controls live in
the view's control row and notify the app to re-run via `on_params_change`.
"""
import asyncio
import html
import json

import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)

ROOT_URL = "https://gedcom.local/"
POLL_INTERVAL = 0.15
# Reads both the person-nav var and the relationship-graph var in one call, returning
# a JSON object string (always non-empty).
POLL_JS = ("(function(){var n=window.__nav||null,r=window.__relgraph||null;"
           "window.__nav=null;window.__relgraph=null;"
           "return JSON.stringify({n:n,r:r});})()")

EDGE_LABEL = {
    "father": "↑ father", "mother": "↑ mother",
    "child": "↓ child", "sibling": "↔ sibling", "spouse": "⚭ spouse",
}

STYLE = """<style>
  body{font:14px -apple-system,Segoe UI,sans-serif;margin:16px;color:#1b1f24;}
  h2{margin:0 0 10px;font-size:18px;}
  .rank{font-weight:600;margin:16px 0 2px;font-size:15px;}
  .detail{margin:1px 0 1px 18px;}
  .path{margin:2px 0 2px 30px;color:#39424c;}
  .markers{margin:2px 0 2px 30px;color:#6a737d;font-size:13px;}
  .note{color:#6a737d;margin:0 0 12px;}
  a.person{color:#0969da;text-decoration:none;cursor:pointer;}
  a.person:hover{text-decoration:underline;}
  .years{color:#6a737d;}
  .label{color:#6a737d;}
</style>"""


class MatchesView:
    def __init__(self, model, *, on_person_click=None, on_params_change=None,
                 on_relationship_click=None, top_n=3, max_depth=10):
        self.model = model
        self.on_person_click = on_person_click
        self.on_params_change = on_params_change
        self.on_relationship_click = on_relationship_click
        self.start_id = None
        self._paths = []   # path per rendered match, for relationship-graph clicks

        self.top_n_input = toga.NumberInput(
            min=1, max=100, step=1, value=top_n,
            on_change=self._params_changed, style=Pack(width=70))
        self.max_depth_input = toga.NumberInput(
            min=1, max=100, step=1, value=max_depth,
            on_change=self._params_changed, style=Pack(width=70))
        self.status = toga.Label("", style=Pack(margin=(4, 8), flex=1))
        controls = toga.Box(style=Pack(direction=ROW, margin=(6, 8, 2, 8)), children=[
            toga.Label("Top matches:", style=Pack(margin=(4, 4))), self.top_n_input,
            toga.Label("Max depth:", style=Pack(margin=(4, 4))), self.max_depth_input,
            self.status,
        ])
        self.web = toga.WebView(style=Pack(flex=1))
        self.container = toga.Box(
            style=Pack(direction=COLUMN, flex=1), children=[controls, self.web])
        self._poll_task = None
        self.set_content("<p class='note'>Select a person to find DNA matches.</p>")

    # ---- params ----------------------------------------------------------
    @property
    def top_n(self):
        return int(self.top_n_input.value or 3)

    @property
    def max_depth(self):
        return int(self.max_depth_input.value or 10)

    def _params_changed(self, widget, **kw):
        if self.on_params_change:
            self.on_params_change()

    def set_status(self, text):
        self.status.text = text

    def set_content(self, body_html):
        self.web.set_content(ROOT_URL, "<!doctype html><meta charset='utf-8'>"
                             + STYLE + body_html)

    # ---- rendering -------------------------------------------------------
    def _label(self, iid):
        ind = self.model.individuals.get(iid, {})
        name = ind.get("name") or iid
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f" ({by or '?'}–{dy or ''})" if (by or dy) else ""
        return name, years

    def _person_link(self, iid):
        name, years = self._label(iid)
        onclick = html.escape(f"window.__nav={json.dumps(iid)};return false;", quote=True)
        return (f"<a class='person' href='#' onclick=\"{onclick}\">{html.escape(name)}</a>"
                f"<span class='years'>{html.escape(years)}</span>")

    def render(self, start_id, results):
        """Render ranked DNA-match results (list of (distance, path))."""
        self.start_id = start_id
        indi = self.model.individuals
        fams = self.model.families
        if start_id not in indi:
            self.set_content("<p class='note'>No person selected.</p>")
            return
        self._paths = [path for (_dist, path) in results]
        sname, syears = self._label(start_id)
        parts = [f"<h2>DNA matches for {html.escape(sname)}"
                 f"<span class='years'>{html.escape(syears)}</span></h2>"]

        start_markers = indi[start_id].get("dna_markers") or []
        if start_markers:
            parts.append("<p class='note'>This person is DNA-flagged:</p>")
            for m in start_markers:
                parts.append(f"<div class='markers'>• {html.escape(str(m))}</div>")

        if not results:
            parts.append(f"<p class='note'>No DNA matches found within "
                         f"{self.max_depth} steps.</p>")
            self.set_content("\n".join(parts))
            return

        # Precompute the start person's ancestor/descendant depths once (feeds
        # describe_relationship's step-vs-blood disambiguation).
        ancestors = get_ancestor_depths(start_id, indi, fams)
        descendants = get_descendant_depths(start_id, indi, fams)

        for rank, (_distance, path) in enumerate(results, 1):
            match_id = path[-1][0]
            rel = describe_relationship(
                path, indi, ancestors=ancestors, descendants=descendants, families=fams)
            parts.append(f"<div class='rank'>{rank}. {self._person_link(match_id)}</div>")
            rel_click = html.escape(
                f"window.__relgraph={json.dumps(str(rank - 1))};return false;", quote=True)
            parts.append(f"<div class='detail'><span class='label'>Relationship:</span> "
                         f"<a class='person' href='#' onclick=\"{rel_click}\">"
                         f"{html.escape(rel)}</a> <span class='label'>(graph)</span></div>")

            common = self.model.find_common_ancestors(start_id, match_id)
            if common:
                links = ", ".join(self._person_link(cid) for cid in common)
                parts.append(f"<div class='detail'><span class='label'>Common "
                             f"ancestor{'s' if len(common) > 1 else ''}:</span> {links}</div>")

            parts.append("<div class='detail'><span class='label'>Path:</span></div>")
            for i, (node_id, edge) in enumerate(path):
                prefix = "" if i == 0 else (EDGE_LABEL.get(edge, edge or "") + ": ")
                parts.append(f"<div class='path'>{html.escape(prefix)}"
                             f"{self._person_link(node_id)}</div>")

            match_markers = indi.get(match_id, {}).get("dna_markers") or []
            for m in match_markers:
                parts.append(f"<div class='markers'>• {html.escape(str(m))}</div>")

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
                raw = await self.web.evaluate_javascript(POLL_JS)
                data = json.loads(raw) if raw else {}
            except Exception:  # noqa: BLE001 — webview not ready / eval hiccup
                continue
            nav, rel = data.get("n"), data.get("r")
            if nav and nav in self.model.individuals and self.on_person_click:
                self.on_person_click(nav)
            if rel is not None and self.on_relationship_click:
                try:
                    idx = int(rel)
                except (TypeError, ValueError):
                    idx = -1
                if 0 <= idx < len(self._paths):
                    self.on_relationship_click(self._paths[idx])
