"""Tests for debug-only diagnostics logging."""

import importlib
import logging


def _reload_debug_module(monkeypatch, tmp_path, *, enabled):
    monkeypatch.setenv(
        "GEDCOM_NAVIGATOR_DEBUG_LOG",
        str(tmp_path / "gedcom-debug.log"),
    )
    if enabled:
        monkeypatch.setenv("GEDCOM_NAVIGATOR_DEBUG", "1")
    else:
        monkeypatch.delenv("GEDCOM_NAVIGATOR_DEBUG", raising=False)

    logger = logging.getLogger("gedcom_navigator")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    import gedcom_debug

    return importlib.reload(gedcom_debug)


def test_debug_logging_disabled_is_inert(monkeypatch, tmp_path):
    gedcom_debug = _reload_debug_module(monkeypatch, tmp_path, enabled=False)

    assert gedcom_debug.configure_debug_logging() is None
    assert not (tmp_path / "gedcom-debug.log").exists()


def test_log_exception_writes_recovered_traceback(monkeypatch, tmp_path):
    gedcom_debug = _reload_debug_module(monkeypatch, tmp_path, enabled=True)

    try:
        raise RuntimeError("diagnostic failure")
    except RuntimeError:
        gedcom_debug.log_exception("test recovery path")

    log_text = (tmp_path / "gedcom-debug.log").read_text(encoding="utf-8")
    assert "Recovered exception: test recovery path" in log_text
    assert "RuntimeError: diagnostic failure" in log_text
