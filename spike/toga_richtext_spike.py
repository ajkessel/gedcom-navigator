"""
Throwaway Toga spike — deliverable (b): rich results view with clickable person links.

The current results pane is inline rich text (bold headers, indentation, and clickable
person-name links flowing in paragraphs) via tk.Text tag_bind — which has no native Toga
analog. This proves the WebView approach:
  - render results as styled HTML with `<a href="person:ID">Name</a>` links
  - intercept clicks via WebView.on_navigation_starting, CANCEL the navigation, and
    re-render centered on the clicked person (the navigate loop)
This one widget also covers the markdown help/about dialogs (markdown -> HTML -> WebView).

Run headed:  spike-venv/bin/python spike/toga_richtext_spike.py
Emit HTML:   GEDCOM_SPIKE_HTML=out.html spike-venv/bin/python spike/toga_richtext_spike.py
"""
import asyncio
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import toga
from toga.style.pack import COLUMN, Pack

from gedcom_parser import build_model
import gedcom_family_tree as ft

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "fictional_genealogy.ged")
ROOT_URL = "https://spike.local/"
# Link handling uses NO navigation and NO _impl reach: a clicked link sets a JS var
# (window.__nav) and cancels its own navigation (return false); a poll reads the var via
# the public evaluate_javascript() API. Identical on WKWebView + WebView2, sidestepping
# the on_navigation_starting quirks (WKWebView custom-scheme rejection; toga-winforms
# leaving _allowed_url pinned to "about:blank"). This is the portable, public-API path.
POLL_INTERVAL = 0.15
POLL_JS = "(function(){var v=window.__nav||null;window.__nav=null;return v;})()"


class Data:
    def __init__(self, path):
        res = build_model(path, "DNA", "AncestryDNA Match")
        self.individuals, self.families = res[0], res[1]
        self.center = self._widest()

    def _widest(self):
        best = (None, -1)
        for iid in self.individuals:
            v, _ = ft.build_pedigree_tree_graph(iid, self.individuals, self.families)
            if len(v) > best[1]:
                best = (iid, len(v))
        return best[0]

    def label(self, iid):
        ind = self.individuals.get(iid, {})
        name = ind.get("name") or iid
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f" ({by or '?'}–{dy or ''})" if (by or dy) else ""
        return name, years

    def ancestors(self, center):
        """Ordered (depth, id) ancestor rows for a pedigree-style list."""
        visible, edges = ft.build_pedigree_tree_graph(center, self.individuals, self.families)
        nodes = ft.layout_pedigree_tree(center, visible, edges)
        rows = [(int(n["column"]), n["generation"], n["id"]) for n in nodes]
        rows.sort(key=lambda r: (r[0], r[1]))
        return rows


def render_html(data, center):
    """Build the styled results HTML — the faithful stand-in for the tk.Text view."""
    cname, cyears = data.label(center)
    rows = data.ancestors(center)
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
        "<p class='sub'>Click any name to recenter (intercepted via on_navigation_starting).</p>",
    ]
    last_depth = None
    for depth, _gen, iid in rows:
        if depth != last_depth:
            parts.append(f"<div class='gen'>{html.escape(gen_labels.get(depth, f'Generation +{depth}'))}</div>")
            last_depth = depth
        name, years = data.label(iid)
        # onclick sets a JS var and returns false so the page never navigates.
        onclick = html.escape(f"window.__nav={json.dumps(iid)};return false;", quote=True)
        link = f"<a class='person' href='#' onclick=\"{onclick}\">{html.escape(name)}</a>"
        parts.append(f"<div class='row'>{link} <span class='years'>{html.escape(years)}</span></div>")
    return "\n".join(parts)


class RichTextApp(toga.App):
    def startup(self):
        self.data = Data(SAMPLE)
        self.header = toga.Label("", style=Pack(margin=(8, 10), font_weight="bold"))
        self.web = toga.WebView(style=Pack(flex=1))
        root = toga.Box(style=Pack(direction=COLUMN), children=[self.header, self.web])
        self.main_window = toga.MainWindow(title="Toga Rich-Text Results Spike", size=(760, 820))
        self.main_window.content = root
        self.main_window.show()
        self._render()
        asyncio.create_task(self._poll_clicks())

        if os.environ.get("GEDCOM_SPIKE_HTML"):
            asyncio.create_task(self._dump_and_exit())

    def _render(self):
        name, years = self.data.label(self.data.center)
        self.header.text = f"Center: {name}{years}"
        self.web.set_content(ROOT_URL, render_html(self.data, self.data.center))

    async def _poll_clicks(self):
        """Public-API link handling: poll window.__nav (set by a link's onclick) via
        evaluate_javascript. No navigation, no _impl reach — identical on WKWebView +
        WebView2."""
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                iid = await self.web.evaluate_javascript(POLL_JS)
            except Exception:  # noqa: BLE001 — webview not ready / eval hiccup
                continue
            if iid and iid in self.data.individuals and iid != self.data.center:
                self.data.center = iid
                self._render()

    async def _dump_and_exit(self):
        path = os.environ["GEDCOM_SPIKE_HTML"]
        with open(path, "w") as fh:
            fh.write(render_html(self.data, self.data.center))
        print(f"HTML_DUMP_OK {path}")
        self.request_exit()


def main():
    return RichTextApp("Rich-Text Results Spike", "org.beeware.gedcom.richspike")


if __name__ == "__main__":
    main().main_loop()
