"""
Native hover tooltips over Toga Canvas node regions (macOS + Windows).

Toga has no mouse-move event, so per-node hover can't be done in pure Toga. This
reaches into `canvas._impl.native` per backend:

  - macOS (Cocoa/rubicon-objc): Cocoa's tooltip-rect machinery —
    `addToolTipRect:owner:userData:` + a `view:stringForToolTip:point:userData:`
    owner. The OS handles hover detection, delay, and rendering.
  - Windows (WinForms/Python.NET): subscribe to the control's `MouseMove` event and
    drive a persistent `System.Windows.Forms.ToolTip` via `SetToolTip`.
  - GTK: not implemented here (would use the `query-tooltip` signal). No-ops.

`install(canvas, resolve)` where `resolve(x, y) -> str | None` (x/y in canvas-local
coords). Returns a `refresh()` callable to re-register after a resize (needed on Cocoa;
no-op on WinForms, whose handler is position-dynamic). No-ops cleanly where unsupported,
so the spike still runs everywhere.

UNTESTED in the Linux spike sandbox — verify on macOS and Windows. On Cocoa, watch for
Y-flip (see FLIP_Y note).
"""

_RESOLVERS = {}          # Cocoa: view ptr -> resolve(x, y)
_owner = None            # Cocoa: shared tooltip-rect owner
_WIN_KEEPALIVE = []      # WinForms: keep ToolTip + delegates from being GC'd
_available = None


# ---------------------------------------------------------------- macOS (Cocoa)
def _cocoa():
    try:
        from rubicon.objc import NSObject, objc_method, CGPoint, ObjCInstance, at
    except Exception:  # noqa: BLE001 — not macOS / no rubicon
        return None
    return NSObject, objc_method, CGPoint, ObjCInstance, at


def _build_owner_class():
    NSObject, objc_method, CGPoint, ObjCInstance, at = _cocoa()

    class TogaCanvasTooltipOwner(NSObject):
        @objc_method
        def view_stringForToolTip_point_userData_(
            self, view, tag: int, point: CGPoint, userData
        ) -> ObjCInstance:
            resolve = _RESOLVERS.get(view.ptr.value)
            if resolve is None:
                return None
            # point is in the canvas view's coord space (same as on_press coords).
            # FLIP_Y: if the view is NOT flipped, use view.bounds.size.height - point.y.
            text = resolve(point.x, point.y)
            return at(text) if text else None

    return TogaCanvasTooltipOwner


def _install_cocoa(canvas, resolve):
    global _owner
    native = canvas._impl.native
    _RESOLVERS[native.ptr.value] = resolve
    if _owner is None:
        _owner = _build_owner_class().alloc().init()

    def refresh():
        n = canvas._impl.native
        n.removeAllToolTips()
        n.addToolTipRect(n.bounds, owner=_owner, userData=None)

    refresh()
    return refresh


# ------------------------------------------------------------- Windows (WinForms)
def _install_winforms(canvas, resolve):
    from System.Windows.Forms import ToolTip
    native = canvas._impl.native
    tooltip = ToolTip()
    state = {"last": None}

    def on_move(sender, e):  # e is MouseEventArgs (client-relative X/Y)
        text = resolve(e.X, e.Y) or ""
        if text != state["last"]:
            state["last"] = text
            tooltip.SetToolTip(native, text)

    native.MouseMove += on_move
    _WIN_KEEPALIVE.append((tooltip, on_move))  # prevent GC of the .NET delegate
    return lambda: None  # position-dynamic; nothing to re-register on resize


# ------------------------------------------------------------------------ dispatch
def install(canvas, resolve):
    global _available
    if _available is False:
        return lambda: None
    try:
        if _cocoa() is not None:
            _available = True
            return _install_cocoa(canvas, resolve)
        try:
            import System.Windows.Forms  # noqa: F401 — probe for WinForms
        except Exception:  # noqa: BLE001
            _available = False
            return lambda: None
        _available = True
        return _install_winforms(canvas, resolve)
    except Exception as exc:  # noqa: BLE001 — spike diagnostic
        print(f"[canvas-hover] native install failed: {type(exc).__name__}: {exc}")
        _available = False
        return lambda: None
