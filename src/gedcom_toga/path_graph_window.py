"""Relationship path graph — popup window (Phase 5.3).

Opens in its own toga.Window (like the tkinter Toplevel) and renders a relationship
path between two people as a canvas graph: a spine of the path nodes plus, on demand,
expanded off-path relatives. Reuses the pure layout from GraphLayoutMixin
(gedcom_gui_graph_layout — verified import-clean), the family/coparent lookups from
graph_geometry, and a Toga canvas draw idiom (state/scale + fill/stroke/round_rect).

Interaction (Toga has no canvas context menu, so the tkinter right-click menu becomes an
action bar): click a node to select it → the action bar's Show person / Find matches /
Find path buttons act on it. Each node draws a "＋"/"－" toggle that expands/collapses
its immediate relatives via _expanded_path_graph_layout.
"""
import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_gui_graph_layout import GraphLayoutMixin

from . import graph_geometry as gg

COL_GAP = 210.0
ROW_GAP = 120.0
NODE_W = 184.0
NODE_H = 48.0
MARGIN = 60.0
EXPAND_R = 9.0
EXPAND_CATEGORIES = ("parents", "siblings", "spouses", "children")


class PathGraphWindow:
    def __init__(self, model, path, relationship, *, on_show_person=None,
                 on_find_matches=None, on_find_path=None):
        self.model = model
        self.on_show_person = on_show_person
        self.on_find_matches = on_find_matches
        self.on_find_path = on_find_path
        self.relationship = relationship or ""
        self.raw_path = list(path)
        self.zoom = 1.0
        self.selected = None
        self.expanded_nodes = set()
        self._press_at = (0, 0)
        self._expand_hits = {}   # id -> (cx, cy, r) in world coords

        self._family_lookup = lambda iid: gg.family_members(
            iid, self.model.individuals, self.model.families)
        self._coparent_lookup = lambda iid, exclude: gg.coparents(
            iid, exclude, self.model.individuals, self.model.families)

        self._rebuild_layout()

        self.canvas = toga.Canvas(on_press=self._on_press, on_release=self._on_release)
        self.scroller = toga.ScrollContainer(
            horizontal=True, vertical=True, content=self.canvas, style=Pack(flex=1))
        self.info = toga.Label(self._info_text(), style=Pack(margin=(6, 8), flex=1))
        self.btn_person = toga.Button(
            "Show person", on_press=lambda w: self._act(self.on_show_person),
            enabled=False, style=Pack(margin=(0, 3)))
        self.btn_matches = toga.Button(
            "Find matches", on_press=lambda w: self._act(self.on_find_matches),
            enabled=False, style=Pack(margin=(0, 3)))
        self.btn_path = toga.Button(
            "Find path", on_press=lambda w: self._act(self.on_find_path),
            enabled=False, style=Pack(margin=(0, 3)))
        controls = toga.Box(style=Pack(direction=ROW, margin=4), children=[
            toga.Button("Zoom −", on_press=lambda w: self._bump_zoom(1 / 1.25)),
            toga.Button("Zoom +", on_press=lambda w: self._bump_zoom(1.25)),
            toga.Button("Reset", on_press=lambda w: self._reset_view()),
            self.info, self.btn_person, self.btn_matches, self.btn_path,
        ])
        root = toga.Box(style=Pack(direction=COLUMN, flex=1),
                        children=[controls, self.scroller])
        title = f"Relationship path — {self.relationship}" if self.relationship \
            else "Relationship path"
        self.window = toga.Window(title=title, size=(940, 700))
        self.window.content = root

    def show(self):
        self.window.show()
        self.redraw()

    # ---- layout ----------------------------------------------------------
    def _rebuild_layout(self):
        simplified = GraphLayoutMixin._simplify_path_for_graph(self.raw_path)
        base = GraphLayoutMixin._path_graph_layout(simplified)
        if self.expanded_nodes:
            requests = [(nid, cat) for nid in self.expanded_nodes
                        for cat in EXPAND_CATEGORIES]
            layout, extra = GraphLayoutMixin._expanded_path_graph_layout(
                base, requests, self._family_lookup, self._coparent_lookup)
        else:
            layout, extra = base, []
        self.layout = layout
        self.extra_edges = extra
        min_gen = min((n["generation"] for n in layout), default=0)
        min_col = min((n["column"] for n in layout), default=0)
        self.boxes = {}
        for n in layout:
            x = MARGIN + (n["column"] - min_col) * COL_GAP
            y = MARGIN + (n["generation"] - min_gen) * ROW_GAP
            self.boxes[n["id"]] = (x, y, NODE_W, NODE_H)
        path_nodes = sorted((n for n in layout if n.get("is_path_node")),
                            key=lambda n: n["index"])
        self.spine = [(path_nodes[i - 1]["id"], path_nodes[i]["id"], path_nodes[i]["edge"])
                      for i in range(1, len(path_nodes))]
        self._endpoints = {n["id"] for n in layout if n.get("is_endpoint")}
        self._path_ids = {n["id"] for n in layout if n.get("is_path_node")}

    def content_size(self):
        if not self.boxes:
            return 400, 400
        max_x = max(x + w for (x, y, w, h) in self.boxes.values())
        max_y = max(y + h for (x, y, w, h) in self.boxes.values())
        return max_x + MARGIN, max_y + MARGIN

    def _label(self, iid):
        ind = self.model.individuals.get(iid, {})
        name = ind.get("name") or iid
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f"({by or '?'}–{dy or ''})" if (by or dy) else ""
        return name, years

    # ---- rendering -------------------------------------------------------
    def redraw(self):
        c = self.canvas
        cw, ch = self.content_size()
        c.style.width = int(cw * self.zoom)
        c.style.height = int(ch * self.zoom)
        c.root_state.drawing_actions.clear()
        with c.state():
            c.scale(self.zoom, self.zoom)
            self._draw_edges()
            self._draw_nodes()
        c.redraw()

    def _draw_edges(self):
        c = self.canvas
        for src, dst, *_ in self.spine + list(self.extra_edges):
            sb, db = self.boxes.get(src), self.boxes.get(dst)
            if not sb or not db:
                continue
            sx, sy = sb[0] + sb[2] / 2, sb[1] + sb[3] / 2
            dx, dy = db[0] + db[2] / 2, db[1] + db[3] / 2
            with c.stroke(color="#8a8f98", line_width=1.8):
                c.move_to(sx, sy)
                midy = (sy + dy) / 2
                c.line_to(sx, midy)
                c.line_to(dx, midy)
                c.line_to(dx, dy)

    def _draw_nodes(self):
        c = self.canvas
        self._expand_hits = {}
        for iid, (x, y, w, h) in self.boxes.items():
            is_end = iid in self._endpoints
            is_path = iid in self._path_ids
            is_sel = iid == self.selected
            if is_end:
                fill = "#1f6feb"
            elif is_path:
                fill = "#22272e"
            else:
                fill = "#2b2029"  # expanded relative (muted)
            if is_sel:
                fill = "#2d333b"
            with c.fill(color=fill):
                c.round_rect(x, y, w, h, 8)
            with c.stroke(color="#4fa3ff" if is_sel else "#444c56", line_width=1.8):
                c.round_rect(x, y, w, h, 8)
            name, years = self._label(iid)
            with c.fill(color="#ffffff"):
                c.fill_text(name[:24], x + 10, y + 20, font=toga.Font("sans-serif", 12))
            if years:
                with c.fill(color="#9aa4af"):
                    c.fill_text(years, x + 10, y + 38, font=toga.Font("sans-serif", 10))
            # expand/collapse toggle (top-right corner)
            cx, cy = x + w - 4, y + 4
            self._expand_hits[iid] = (cx, cy, EXPAND_R)
            with c.fill(color="#30363d"):
                c.arc(cx, cy, EXPAND_R, 0, 6.2832)
            with c.stroke(color="#8a8f98", line_width=1.2):
                c.arc(cx, cy, EXPAND_R, 0, 6.2832)
            sign = "−" if iid in self.expanded_nodes else "+"
            with c.fill(color="#e6edf3"):
                c.fill_text(sign, cx - 3, cy + 4, font=toga.Font("sans-serif", 12))

    # ---- interaction -----------------------------------------------------
    def _on_press(self, widget, x, y, **kw):
        self._press_at = (x, y)

    def _on_release(self, widget, x, y, **kw):
        if abs(x - self._press_at[0]) + abs(y - self._press_at[1]) >= 4:
            return  # drag-scroll, not a click
        wx, wy = x / self.zoom, y / self.zoom
        # expand toggles take priority over node-body selection
        for iid, (cx, cy, r) in self._expand_hits.items():
            if (wx - cx) ** 2 + (wy - cy) ** 2 <= (r + 2) ** 2:
                self._toggle_expand(iid)
                return
        for iid, (bx, by, bw, bh) in self.boxes.items():
            if bx <= wx <= bx + bw and by <= wy <= by + bh:
                self._select(iid)
                return

    def _toggle_expand(self, iid):
        if iid in self.expanded_nodes:
            self.expanded_nodes.discard(iid)
        else:
            self.expanded_nodes.add(iid)
        keep = self.selected
        self._rebuild_layout()
        self.selected = keep if keep in self.boxes else None
        self._sync_actions()
        self.redraw()

    def _select(self, iid):
        self.selected = iid
        self.info.text = self._info_text()
        self._sync_actions()
        self.redraw()

    def _sync_actions(self):
        has = self.selected is not None and self.selected in self.model.individuals
        self.btn_person.enabled = has
        self.btn_matches.enabled = has
        self.btn_path.enabled = has

    def _act(self, callback):
        if callback and self.selected:
            callback(self.selected)

    def _bump_zoom(self, factor):
        self.zoom = max(0.3, min(3.0, self.zoom * factor))
        self.info.text = self._info_text()
        self.redraw()

    def _reset_view(self):
        self.zoom = 1.0
        self.info.text = self._info_text()
        self.redraw()

    def _info_text(self):
        if self.selected and self.selected in self.model.individuals:
            name, years = self._label(self.selected)
            return f"Selected: {name} {years}"
        return f"{self.relationship}   nodes: {len(self.boxes)}   zoom: {self.zoom:.2f}"
