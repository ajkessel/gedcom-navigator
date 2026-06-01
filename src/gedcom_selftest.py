#!/usr/bin/env python3
"""
gedcom_selftest.py

Headless runtime self-test for the packaged app.  Exercises the native code
paths that the App Sandbox can break but unsandboxed unit tests cannot see --
chiefly Pillow's `_imaging` extension (and its transitive dylibs such as
libxcb -> libXau) and the macOS pasteboard bridge.

Run via ``gedcom-navigator --self-test``.  The build pipeline launches the
*signed, sandboxed* bundle with this flag and treats a non-zero exit as a
build failure, so a mislinked dylib cannot ship unnoticed.
"""

import sys


def _check_pillow_import():
    """Import Pillow's native extension; surfaces dylib load failures."""
    from PIL import Image, ImageDraw  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import


def _check_canvas_png():
    """Render a Tk canvas to PNG, the exact path graph copy/save uses."""
    import tkinter as tk  # pylint: disable=import-outside-toplevel

    from gedcom_graph_export import canvas_to_png_bytes  # pylint: disable=import-outside-toplevel

    root = tk.Tk()
    try:
        root.withdraw()
        canvas = tk.Canvas(root, width=120, height=80, bg='white')
        canvas.create_rectangle(10, 10, 110, 70, fill='#d9ecff', outline='black')
        canvas.create_line(10, 10, 110, 70, fill='black', width=2)
        canvas.create_text(60, 40, text='Self Test', fill='black')
        canvas.update_idletasks()
        png = canvas_to_png_bytes(canvas, 120, 80)
        if not png or not png.startswith(b'\x89PNG'):
            raise RuntimeError("canvas_to_png_bytes did not return PNG data")
    finally:
        root.destroy()


def _check_macos_pasteboard():
    """Verify the NSPasteboard text bridge loads on macOS (no PyObjC -> skip)."""
    if sys.platform != 'darwin':
        return
    try:
        from AppKit import NSPasteboard  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        # pbcopy fallback covers this; not a hard failure.
        print("  note: PyObjC/AppKit unavailable; relying on pbcopy fallback")


_CHECKS = (
    ("import Pillow native extension", _check_pillow_import),
    ("render canvas to PNG", _check_canvas_png),
    ("load macOS pasteboard bridge", _check_macos_pasteboard),
)


def run_self_test():
    """Run all checks; return 0 on success, 1 on the first failure."""
    failures = 0
    for label, check in _CHECKS:
        try:
            check()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            failures += 1
            print(f"FAIL: {label}: {exc!r}", file=sys.stderr)
        else:
            print(f"ok: {label}")
    if failures:
        print(f"self-test FAILED ({failures} check(s))", file=sys.stderr)
        return 1
    print("self-test PASSED")
    return 0
