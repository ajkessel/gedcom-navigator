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
        return _apply_winforms(native, widths)
    return False


def _flex_index(widths):
    for i, w in enumerate(widths):
        if w is None:
            return i
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
def _apply_winforms(native, widths):
    columns = native.Columns
    if columns.Count != len(widths):
        return False
    flex = _flex_index(widths)

    def resize(*_):
        used = sum(w for w in widths if w is not None)
        for i, w in enumerate(widths):
            if w is None:
                columns[i].Width = max(120, native.ClientSize.Width - used)
            else:
                columns[i].Width = w

    resize()
    # Recompute the flexible column when the ListView is resized. Toga's own
    # _resize_columns only fires on insert/remove, so this won't fight it.
    if flex is not None and id(native) not in _WIN_HANDLERS:
        native.SizeChanged += resize
        _WIN_HANDLERS.add(id(native))
    return True
