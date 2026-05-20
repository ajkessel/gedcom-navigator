#!/usr/bin/env python3
"""
gedcom_platform.py

Small platform integration hooks that do not belong in persistence helpers.
"""

import sys


def configure_process_identity():
    """Apply process-level desktop identity settings when supported."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes  # pylint: disable=import-outside-toplevel

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.ajkessel.gedcom-navigator")
    except Exception:  # pylint: disable=broad-exception-caught
        pass
