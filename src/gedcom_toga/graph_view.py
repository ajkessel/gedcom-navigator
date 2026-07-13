"""Graph view — Canvas-based family tree with zoom, pan, and node selection.

Adapted from spike/toga_graph_spike.py for Phase 4 integration.
"""
import toga
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_family_tree import build_pedigree_tree_graph, layout_pedigree_tree

# Pixel geometry (mirrors the tk renderer's gaps, pre-zoom)
COL_GAP = 200.0
ROW_GAP = 90.0
NODE_W = 170.0
NODE_H = 46.0
MARGIN = 60.0

_WINFORMS_TOOLTIP = None


def add_native_tooltip(widget, text):
    """Set OS-native tooltip on a widget via _impl.native (GTK/WinForms/Cocoa)."""
    global _WINFORMS_TOOLTIP
    try:
        native = widget._impl.native
    except AttributeError:
        return False
    # GTK
    if hasattr(native, "set_tooltip_text"):
        native.set_tooltip_text(text)
        return True
    # WinForms
    try:
        from System.Windows.Forms import ToolTip
        if _WINFORMS_TOOLTIP is None:
            _WINFORMS_TOOLTIP = ToolTip()
        _WINFORMS_TOOLTIP.SetToolTip(native, text)
        return True
    except Exception:  # noqa: BLE001
        pass
    # Cocoa
    try:
        native.toolTip = text
        return True
    except Exception:  # noqa: BLE001
        return False


class GraphModel:
    """Manages the parsed GEDCOM data + current center; produces positioned nodes/edges."""

    def __init__(self, individuals, families):
        self.individuals = individuals
        self.families = families
        self.center = None
        self.boxes = {}
        self.nodes = []
        self.edges = []

    def set_center(self, center_id):
        """Set the center person and rebuild the graph layout."""
        if center_id not in self.individuals:
            return
        self.center = center_id
        self._rebuild()

    def _rebuild(self):
        if not self.center:
            self.boxes = {}
            self.nodes = []
            self.edges = []
            return
        visible, edges = build_pedigree_tree_graph(
            self.center, self.individuals, self.families
        )
        nodes = layout_pedigree_tree(self.center, visible, edges)
        min_gen = min((n["generation"] for n in nodes), default=0.0)
        self.boxes = {}
        for n in nodes:
            x = MARGIN + n["column"] * COL_GAP
            y = MARGIN + (n["generation"] - min_gen) * ROW_GAP
            self.boxes[n["id"]] = (x, y, NODE_W, NODE_H)
        self.nodes = nodes
        self.edges = [(s, t) for (s, t, cat) in edges if cat == "parents"]

    def label(self, indi_id):
        """Return (name, years) tuple for a person."""
        ind = self.individuals.get(indi_id, {})
        name = ind.get("name") or indi_id
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = ""
        if by or dy:
            years = f"  ({by or '?'}–{dy or ''})"
        return name, years

    def content_size(self):
        """Return (width, height) of the graph content."""
        if not self.boxes:
            return 400, 400
        max_x = max((x + w for (x, y, w, h) in self.boxes.values()), default=400)
        max_y = max((y + h for (x, y, w, h) in self.boxes.values()), default=400)
        return max_x + MARGIN, max_y + MARGIN


