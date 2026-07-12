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
import html
import os
import sys
from urllib.parse import quote, unquote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import toga
from toga.style.pack import COLUMN, Pack

from gedcom_parser import build_model
import gedcom_family_tree as ft

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "fictional_genealogy.ged")
ROOT_URL = "https://spike.local/"
# Person links must use a REAL http(s) scheme: WKWebView ignores unregistered custom
# schemes, and Toga's WebView.url setter rejects any non-http(s) URL (used by the
# on_navigation_starting cleanup). We intercept these and cancel before they load.
PERSON_MARKER = "/person/"
PERSON_BASE = ROOT_URL.rstrip("/") + PERSON_MARKER


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
        href = PERSON_BASE + quote(iid, safe="")
        link = f"<a class='person' href='{html.escape(href)}'>{html.escape(name)}</a>"
        parts.append(f"<div class='row'>{link} <span class='years'>{html.escape(years)}</span></div>")
    return "\n".join(parts)


class RichTextApp(toga.App):
    def startup(self):
        self.data = Data(SAMPLE)
        self.header = toga.Label("", style=Pack(margin=(8, 10), font_weight="bold"))
        self.web = toga.WebView(
            style=Pack(flex=1),
            on_navigation_starting=self.on_nav,
            on_webview_load=self.on_loaded,
        )
        root = toga.Box(style=Pack(direction=COLUMN), children=[self.header, self.web])
        self.main_window = toga.MainWindow(title="Toga Rich-Text Results Spike", size=(760, 820))
        self.main_window.content = root
        self.main_window.show()
        self._render()

        if os.environ.get("GEDCOM_SPIKE_HTML"):
            self.add_background_task(self._dump_and_exit)

    def _render(self):
        name, years = self.data.label(self.data.center)
        self.header.text = f"Center: {name}{years}"
        self.web.set_content(ROOT_URL, render_html(self.data, self.data.center))

    def on_nav(self, widget, url, **kw):
        """on_navigation_starting: return True = allow (Toga then sets self.url),
        False = block. We never want the WebView to leave our injected content:
          - person link  -> recenter in-app, block (False)
          - any non-http(s) scheme -> block (False), else Toga's cleanup would try
            self.url = <bad scheme> and raise ValueError
          - a genuine http(s) page (none in this spike) -> allow (True)"""
        if PERSON_MARKER in url:
            iid = unquote(url.split(PERSON_MARKER, 1)[1])
            if iid in self.data.individuals:
                self.data.center = iid
                self._render()
            return False
        if url.startswith(("http://", "https://")):
            return True
        return False

    def on_loaded(self, widget, **kw):
        """WINDOWS re-arm: toga-winforms leaves its internal `_allowed_url` set to
        "about:blank" after set_content() and never clears it on an allowed nav, so
        on_navigation_starting is bypassed for every later click. Reset it once the
        page has loaded so the next link click reaches our handler. Windows-only and
        guarded — macOS (WKWebView) uses a different path and already works."""
        impl = self.web._impl
        if type(impl).__module__.startswith("toga_winforms") and hasattr(impl, "_allowed_url"):
            impl._allowed_url = None

    async def _dump_and_exit(self, widget, **kw):
        path = os.environ["GEDCOM_SPIKE_HTML"]
        with open(path, "w") as fh:
            fh.write(render_html(self.data, self.data.center))
        print(f"HTML_DUMP_OK {path}")
        self.request_exit()


def main():
    return RichTextApp("Rich-Text Results Spike", "org.beeware.gedcom.richspike")


if __name__ == "__main__":
    main().main_loop()
