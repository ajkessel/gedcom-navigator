"""Family graph popup (Phase 5.5) — tree / pedigree / descendant views.

One window renders any of the three tkinter graph types, switchable via a selector:
  - pedigree   : all recorded ancestors (build_pedigree_tree_graph + layout_pedigree_tree)
  - descendant : expandable descendants (build_descendant_tree_graph + layout_descendant_tree)
  - tree       : expandable immediate-family tree (build_family_tree_graph +
                 layout_family_tree_units)

Nodes are color-coded by gender (matching the tkinter palette: M #d9ecff, F #ffe1ec,
else #f2f2f2, dark text) and show a profile image where one resolves on disk (toga.Image
+ Canvas.draw_image). Click a node to recenter; "+"/"−" toggles expand descendants/tree
relatives. Layout coordinates (generation/column) map to pixels with the same
column*gap / generation*gap scheme used across the canvas views.
"""
import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_family_tree import (
    build_descendant_tree_graph,
    build_family_tree_graph,
    build_pedigree_tree_graph,
    descendant_tree_expansion_options,
    family_tree_expansion_options,
    layout_descendant_tree,
    layout_pedigree_tree,
)
from gedcom_family_tree_layout import layout_family_tree_units

from . import graph_geometry as gg
from . import media_resolve

MARGIN = 54.0
NODE_W = 128.0        # narrow node (tkinter-style): 3 short text lines
IMG_H = 60.0          # image band height when images are shown
TEXT_H = 54.0         # three text lines: given+initials / surname / dates
GAP_X = 48.0
GAP_Y = 44.0          # room for the top/bottom edge handles
HANDLE_R = 8.0

# Expansion categories in draw order, and which node edge each handle sits on.
EXPAND_CATEGORIES = ("parents", "children", "siblings", "spouses")
HANDLE_EDGE = {"parents": "top", "children": "bottom",
               "siblings": "left", "spouses": "right"}

FILL_MALE = "#d9ecff"
FILL_FEMALE = "#ffe1ec"
FILL_NEUTRAL = "#f2f2f2"
TEXT_COLOR = "#1a1a1a"
SUBTEXT_COLOR = "#5a6068"
OUTLINE = "#9aa4af"
CENTER_OUTLINE = "#1155bb"

GRAPH_TYPES = [("tree", "Tree"), ("pedigree", "Pedigree"), ("descendant", "Descendant")]


def _mix(hex_a, hex_b, weight_b):
    a = hex_a.lstrip("#")
    b = hex_b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    m = [round(x * (1 - weight_b) + y * weight_b) for x, y in zip(ca, cb)]
    return "#%02x%02x%02x" % tuple(m)


