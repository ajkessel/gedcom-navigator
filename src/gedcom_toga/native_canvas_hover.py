"""
Native hover tooltips over Toga Canvas node regions (macOS + Windows).

Toga has no mouse-move event, so per-node hover can't be done in pure Toga. This
reaches into `canvas._impl.native` per backend, using a `regions()` callable that
returns the node rectangles + text in canvas pixel/view coords (content * zoom):

  - macOS (Cocoa/rubicon-objc): registers ONE tooltip rect PER node via
    `addToolTipRect:owner:userData:`. Per-node rects are essential: Cocoa only
    re-queries / hides the tooltip when the cursor crosses a rect boundary, so a
    single canvas-sized rect leaves stale tooltips that never dismiss. With per-node
    rects, moving into the gaps (no rect) hides it and moving to another node shows
    the new text. The `view:stringForToolTip:point:userData:` owner hit-tests the
    point against the cached regions.
  - Windows (WinForms/Python.NET): the control's `MouseMove` drives a persistent
    `System.Windows.Forms.ToolTip`; SetToolTip is updated only when the hovered text
    changes (and cleared to "" over gaps).
  - GTK: not implemented (would use the `query-tooltip` signal). No-ops.

`install(canvas, regions)` where `regions() -> list[(x, y, w, h, text)]` in canvas
pixel coords. Returns `refresh()` — call it after every redraw (zoom/recenter changes
the rects). No-ops cleanly where unsupported.

UNTESTED in the Linux spike sandbox — verify on macOS and Windows. On Cocoa, watch for
Y-flip (see FLIP_Y note): if a node's tooltip fires over the vertically-mirrored spot,
flip each rect's y with the canvas height.
"""

_REGIONS = {}        # Cocoa: view ptr -> [(x, y, w, h, text), ...]
_owner = None        # Cocoa: shared tooltip-rect owner
_WIN_KEEPALIVE = []  # WinForms: keep ToolTip + delegate refs from GC
_available = None


def _hit_regions(regions, px, py):
    for (x, y, w, h, text) in regions:
        if x <= px <= x + w and y <= py <= y + h:
            return text
    return None


# ---------------------------------------------------------------- macOS (Cocoa)
def _cocoa():
    try:
        from rubicon.objc import (
            NSObject, objc_method, CGPoint, CGRect, CGSize, ObjCInstance, at,
        )
    except Exception:  # noqa: BLE001 — not macOS / no rubicon
        return None
    return NSObject, objc_method, CGPoint, CGRect, CGSize, ObjCInstance, at


def _build_owner_class():
    NSObject, objc_method, CGPoint, CGRect, CGSize, ObjCInstance, at = _cocoa()

    class TogaCanvasTooltipOwner(NSObject):
        @objc_method
        def view_stringForToolTip_point_userData_(
            self, view, tag: int, point: CGPoint, userData
        ) -> ObjCInstance:
            text = _hit_regions(_REGIONS.get(view.ptr.value, ()), point.x, point.y)
            # FLIP_Y: if wrong-node vertically, hit-test with
            # (view.bounds.size.height - point.y) instead of point.y.
            return at(text) if text else None

    return TogaCanvasTooltipOwner


def _install_cocoa(canvas, regions):
    global _owner
    _, _, CGPoint, CGRect, CGSize, _, _ = _cocoa()
    native = canvas._impl.native
    if _owner is None:
        _owner = _build_owner_class().alloc().init()

    def refresh():
        n = canvas._impl.native
        regs = list(regions())
        _REGIONS[n.ptr.value] = regs
        n.removeAllToolTips()
        for (x, y, w, h, _text) in regs:
            n.addToolTipRect(
                CGRect(CGPoint(x, y), CGSize(w, h)), owner=_owner, userData=None
            )

    refresh()
    return refresh


# ------------------------------------------------------------- Windows (WinForms)
def _install_winforms(canvas, regions):
    from System.Windows.Forms import ToolTip
    native = canvas._impl.native
    tooltip = ToolTip()
    state = {"regs": list(regions()), "last": None}

    def on_move(sender, e):  # MouseEventArgs: client-relative X/Y
        text = _hit_regions(state["regs"], e.X, e.Y) or ""
        if text != state["last"]:
            state["last"] = text
            tooltip.SetToolTip(native, text)

    native.MouseMove += on_move
    _WIN_KEEPALIVE.append((tooltip, on_move))

    def refresh():
        state["regs"] = list(regions())

    return refresh


# ------------------------------------------------------------------------ dispatch
def install(canvas, regions):
    global _available
    if _available is False:
        return lambda: None
    try:
        if _cocoa() is not None:
            _available = True
            return _install_cocoa(canvas, regions)
        try:
            import System.Windows.Forms  # noqa: F401 — probe for WinForms
        except Exception:  # noqa: BLE001
            _available = False
            return lambda: None
        _available = True
        return _install_winforms(canvas, regions)
    except Exception as exc:  # noqa: BLE001 — spike diagnostic
        print(f"[canvas-hover] native install failed: {type(exc).__name__}: {exc}")
        _available = False
        return lambda: None
