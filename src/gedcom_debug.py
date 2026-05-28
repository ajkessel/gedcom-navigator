#!/usr/bin/env python3
"""
gedcom_debug.py

Debug-only exception logging and process-wide exception hooks.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

_DEBUG_ENV = "GEDCOM_NAVIGATOR_DEBUG"
_LOG_PATH_ENV = "GEDCOM_NAVIGATOR_DEBUG_LOG"
_LOGGER_NAME = "gedcom_navigator"
_MAX_LOG_BYTES = 1_000_000
_BACKUP_COUNT = 3

_configured_path = None
_app_version_string = None
_previous_sys_excepthook = None
_previous_threading_excepthook = None
_previous_tk_report_callback_exception = None
_logged_exception_keys = set()


def _getenv(name, default=None):
    """Return an environment value using case-insensitive lookup on all platforms."""
    value = os.environ.get(name)
    if value is not None:
        return value
    name_upper = name.upper()
    for key, candidate in os.environ.items():
        if key.upper() == name_upper:
            return candidate
    return default


def debug_enabled():
    """Return whether debug diagnostics are enabled for this process."""
    return _getenv(_DEBUG_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def set_debug_enabled(enabled=True):
    """Set or clear the environment flag used by all debug-only helpers."""
    if enabled:
        os.environ[_DEBUG_ENV] = "1"
    else:
        os.environ.pop(_DEBUG_ENV, None)


def _default_debug_log_path():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "gedcom-navigator" / "debug.log"


def debug_log_path():
    """Return the configured debug log path."""
    override = _getenv(_LOG_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return _default_debug_log_path()


def get_debug_logger():
    """Return the application debug logger."""
    return logging.getLogger(_LOGGER_NAME)


def configure_debug_logging(*, enabled=None):
    """Configure rotating file logging when debug mode is enabled."""
    global _configured_path

    if enabled is not None:
        set_debug_enabled(enabled)
    if not debug_enabled():
        return None

    logger = get_debug_logger()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if _configured_path is not None:
        return _configured_path

    path = debug_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        fallback_dir = Path(tempfile.gettempdir())
        path = fallback_dir / "gedcom-navigator-debug.log"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )

    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
        )
    )
    logger.addHandler(handler)
    _configured_path = path
    logger.debug(
        "Debug logging enabled: executable=%r argv=%r log_path=%s",
        sys.executable,
        sys.argv,
        path,
    )
    return path


def log_debug(message, *args, **kwargs):
    """Write a debug message if diagnostics are enabled."""
    if not debug_enabled():
        return
    configure_debug_logging()
    get_debug_logger().debug(message, *args, **kwargs)


def log_exception(context):
    """Log the active exception if diagnostics are enabled."""
    if not debug_enabled():
        return
    configure_debug_logging()
    get_debug_logger().debug("Recovered exception: %s", context, exc_info=True)


def log_exception_once(key, context):
    """Log the active exception once per key if diagnostics are enabled."""
    if key in _logged_exception_keys:
        return
    _logged_exception_keys.add(key)
    log_exception(context)


def _log_unhandled_exception(context, exc_info):
    configure_debug_logging()
    get_debug_logger().critical(context, exc_info=exc_info)


def _read_version():
    try:
        from gedcom_navigator import __version__

        return __version__
    except ImportError:
        pass
    try:
        init_path = Path(__file__).parent.parent / "gedcom_navigator" / "__init__.py"
        for line in init_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                return line.split("=", 1)[1].strip().strip("\"'")
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def app_version_string():
    """Return a version string combining release version and git commit hash.

    Format: "1.9.6 (76297af)" in development, or "1.9.6" if git is unavailable
    (e.g. in frozen PyInstaller builds).

    The result is memoized so the underlying ``git`` subprocess runs at most
    once per process. This is intended to be called only in debug mode, since
    spawning ``git`` is expensive (and, in a windowed PyInstaller build on
    Windows, briefly flashes a console window) per call.
    """
    global _app_version_string
    if _app_version_string is not None:
        return _app_version_string

    __version__ = _read_version() + f" ({sys.platform})"
    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            .decode()
            .strip()
        )
        if commit:
            __version__ = f"{__version__} ({commit})"
    except Exception:  # noqa: BLE001
        pass
    _app_version_string = __version__
    return __version__


def install_exception_hooks(root=None):
    """Install process-wide debug hooks for uncaught exceptions."""
    global _previous_sys_excepthook
    global _previous_threading_excepthook
    global _previous_tk_report_callback_exception

    if not debug_enabled():
        return
    configure_debug_logging()

    if _previous_sys_excepthook is None:
        _previous_sys_excepthook = sys.excepthook

        def _sys_excepthook(exc_type, exc_value, traceback):
            _log_unhandled_exception(
                "Unhandled main-thread exception",
                (exc_type, exc_value, traceback),
            )
            _previous_sys_excepthook(exc_type, exc_value, traceback)

        sys.excepthook = _sys_excepthook

    if _previous_threading_excepthook is None and hasattr(threading, "excepthook"):
        _previous_threading_excepthook = threading.excepthook

        def _threading_excepthook(args):
            _log_unhandled_exception(
                f"Unhandled thread exception in {args.thread!r}",
                (args.exc_type, args.exc_value, args.exc_traceback),
            )
            _previous_threading_excepthook(args)

        threading.excepthook = _threading_excepthook

    if root is not None and _previous_tk_report_callback_exception is None:
        _previous_tk_report_callback_exception = root.report_callback_exception

        def _report_callback_exception(exc_type, exc_value, traceback):
            _log_unhandled_exception(
                "Unhandled Tk callback exception",
                (exc_type, exc_value, traceback),
            )
            _previous_tk_report_callback_exception(exc_type, exc_value, traceback)

        root.report_callback_exception = _report_callback_exception