class GraphView:
    """Reusable graph view widget with zoom, pan, and click-to-select."""

    def __init__(self, individuals, families, on_person_select=None):
        self.model = GraphModel(individuals, families)
        self.zoom = 1.0
        self.selected = None
        self.on_person_select = on_person_select

        self.canvas = toga.Canvas(on_press=self._on_press, on_release=self._on_release)
        self.scroller = toga.ScrollContainer(
            horizontal=True, vertical=True, content=self.canvas, style=Pack(flex=1)
        )
        self.info = toga.Label("", style=Pack(margin=(6, 8), flex=1))
        btn_out = toga.Button("Zoom −", on_press=lambda w: self._bump_zoom(1 / 1.25))
        btn_in = toga.Button("Zoom +", on_press=lambda w: self._bump_zoom(1.25))
        btn_reset = toga.Button("Reset", on_press=lambda w: self._reset_view())
        add_native_tooltip(btn_out, "Zoom out (Cmd −)")
        add_native_tooltip(btn_in, "Zoom in (Cmd +)")
        add_native_tooltip(btn_reset, "Reset zoom (Cmd 0)")

        controls = toga.Box(
            style=Pack(direction=ROW, margin=4),
            children=[btn_out, btn_in, btn_reset, self.info],
        )
        self.container = toga.Box(
            style=Pack(direction=COLUMN, flex=1), children=[controls, self.scroller]
        )
        self._press_at = (0, 0)
        self._hover_refresh = None

    def set_center(self, center_id):
        """Set the center person and redraw the graph."""
        self.model.set_center(center_id)
        self.selected = center_id
        self._update_info()
        self.redraw()

    def update_data(self, individuals, families):
        """Update the underlying data model (after reload)."""
        self.model.individuals = individuals
        self.model.families = families
        if self.model.center:
            self.model._rebuild()
            self.redraw()

    def redraw(self):
        """Redraw the canvas with current zoom and model state."""
        c = self.canvas
        cw, ch = self.model.content_size()
        c.style.width = int(cw * self.zoom)
        c.style.height = int(ch * self.zoom)
        c.root_state.drawing_actions.clear()
        with c.state():
            c.scale(self.zoom, self.zoom)
            self._draw_edges()
            self._draw_nodes()
        c.redraw()
        if self._hover_refresh:
            self._hover_refresh()

    def _draw_edges(self):
        c = self.canvas
        for child_id, parent_id in self.model.edges:
            cb = self.model.boxes.get(child_id)
            pb = self.model.boxes.get(parent_id)
            if not cb or not pb:
                continue
            cx, cy = cb[0] + cb[2], cb[1] + cb[3] / 2
            px, py = pb[0], pb[1] + pb[3] / 2
            with c.stroke(color="#8a8f98", line_width=1.6):
                c.move_to(cx, cy)
                mid = (cx + px) / 2
                c.line_to(mid, cy)
                c.line_to(mid, py)
                c.line_to(px, py)

    def _draw_nodes(self):
        c = self.canvas
        for indi_id, (x, y, w, h) in self.model.boxes.items():
            is_center = indi_id == self.model.center
            is_sel = indi_id == self.selected
            fill_color = "#1f6feb" if is_center else ("#2d333b" if is_sel else "#22272e")
            with c.fill(color=fill_color):
                c.round_rect(x, y, w, h, 8)
            with c.stroke(color="#4fa3ff" if is_sel else "#444c56", line_width=1.8):
                c.round_rect(x, y, w, h, 8)
            name, years = self.model.label(indi_id)
            with c.fill(color="#ffffff"):
                c.fill_text(name[:22], x + 10, y + 20, font=toga.Font("sans-serif", 12))
            if years:
                with c.fill(color="#9aa4af"):
                    c.fill_text(years.strip(), x + 10, y + 38, font=toga.Font("sans-serif", 10))

    def _hit(self, x, y):
        """Canvas-local press coords → node id."""
        wx, wy = x / self.zoom, y / self.zoom
        for indi_id, (bx, by, bw, bh) in self.model.boxes.items():
            if bx <= wx <= bx + bw and by <= wy <= by + bh:
                return indi_id
        return None

    def _on_press(self, widget, x, y, **kw):
        self._press_at = (x, y)

    def _on_release(self, widget, x, y, **kw):
        moved = abs(x - self._press_at[0]) + abs(y - self._press_at[1])
        if moved < 4:
            hit = self._hit(x, y)
            if hit:
                self.selected = hit
                if hit != self.model.center:
                    self.model.center = hit
                    self.model._rebuild()
                self._update_info()
                self.redraw()
                if self.on_person_select:
                    self.on_person_select(hit)

    def _bump_zoom(self, factor):
        self.zoom = max(0.3, min(3.0, self.zoom * factor))
        self._update_info()
        self.redraw()

    def _reset_view(self):
        self.zoom = 1.0
        self._update_info()
        self.redraw()

    def _update_info(self):
        if not self.selected or self.selected not in self.model.individuals:
            self.info.text = ""
            return
        name, years = self.model.label(self.selected)
        self.info.text = f"Selected: {name}{years}   |   nodes: {len(self.model.boxes)}   zoom: {self.zoom:.2f}"

    def install_hover_tooltips(self):
        """Install native per-node hover tooltips (macOS + Windows)."""
        try:
            from . import native_canvas_hover
            self._hover_refresh = native_canvas_hover.install(
                self.canvas, self._hover_regions
            )
        except Exception:  # noqa: BLE001
            pass

    def _hover_regions(self):
        """Node rectangles + text in canvas pixel coords for hover tooltips."""
        z = self.zoom
        regions = []
        for indi_id, (x, y, w, h) in self.model.boxes.items():
            name, years = self.model.label(indi_id)
            regions.append((x * z, y * z, w * z, h * z, f"{name}{years}"))
        return regions
