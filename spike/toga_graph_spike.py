"""
Throwaway Toga spike — deliverable (a) of the migration go/no-go.

Proves that the existing, tkinter-free layout engine
(gedcom_family_tree.layout_pedigree_tree) can drive a Toga Canvas:
  - node boxes (round_rect) + labels (write_text) + parent edges (line_to)
  - click a node to recenter (hit-testing against layout boxes)
  - zoom via native context transform (scale/translate) — NOT re-layout
  - drag to pan
  - selected-node info panel (stands in for hover tooltips, which Toga
    Canvas cannot do — no mouse-move event)

Run headed:   spike-venv/bin/python spike/toga_graph_spike.py
Render a PNG:  GEDCOM_SPIKE_SNAPSHOT=out.png spike-venv/bin/python spike/toga_graph_spike.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import toga
import mac_canvas_hover
from toga.style.pack import COLUMN, ROW, Pack

from gedcom_parser import build_model
import gedcom_family_tree as ft

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "fictional_genealogy.ged")

# pixel geometry (mirrors the tk renderer's gaps, pre-zoom)
COL_GAP = 200.0
ROW_GAP = 90.0
NODE_W = 170.0
NODE_H = 46.0
MARGIN = 60.0


def add_native_tooltip(widget, text):
    """Workaround for Toga's missing tooltip API: set the OS-native tooltip on the
    backing widget. macOS: NSView.toolTip; GTK: set_tooltip_text(). Isolated here so
    the whole app's tooltip dependency on private `_impl.native` lives in one place."""
    try:
        native = widget._impl.native  # private API — the isolated bet
    except AttributeError:
        return False
    # GTK
    if hasattr(native, "set_tooltip_text"):
        native.set_tooltip_text(text)
        return True
    # Cocoa (rubicon-objc): NSView/NSControl exposes a toolTip property
    try:
        native.toolTip = text
        return True
    except Exception:  # noqa: BLE001 — spike diagnostic
        return False


class GraphModel:
    """Owns the parsed data + current center; produces positioned nodes/edges."""

    def __init__(self, path):
        res = build_model(path, "DNA", "AncestryDNA Match")
        self.individuals, self.families = res[0], res[1]
        self.center = self._widest_pedigree_center()
        self.rebuild()

    def _widest_pedigree_center(self):
        best = (None, -1)
        for iid in self.individuals:
            visible, _ = ft.build_pedigree_tree_graph(iid, self.individuals, self.families)
            if len(visible) > best[1]:
                best = (iid, len(visible))
        return best[0]

    def rebuild(self):
        visible, edges = ft.build_pedigree_tree_graph(
            self.center, self.individuals, self.families
        )
        nodes = ft.layout_pedigree_tree(self.center, visible, edges)
        # generation (row) can be negative; normalize to >= 0 for pixel space
        min_gen = min((n["generation"] for n in nodes), default=0.0)
        self.boxes = {}  # id -> (x, y, w, h) in pre-zoom pixel space
        for n in nodes:
            x = MARGIN + n["column"] * COL_GAP
            y = MARGIN + (n["generation"] - min_gen) * ROW_GAP
            self.boxes[n["id"]] = (x, y, NODE_W, NODE_H)
        self.nodes = nodes
        self.edges = [(s, t) for (s, t, cat) in edges if cat == "parents"]

    def label(self, indi_id):
        ind = self.individuals.get(indi_id, {})
        name = ind.get("name") or indi_id
        by, dy = ind.get("birth_year"), ind.get("death_year")
        years = ""
        if by or dy:
            years = f"  ({by or '?'}–{dy or ''})"
        return name, years

    def content_size(self):
        max_x = max((x + w for (x, y, w, h) in self.boxes.values()), default=400)
        max_y = max((y + h for (x, y, w, h) in self.boxes.values()), default=400)
        return max_x + MARGIN, max_y + MARGIN


