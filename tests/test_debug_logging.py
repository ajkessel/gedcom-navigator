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


def test_debug_env_lookup_accepts_lowercase_name(monkeypatch, tmp_path):
    gedcom_debug = _reload_debug_module(monkeypatch, tmp_path, enabled=False)
    monkeypatch.setenv("gedcom_navigator_debug", "true")

    assert gedcom_debug.debug_enabled()


def test_debug_log_path_accepts_lowercase_name(monkeypatch, tmp_path):
    lower_log = tmp_path / "lowercase-debug.log"
    gedcom_debug = _reload_debug_module(monkeypatch, tmp_path, enabled=False)
    monkeypatch.delenv("GEDCOM_NAVIGATOR_DEBUG_LOG", raising=False)
    monkeypatch.setenv("gedcom_navigator_debug", "1")
    monkeypatch.setenv("gedcom_navigator_debug_log", str(lower_log))

    try:
        raise RuntimeError("lowercase diagnostic failure")
    except RuntimeError:
        gedcom_debug.log_exception("lowercase recovery path")

    log_text = lower_log.read_text(encoding="utf-8")
    assert "Recovered exception: lowercase recovery path" in log_text
    assert "RuntimeError: lowercase diagnostic failure" in log_text
