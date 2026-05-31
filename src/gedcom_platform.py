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