class SpikeApp(toga.App):
    def startup(self):
        self.model = GraphModel(SAMPLE)
        self.zoom = 1.0
        self.selected = self.model.center

        # Canvas sized to content*zoom; a ScrollContainer provides NATIVE
        # wheel/trackpad panning (the scroll-wheel workaround). Zoom is
        # buttons + Cmd +/-/0 keyboard commands (no wheel-zoom in Toga).
        self.canvas = toga.Canvas(
            on_press=self.on_press,
            on_release=self.on_release,
        )
        self.scroller = toga.ScrollContainer(
            horizontal=True, vertical=True, content=self.canvas, style=Pack(flex=1)
        )
        self.info = toga.Label(
            self._info_text(), style=Pack(padding=(6, 8), flex=1)
        )
        btn_out = toga.Button("Zoom −", on_press=lambda w: self.bump_zoom(1 / 1.25))
        btn_in = toga.Button("Zoom +", on_press=lambda w: self.bump_zoom(1.25))
        btn_reset = toga.Button("Reset", on_press=lambda w: self.reset_view())
        controls = toga.Box(
            style=Pack(direction=ROW, padding=4),
            children=[btn_out, btn_in, btn_reset, self.info],
        )
        root = toga.Box(style=Pack(direction=COLUMN), children=[controls, self.scroller])
        self.main_window = toga.MainWindow(title="Toga Graph Spike", size=(1100, 760))
        self.main_window.content = root

        # Tooltip workaround: native OS tooltips via _impl.native (test on Mac).
        self._tooltips_ok = all([
            add_native_tooltip(btn_out, "Zoom out (Cmd −)"),
            add_native_tooltip(btn_in, "Zoom in (Cmd +)"),
            add_native_tooltip(btn_reset, "Reset zoom (Cmd 0)"),
        ])

        # Keyboard zoom as proper Mac menu commands.
        grp = toga.Group.VIEW
        self.commands.add(
            toga.Command(lambda w: self.bump_zoom(1.25), "Zoom In",
                         shortcut=toga.Key.MOD_1 + "+", group=grp),
            toga.Command(lambda w: self.bump_zoom(1 / 1.25), "Zoom Out",
                         shortcut=toga.Key.MOD_1 + "-", group=grp),
            toga.Command(lambda w: self.reset_view(), "Actual Size",
                         shortcut=toga.Key.MOD_1 + "0", group=grp),
        )

        self.main_window.show()
        self._hover_refresh = None
        self.redraw()
        # native canvas hover tooltips (macOS only; no-op elsewhere)
        self._hover_refresh = mac_canvas_hover.install(self.canvas, self._hover_text)

        snapshot = os.environ.get("GEDCOM_SPIKE_SNAPSHOT")
        if snapshot:
            # render one frame to PNG for headless verification, then exit
            self.add_background_task(self._snapshot_and_exit)

    # ---- rendering -------------------------------------------------------
    def redraw(self):
        c = self.canvas
        # size the canvas to content*zoom so the ScrollContainer can pan it natively
        cw, ch = self.model.content_size()
        c.style.width = int(cw * self.zoom)
        c.style.height = int(ch * self.zoom)
        c.context.clear()
        with c.context.Context() as ctx:
            ctx.scale(self.zoom, self.zoom)  # pan is the ScrollContainer's job
            self._draw_edges(ctx)
            self._draw_nodes(ctx)
        c.redraw()
        # canvas resized (zoom/recenter) → re-register the native tooltip rect
        if getattr(self, "_hover_refresh", None):
            self._hover_refresh()

    def _hover_text(self, x, y):
        """Resolve a hover point (canvas coords) to a person label, or None."""
        hit = self._hit(x, y)
        if not hit:
            return None
        name, years = self.model.label(hit)
        return f"{name}{years}"

    def _draw_edges(self, ctx):
        for child_id, parent_id in self.model.edges:
            cb = self.model.boxes.get(child_id)
            pb = self.model.boxes.get(parent_id)
            if not cb or not pb:
                continue
            cx, cy = cb[0] + cb[2], cb[1] + cb[3] / 2          # child right-center
            px, py = pb[0], pb[1] + pb[3] / 2                    # parent left-center
            with ctx.Stroke(color="#8a8f98", line_width=1.6) as s:
                s.move_to(cx, cy)
                mid = (cx + px) / 2
                s.line_to(mid, cy)
                s.line_to(mid, py)
                s.line_to(px, py)

    def _draw_nodes(self, ctx):
        for indi_id, (x, y, w, h) in self.model.boxes.items():
            is_center = indi_id == self.model.center
            is_sel = indi_id == self.selected
            fill = "#1f6feb" if is_center else ("#2d333b" if is_sel else "#22272e")
            with ctx.Fill(color=fill) as f:
                f.round_rect(x, y, w, h, 8)
            with ctx.Stroke(color="#4fa3ff" if is_sel else "#444c56", line_width=1.8) as s:
                s.round_rect(x, y, w, h, 8)
            name, years = self.model.label(indi_id)
            with ctx.Fill(color="#ffffff") as f:
                f.write_text(name[:22], x + 10, y + 20, font=toga.Font("sans-serif", 12))
            if years:
                with ctx.Fill(color="#9aa4af") as f:
                    f.write_text(years.strip(), x + 10, y + 38, font=toga.Font("sans-serif", 10))

    # ---- interaction -----------------------------------------------------
    def _hit(self, x, y):
        """Canvas-local press coords → node id (undo only the zoom scale;
        pan is handled by the ScrollContainer so x,y are already content-local)."""
        wx, wy = x / self.zoom, y / self.zoom
        for indi_id, (bx, by, bw, bh) in self.model.boxes.items():
            if bx <= wx <= bx + bw and by <= wy <= by + bh:
                return indi_id
        return None

    def on_press(self, widget, x, y, **kw):
        self._press_at = (x, y)

    def on_release(self, widget, x, y, **kw):
        moved = abs(x - self._press_at[0]) + abs(y - self._press_at[1])
        if moved < 4:  # a click, not a drag-scroll
            hit = self._hit(x, y)
            if hit:
                self.selected = hit
                if hit != self.model.center:
                    self.model.center = hit
                    self.model.rebuild()
                self.info.text = self._info_text()
                self.redraw()

    def bump_zoom(self, factor):
        self.zoom = max(0.3, min(3.0, self.zoom * factor))
        self.info.text = self._info_text()
        self.redraw()

    def reset_view(self):
        self.zoom = 1.0
        self.info.text = self._info_text()
        self.redraw()

    def _info_text(self):
        name, years = self.model.label(self.selected)
        return f"Selected: {name}{years}   |   nodes: {len(self.model.boxes)}   zoom: {self.zoom:.2f}"

    async def _snapshot_and_exit(self, widget, **kw):
        import asyncio
        await asyncio.sleep(0.5)
        path = os.environ["GEDCOM_SPIKE_SNAPSHOT"]
        try:
            img = self.canvas.as_image()
            img.save(path)
            print(f"SNAPSHOT_OK {path}")
        except Exception as exc:  # noqa: BLE001 — spike diagnostic
            print(f"SNAPSHOT_FAIL {type(exc).__name__}: {exc}")
        self.request_exit()


def main():
    return SpikeApp("Toga Graph Spike", "org.beeware.gedcom.spike")


if __name__ == "__main__":
    main().main_loop()
