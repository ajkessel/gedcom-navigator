"""Results view — WebView-based rich text display with clickable person links.

Adapted from spike/toga_richtext_spike.py for Phase 4 integration.
Renders ancestor/descendant reports as styled HTML with navigation.
"""
import asyncio
import html
import json

import toga
from toga.style.pack import COLUMN, Pack

from gedcom_family_tree import build_pedigree_tree_graph, layout_pedigree_tree

ROOT_URL = "https://gedcom.local/"
POLL_INTERVAL = 0.15
POLL_JS = "(function(){var v=window.__nav||null;window.__nav=null;return v;})()"


class ResultsView:
    """Reusable results view with WebView rendering and link navigation."""

    def __init__(self, individuals, families, on_person_click=None):
        self.individuals = individuals
        self.families = families
        self.center = None
        self.on_person_click = on_person_click
        self.mode = "pedigree"  # "pedigree" or "descendants"

        self.header = toga.Label("", style=Pack(margin=(8, 10), font_weight="bold"))
        self.web = toga.WebView(style=Pack(flex=1))
        self.container = toga.Box(
            style=Pack(direction=COLUMN, flex=1), children=[self.header, self.web]
        )
        self._poll_task = None

    def set_center(self, center_id, mode="pedigree"):
        """Set the center person and render the report."""
        if center_id not in self.individuals:
            return
        self.center = center_id
        self.mode = mode
        self._render()

    def update_data(self, individuals, families):
        """Update the underlying data model (after reload)."""
        self.individuals = individuals
        self.families = families
        if self.center and self.center in self.individuals:
            self._render()

    def start_polling(self):
        """Start polling for link clicks (call once after view is shown)."""
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll_clicks())

    def stop_polling(self):
        """Stop polling for link clicks."""
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    def _render(self):
        if not self.center or self.center not in self.individuals:
            self.header.text = ""
            self.web.set_content(ROOT_URL, "<p>No person selected.</p>")
            return
        name, years = self._label(self.center)
        self.header.text = f"Center: {name}{years}"
        if self.mode == "pedigree":
            html_content = self._render_pedigree_html()
        else:
            html_content = self._render_descendants_html()
        self.web.set_content(ROOT_URL, html_content)

    def _label(self, iid):
        ind = self.individuals.get(iid, {})
        name = ind.get("name") or iid
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f" ({by or '?'}–{dy or ''})" if (by or dy) else ""
        return name, years

    def _render_pedigree_html(self):
        """Build styled HTML for an Ahnentafel ancestor report."""
        cname, cyears = self._label(self.center)
        rows = self._ancestors(self.center)
        gen_labels = {0: "Self", 1: "Parents", 2: "Grandparents", 3: "Great-grandparents"}
        parts = [
            "<!doctype html><meta charset='utf-8'>",
            """<style>
              body{font:14px -apple-system,Segoe UI,sans-serif;margin:16px;color:#1b1f24;}
              h2{margin:0 0 4px;font-size:18px;}
              .sub{color:#6a737d;margin:0 0 14px;}
              .gen{font-weight:600;margin:14px 0 4px;color:#24292e;}
              .row{margin:2px 0 2px 20px;}
              a.person{color:#0969da;text-decoration:none;cursor:pointer;}
              a.person:hover{text-decoration:underline;}
              .years{color:#6a737d;}
            </style>""",
            f"<h2>Ancestors of {html.escape(cname)}<span class='years'>{html.escape(cyears)}</span></h2>",
            "<p class='sub'>Click any name to recenter.</p>",
        ]
        last_depth = None
        for depth, _gen, iid in rows:
            if depth != last_depth:
                label = gen_labels.get(depth, f"Generation +{depth}")
                parts.append(f"<div class='gen'>{html.escape(label)}</div>")
                last_depth = depth
            name, years = self._label(iid)
            onclick = html.escape(f"window.__nav={json.dumps(iid)};return false;", quote=True)
            link = f"<a class='person' href='#' onclick=\"{onclick}\">{html.escape(name)}</a>"
            parts.append(f"<div class='row'>{link} <span class='years'>{html.escape(years)}</span></div>")
        return "\n".join(parts)

    def _render_descendants_html(self):
        """Build styled HTML for a Henry-numbered descendant report."""
        cname, cyears = self._label(self.center)
        parts = [
            "<!doctype html><meta charset='utf-8'>",
            """<style>
              body{font:14px -apple-system,Segoe UI,sans-serif;margin:16px;color:#1b1f24;}
              h2{margin:0 0 4px;font-size:18px;}
              .sub{color:#6a737d;margin:0 0 14px;}
              .row{margin:2px 0;}
              a.person{color:#0969da;text-decoration:none;cursor:pointer;}
              a.person:hover{text-decoration:underline;}
              .years{color:#6a737d;}
              .spouse{color:#6a737d;font-style:italic;}
            </style>""",
            f"<h2>Descendants of {html.escape(cname)}<span class='years'>{html.escape(cyears)}</span></h2>",
            "<p class='sub'>Click any name to recenter.</p>",
        ]
        visited = set()

        def walk(iid, henry, depth):
            if iid in visited:
                return
            visited.add(iid)
            indent = '&nbsp;' * (depth - 1) * 3
            name, years = self._label(iid)
            onclick = html.escape(f"window.__nav={json.dumps(iid)};return false;", quote=True)
            link = f"<a class='person' href='#' onclick=\"{onclick}\">{html.escape(name)}</a>"
            parts.append(
                f"<div class='row'>{indent}{henry}. {link} "
                f"<span class='years'>{html.escape(years)}</span></div>"
            )
            indi = self.individuals.get(iid, {})
            spouses_written = set()
            child_counter = [0]
            for fam_id in indi.get("fams", ()):
                fam = self.families.get(fam_id)
                if not fam:
                    continue
                spouse_id = fam.get("wife") if fam.get("husb") == iid else fam.get("husb")
                if spouse_id and spouse_id in self.individuals and spouse_id not in spouses_written:
                    sname, syears = self._label(spouse_id)
                    sonclick = html.escape(f"window.__nav={json.dumps(spouse_id)};return false;", quote=True)
                    slink = f"<a class='person' href='#' onclick=\"{sonclick}\">{html.escape(sname)}</a>"
                    parts.append(
                        f"<div class='row spouse'>{indent}&nbsp;&nbsp;&nbsp;m. {slink} "
                        f"<span class='years'>{html.escape(syears)}</span></div>"
                    )
                    spouses_written.add(spouse_id)
                for child_id in fam.get("chil", ()):
                    if child_id in self.individuals:
                        child_counter[0] += 1
                        child_henry = f"{henry}.{child_counter[0]}"
                        walk(child_id, child_henry, depth + 1)

        walk(self.center, "1", 1)
        return "\n".join(parts)

    def _ancestors(self, center):
        """Return ordered (depth, generation, id) ancestor rows for pedigree."""
        visible, edges = build_pedigree_tree_graph(center, self.individuals, self.families)
        nodes = layout_pedigree_tree(center, visible, edges)
        rows = [(int(n["column"]), n["generation"], n["id"]) for n in nodes]
        rows.sort(key=lambda r: (r[0], r[1]))
        return rows

    async def _poll_clicks(self):
        """Poll for link clicks via evaluate_javascript."""
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                iid = await self.web.evaluate_javascript(POLL_JS)
            except Exception:  # noqa: BLE001
                continue
            if iid and iid in self.individuals and iid != self.center:
                self.center = iid
                self._render()
                if self.on_person_click:
                    self.on_person_click(iid)
