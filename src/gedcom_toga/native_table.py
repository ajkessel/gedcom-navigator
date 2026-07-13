"""Native per-column widths for Toga Tables.

Toga has no public column-width API — every backend distributes the table width
*equally* across columns (Cocoa `sizeToFit`, WinForms `ClientSize.Width / num_cols`),
and the core `Column`/`AccessorColumn` classes carry no width. Custom column widths
are a known, still-open Toga feature (beeware/toga#4238). This reaches into
`table._impl` per backend — the same isolated "native-layer tax" the graph tooltips
already pay (see native_canvas_hover.py) — to give narrow columns (e.g. birth/death
years) fixed widths and let one flexible column (e.g. a name) absorb the rest.

`apply_column_widths(table, widths)` where `widths` is a list aligned to the table's
columns; each entry is a fixed pixel width, or `None` for the single flexible column
that soaks up the remaining space. Safe to call repeatedly (after show / after each
data refresh). No-ops cleanly where unsupported.

Neither backend re-equalizes on window resize — Cocoa `sizeToFit` and WinForms
`_resize_columns` only fire on column insert/remove, which we never do after
construction — so widths applied once survive. On Cocoa the flexible column keeps
absorbing slack on resize via FirstColumnOnly autoresizing; on WinForms a SizeChanged
handler recomputes it (installed once).

DPI / scaling: the fixed `widths` are **logical** pixels. On Cocoa they're used as-is
because AppKit geometry is in device-independent points (Retina + display scaling are
handled by the system). On WinForms the native ListView takes **physical** pixels, and
Toga is DPI-aware and scales the font up with DPI, so we multiply by the backend's
`dpi_scale` — otherwise the columns would be too narrow and clip the text at 125/150/
200% scaling. This keeps the layout correct regardless of resolution, DPI, and scaling.
"""

_WIN_HANDLERS = set()  # ListView ids with a SizeChanged handler already installed


def apply_column_widths(table, widths):
    """Apply fixed/flexible column widths natively. Returns True if applied."""
    impl = getattr(table, "_impl", None)
    if impl is None:
        return False
    # Cocoa: impl.columns is the NSTableColumn list; impl.native_table the NSTableView.
    if hasattr(impl, "columns") and hasattr(impl, "native_table"):
        return _apply_cocoa(impl, widths)
    # WinForms: impl.native is the ListView, with a .Columns collection.
    native = getattr(impl, "native", None)
    if native is not None and hasattr(native, "Columns"):
        return _apply_winforms(impl, native, widths)
    return False


def _flex_index(widths):
    for i, w in enumerate(widths):
        if w is None:
            return i
    return None


def describe_columns(table):
    """Return the *actual* native column state for diagnostics/verification:
    {backend, headings, widths, dpi_scale, client_width}. Widths are physical pixels
    (WinForms) or points (Cocoa). Used by the Windows DPI test harness. Returns None if
    the table isn't realized on a supported backend."""
    impl = getattr(table, "_impl", None)
    if impl is None:
        return None
    if hasattr(impl, "columns") and hasattr(impl, "native_table"):
        cols = impl.columns
        return {
            "backend": "cocoa",
            "headings": [str(c.headerCell.stringValue) for c in cols],
            "widths": [round(float(c.width)) for c in cols],
            "dpi_scale": 1.0,
            "client_width": round(float(impl.native_table.frame.size.width)),
        }
    native = getattr(impl, "native", None)
    if native is not None and hasattr(native, "Columns"):
        cols = native.Columns
        return {
            "backend": "winforms",
            "headings": [str(cols[i].Text) for i in range(cols.Count)],
            "widths": [int(cols[i].Width) for i in range(cols.Count)],
            "dpi_scale": float(getattr(impl, "dpi_scale", 1) or 1),
            "client_width": int(native.ClientSize.Width),
        }
    return None


# ---------------------------------------------------------------- macOS (Cocoa)
def _apply_cocoa(impl, widths):
    try:
        from toga_cocoa.libs import NSTableViewColumnAutoresizingStyle as Style
    except Exception:  # noqa: BLE001 — not macOS
        return False
    cols = impl.columns
    if len(cols) != len(widths):
        return False
    flex = _flex_index(widths)
    # Only the flexible column should absorb slack when the table resizes.
    if flex == 0:
        impl.native_table.columnAutoresizingStyle = Style.FirstColumnOnly
    elif flex == len(widths) - 1:
        impl.native_table.columnAutoresizingStyle = Style.LastColumnOnly
    else:
        impl.native_table.columnAutoresizingStyle = Style.NoAutoresizing
    for i, w in enumerate(widths):
        col = cols[i]
        if w is None:
            col.minWidth = 120
            col.maxWidth = 100000
        else:
            # Lock fixed columns so neither autoresize nor user-drag changes them.
            col.minWidth = w
            col.maxWidth = w
            col.width = w
    impl.native_table.sizeToFit()
    return True


# ------------------------------------------------------------- Windows (WinForms)
def _apply_winforms(impl, native, widths):
    columns = native.Columns
    if columns.Count != len(widths):
        return False
    flex = _flex_index(widths)

    def resize(*_):
        # Native ListView widths are physical pixels; convert our logical widths using
        # the DPI-aware backend scale so year columns don't clip at >100% scaling. Read
        # dpi_scale live here (not captured once) so moving the window between monitors
        # of different DPI — which also fires SizeChanged — rescales correctly.
        scale = getattr(impl, "dpi_scale", 1) or 1
        phys = [None if w is None else max(1, round(w * scale)) for w in widths]
        used = sum(w for w in phys if w is not None)
        min_flex = max(1, round(120 * scale))
        for i, w in enumerate(phys):
            if w is None:
                columns[i].Width = max(min_flex, native.ClientSize.Width - used)
            else:
                columns[i].Width = w

    resize()
    # Recompute the flexible column when the ListView is resized. Toga's own
    # _resize_columns only fires on insert/remove, so this won't fight it.
    if flex is not None and id(native) not in _WIN_HANDLERS:
        native.SizeChanged += resize
        _WIN_HANDLERS.add(id(native))
    return True
