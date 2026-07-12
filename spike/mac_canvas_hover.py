"""
macOS-only prototype: native hover tooltips over Toga Canvas node regions.

Toga has no mouse-move event, so per-node hover can't be done in pure Toga. This
reaches into `canvas._impl.native` (the NSView) and uses Cocoa's built-in
tooltip-rect machinery — `addToolTipRect:owner:userData:` + an owner implementing
`view:stringForToolTip:point:userData:`. Cocoa handles hover detection, the standard
delay, and native rendering; our callback only hit-tests the point and returns text.

This is the "native-layer tax" the migration write-up calls out, in concrete form:
~40 lines, isolated, depends on the private `_impl.native` + rubicon-objc (bundled with
toga-cocoa). No-ops cleanly on non-macOS backends (returns a no-op refresh callable), so
the spike still runs elsewhere.

UNTESTED in the Linux spike sandbox — verify on macOS. If hover text appears offset
vertically, flip Y (see FLIP_Y note below): toga-cocoa's canvas view is expected to be
flipped (top-left origin, matching press coords), but confirm on-device.
"""

# view pointer -> resolve(x, y) -> str | None
_RESOLVERS = {}
_owner = None
_available = None  # tri-state cache: None=unknown, True/False after first probe


def _cocoa():
    """Return the rubicon-objc bits we need, or None if not on a Cocoa backend."""
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
            # point is in the canvas view's coordinate space — the same space as
            # Toga on_press coords (canvas sized to content*zoom). FLIP_Y: if the
            # view is NOT flipped, use `view.bounds.size.height - point.y`.
            text = resolve(point.x, point.y)
            return at(text) if text else None

    return TogaCanvasTooltipOwner


def install(canvas, resolve):
    """Register native hover tooltips on `canvas`; `resolve(x, y) -> str | None`.

    Returns a `refresh()` callable to re-register after the canvas resizes (zoom),
    or a no-op callable on non-macOS backends.
    """
    global _owner, _available
    if _available is False:
        return lambda: None
    parts = _cocoa()
    if parts is None:
        _available = False
        return lambda: None
    try:
        native = canvas._impl.native
        _RESOLVERS[native.ptr.value] = resolve
        if _owner is None:
            _owner = _build_owner_class().alloc().init()
        _available = True

        def refresh():
            n = canvas._impl.native
            n.removeAllToolTips()
            n.addToolTipRect(n.bounds, owner=_owner, userData=None)

        refresh()
        return refresh
    except Exception as exc:  # noqa: BLE001 — spike diagnostic
        print(f"[canvas-hover] native install failed: {type(exc).__name__}: {exc}")
        _available = False
        return lambda: None