class FamilyGraphWindow:
    def __init__(self, model, center_id, gedcom_path, *, graph_type="pedigree",
                 on_person_select=None):
        self.model = model
        self.center = center_id
        self.gedcom_path = str(gedcom_path) if gedcom_path else ""
        self.graph_type = graph_type
        self.on_person_select = on_person_select
        self.zoom = 1.0
        self.show_images = True
        self.tree_expanded = set()   # (id, category) requests for the tree view
        self.desc_expanded = set()   # ids whose children are shown (descendant view)
        self._press_at = (0, 0)
        self._img_cache = {}
        self._handle_hits = {}       # id -> [(category, cx, cy, r), ...]

        self._family_lookup = lambda i: gg.family_members(
            i, self.model.individuals, self.model.families)
        self._coparent_lookup = lambda i, ex: gg.coparents(
            i, ex, self.model.individuals, self.model.families)

        self._type_buttons = {
            v: toga.Button(lbl, on_press=self._type_handler(v), style=Pack(margin=(0, 2)))
            for v, lbl in GRAPH_TYPES
        }
        self.images_btn = toga.Button(
            "Images: on", on_press=lambda w: self._toggle_images(), style=Pack(margin=(0, 6)))
        self.info = toga.Label("", style=Pack(margin=(6, 8), flex=1))
        controls = toga.Box(style=Pack(direction=ROW, margin=4), children=[
            *self._type_buttons.values(),
            toga.Button("Zoom −", on_press=lambda w: self._bump_zoom(1 / 1.25)),
            toga.Button("Zoom +", on_press=lambda w: self._bump_zoom(1.25)),
            toga.Button("Reset", on_press=lambda w: self._reset_view()),
            self.images_btn, self.info,
        ])
        self.canvas = toga.Canvas(on_press=self._on_press, on_release=self._on_release)
        self.scroller = toga.ScrollContainer(
            horizontal=True, vertical=True, content=self.canvas, style=Pack(flex=1))
        root = toga.Box(style=Pack(direction=COLUMN, flex=1),
                        children=[controls, self.scroller])
        self.window = toga.Window(title="Family Graph", size=(1000, 760))
        self.window.content = root

        self._rebuild()

    def show(self):
        self.window.show()
        self._refresh_type_styles()
        self.redraw()

    # ---- geometry --------------------------------------------------------
    def _expandable_type(self):
        return self.graph_type in ("tree", "descendant")

    def _node_h(self):
        return TEXT_H + (IMG_H if self.show_images else 0)

    def _rebuild(self):
        m = self.model
        c = self.center
        if self.graph_type == "pedigree":
            visible, edges = build_pedigree_tree_graph(c, m.individuals, m.families)
            nodes = layout_pedigree_tree(c, visible, edges)
        elif self.graph_type == "descendant":
            expanded = set(self.desc_expanded) | {c}
            visible, edges = build_descendant_tree_graph(
                c, expanded, m.individuals, m.families)
            nodes = layout_descendant_tree(c, visible, edges)
        else:  # tree
            requests = list(self.tree_expanded)
            visible, edges = build_family_tree_graph(
                c, requests, self._family_lookup, self._coparent_lookup)
            nodes = layout_family_tree_units(c, visible, edges)
        self._visible = visible
        self.edges = edges
        nh = self._node_h()
        col_gap = NODE_W + GAP_X
        row_gap = nh + GAP_Y
        min_gen = min((n["generation"] for n in nodes), default=0)
        min_col = min((n["column"] for n in nodes), default=0)
        self.boxes = {}
        self._is_center = {}
        for n in nodes:
            x = MARGIN + (n["column"] - min_col) * col_gap
            y = MARGIN + (n["generation"] - min_gen) * row_gap
            self.boxes[n["id"]] = (x, y, NODE_W, nh)
            self._is_center[n["id"]] = bool(n.get("is_center"))
        self._update_info()

    def content_size(self):
        if not self.boxes:
            return 400, 400
        max_x = max(x + w for (x, y, w, h) in self.boxes.values())
        max_y = max(y + h for (x, y, w, h) in self.boxes.values())
        return max_x + MARGIN, max_y + MARGIN

    def _node_categories(self, iid):
        """Return [(category, is_expanded)] for the node's expand handles — one per
        category that has hidden relatives or is already expanded."""
        if self.graph_type == "tree":
            opts = family_tree_expansion_options(iid, self._visible, self._family_lookup)
            out = []
            for cat in EXPAND_CATEGORIES:
                expanded = (iid, cat) in self.tree_expanded
                if opts.get(cat) or expanded:
                    out.append((cat, expanded))
            return out
        if self.graph_type == "descendant":
            opts = descendant_tree_expansion_options(iid, self._visible, self._family_lookup)
            expanded = iid in self.desc_expanded
            if opts.get("children") or expanded:
                return [("children", expanded)]
        return []

    def _name_lines(self, iid):
        """(line1, line2, line3): given + middle initials / surname / lifespan."""
        ind = self.model.individuals.get(iid, {})
        given = (ind.get("given_name") or "").strip()
        surname = (ind.get("surname") or "").strip()
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f"({by or '?'}–{dy or ''})" if (by or dy) else ""
        if given:
            toks = given.split()
            line1 = toks[0]
            initials = " ".join(f"{t[0]}." for t in toks[1:] if t)
            if initials:
                line1 = f"{line1} {initials}"
            line2 = surname
        else:
            line1 = ind.get("name") or iid
            line2 = ""
        return line1[:18], line2[:18], years

    def _label(self, iid):
        ind = self.model.individuals.get(iid, {})
        name = ind.get("name") or iid
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = f"({by or '?'}–{dy or ''})" if (by or dy) else ""
        return name, years

    def _fill_for(self, iid, is_center):
        sex = (self.model.individuals.get(iid, {}).get("sex") or "").strip().upper()
        base = FILL_MALE if sex == "M" else FILL_FEMALE if sex == "F" else FILL_NEUTRAL
        return _mix(base, TEXT_COLOR, 0.12) if is_center else base

    def _image_for(self, iid):
        if iid in self._img_cache:
            return self._img_cache[iid]
        img = None
        try:
            path = media_resolve.resolve_person_media(
                self.model.individuals.get(iid, {}), self.gedcom_path)
            if path:
                img = toga.Image(path)
        except Exception:  # noqa: BLE001 — unreadable/unsupported image
            img = None
        self._img_cache[iid] = img
        return img

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
        for src, dst, *_ in self.edges:
            sb, db = self.boxes.get(src), self.boxes.get(dst)
            if not sb or not db:
                continue
            sx, sy = sb[0] + sb[2] / 2, sb[1] + sb[3] / 2
            dx, dy = db[0] + db[2] / 2, db[1] + db[3] / 2
            with c.stroke(color=OUTLINE, line_width=1.6):
                c.move_to(sx, sy)
                midy = (sy + dy) / 2
                c.line_to(sx, midy)
                c.line_to(dx, midy)
                c.line_to(dx, dy)

    def _draw_nodes(self):
        c = self.canvas
        self._handle_hits = {}
        for iid, (x, y, w, h) in self.boxes.items():
            is_center = self._is_center.get(iid)
            fill = self._fill_for(iid, is_center)
            with c.fill(color=fill):
                c.round_rect(x, y, w, h, 8)
            with c.stroke(color=CENTER_OUTLINE if is_center else OUTLINE,
                          line_width=2.4 if is_center else 1.4):
                c.round_rect(x, y, w, h, 8)
            text_top = y + IMG_H if self.show_images else y
            if self.show_images:
                self._draw_image(iid, x, y, w)
            line1, line2, line3 = self._name_lines(iid)
            with c.fill(color=TEXT_COLOR):
                c.fill_text(line1, x + 8, text_top + 15, font=toga.Font("sans-serif", 11))
                if line2:
                    c.fill_text(line2, x + 8, text_top + 31, font=toga.Font("sans-serif", 11))
            if line3:
                with c.fill(color=SUBTEXT_COLOR):
                    c.fill_text(line3, x + 8, text_top + 47, font=toga.Font("sans-serif", 9))
            if self._expandable_type():
                self._draw_handles(iid, x, y, w, h)

    def _draw_handles(self, iid, x, y, w, h):
        """Draw expand/collapse handles as small nubs on the node edges — parents top,
        children bottom, siblings left, spouses right (tkinter convention)."""
        cats = self._node_categories(iid)
        if not cats:
            return
        centers = {
            "top": (x + w / 2, y), "bottom": (x + w / 2, y + h),
            "left": (x, y + h / 2), "right": (x + w, y + h / 2),
        }
        hits = []
        for cat, expanded in cats:
            cx, cy = centers[HANDLE_EDGE[cat]]
            with self.canvas.fill(color="#cfe3ff" if expanded else "#eef1f4"):
                self.canvas.arc(cx, cy, HANDLE_R, 0, 6.2832)
            with self.canvas.stroke(color=CENTER_OUTLINE if expanded else OUTLINE,
                                    line_width=1.2):
                self.canvas.arc(cx, cy, HANDLE_R, 0, 6.2832)
            with self.canvas.fill(color=TEXT_COLOR):
                self.canvas.fill_text("−" if expanded else "+", cx - 3, cy + 4,
                                      font=toga.Font("sans-serif", 12))
            hits.append((cat, cx, cy, HANDLE_R))
        self._handle_hits[iid] = hits

    def _draw_image(self, iid, x, y, w):
        img = self._image_for(iid)
        if img is None:
            return
        region_w, region_h = w - 12, IMG_H - 8
        dw, dh = region_w, region_h
        try:
            iw, ih = img.size
            if iw and ih:
                scale = min(region_w / iw, region_h / ih)
                dw, dh = iw * scale, ih * scale
        except Exception:  # noqa: BLE001 — size unavailable; stretch to region
            pass
        ix = x + (w - dw) / 2
        iy = y + 4 + (region_h - dh) / 2
        try:
            self.canvas.draw_image(img, ix, iy, dw, dh)
        except Exception:  # noqa: BLE001 — backend draw hiccup
            pass

    # ---- interaction -----------------------------------------------------
    def _on_press(self, widget, x, y, **kw):
        self._press_at = (x, y)

    def _on_release(self, widget, x, y, **kw):
        if abs(x - self._press_at[0]) + abs(y - self._press_at[1]) >= 4:
            return
        wx, wy = x / self.zoom, y / self.zoom
        # edge handles take priority over node-body recenter
        for iid, handles in self._handle_hits.items():
            for cat, cx, cy, r in handles:
                if (wx - cx) ** 2 + (wy - cy) ** 2 <= (r + 2) ** 2:
                    self._toggle_category(iid, cat)
                    return
        for iid, (bx, by, bw, bh) in self.boxes.items():
            if bx <= wx <= bx + bw and by <= wy <= by + bh:
                self._recenter(iid)
                return

    def _toggle_category(self, iid, cat):
        if self.graph_type == "descendant":
            self.desc_expanded.symmetric_difference_update({iid})
        else:  # tree
            self.tree_expanded.symmetric_difference_update({(iid, cat)})
        self._rebuild()
        self.redraw()

    def _recenter(self, iid):
        if iid == self.center:
            if self.on_person_select:
                self.on_person_select(iid)
            return
        self.center = iid
        self.tree_expanded = set()
        self.desc_expanded = set()
        self._rebuild()
        self.redraw()
        if self.on_person_select:
            self.on_person_select(iid)

    def set_type(self, graph_type, *, notify=True):
        self.graph_type = graph_type
        self.tree_expanded = set()
        self.desc_expanded = set()
        self._refresh_type_styles()
        self._rebuild()
        self.redraw()

    def _type_handler(self, value):
        return lambda w: self.set_type(value)

    def _toggle_images(self):
        self.show_images = not self.show_images
        self.images_btn.text = "Images: on" if self.show_images else "Images: off"
        self._rebuild()
        self.redraw()

    def _bump_zoom(self, factor):
        self.zoom = max(0.3, min(3.0, self.zoom * factor))
        self._update_info()
        self.redraw()

    def _reset_view(self):
        self.zoom = 1.0
        self._update_info()
        self.redraw()

    def _refresh_type_styles(self):
        for v, b in self._type_buttons.items():
            label = dict(GRAPH_TYPES)[v]
            b.text = f"● {label}" if v == self.graph_type else label

    def _update_info(self):
        name, _ = self._label(self.center)
        self.info.text = f"{name}   nodes: {len(self.boxes)}   zoom: {self.zoom:.2f}"
