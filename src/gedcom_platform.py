#!/usr/bin/env python3
"""
gedcom_platform.py

Small platform integration hooks that do not belong in persistence helpers.
"""

import sys

from gedcom_debug import log_exception


def filedialog_parent(window):
    """Return the parent kwarg value for tkinter filedialog calls.

    On macOS, Tk passes parent= as a sheet host to NSWindow _beginSheet.
    In compiled (PyInstaller) apps the window state is not suitable for
    hosting sheets and AppKit aborts.  Returning None makes the dialog
    appear as a standalone window, which is safe on all platforms.
    """
    if sys.platform == 'darwin':
        return None
    return window


def copy_text_to_clipboard(widget, text):
    """Place ``text`` on the system clipboard.

    On macOS, Tk's clipboard uses a lazy pasteboard-owner mechanism that does
    not reliably reach NSPasteboard in sandboxed (Mac App Store) builds, so the
    copy silently does nothing.  Write straight to NSPasteboard via PyObjC there
    and fall back to Tk's clipboard if PyObjC is unavailable or fails.  Other
    platforms use Tk's clipboard directly.
    """
    if sys.platform == 'darwin':
        try:
            from AppKit import (  # pylint: disable=import-outside-toplevel
                NSPasteboard,
                NSPasteboardTypeString,
            )

            pasteboard = NSPasteboard.generalPasteboard()
            pasteboard.clearContents()
            if pasteboard.setString_forType_(text, NSPasteboardTypeString):
                return
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception("copying text to the macOS pasteboard")
    widget.clipboard_clear()
    widget.clipboard_append(text)


def configure_process_identity():
    """Apply process-level desktop identity settings when supported."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes  # pylint: disable=import-outside-toplevel

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.ajkessel.gedcom-navigator")
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("configuring Windows app user model ID")
        pass
