"""Tests for the Windows DPI scaling patch in gedcom_navigator_gui."""

import types

import customtkinter as ctk
import pytest

from gedcom_navigator_gui import _patch_ctk_scaling_for_tkinter_dpi


@pytest.fixture(autouse=True)
def _restore_scaling_tracker():
    """Restore get_window_dpi_scaling after each test."""
    original = ctk.ScalingTracker.__dict__.get('get_window_dpi_scaling')
    yield
    if original is not None:
        ctk.ScalingTracker.get_window_dpi_scaling = original


def _mock_window(fpixels: float):
    """Minimal window stub whose winfo_fpixels returns a fixed DPI value."""
    win = types.SimpleNamespace()
    win.winfo_fpixels = lambda _spec: fpixels
    return win


def test_patch_replaces_get_window_dpi_scaling():
    original = ctk.ScalingTracker.get_window_dpi_scaling
    _patch_ctk_scaling_for_tkinter_dpi()
    assert ctk.ScalingTracker.get_window_dpi_scaling is not original


@pytest.mark.parametrize("dpi, expected", [
    (96.0,  1.0),    # 100% scaling, virtualized — the bug this patch fixes
    (120.0, 1.25),   # 125% scaling
    (144.0, 1.5),    # 150% scaling
    (168.0, 1.75),   # 175% scaling
    (192.0, 2.0),    # 200% scaling
])
def test_patch_scale_from_winfo_fpixels(dpi, expected):
    _patch_ctk_scaling_for_tkinter_dpi()
    result = ctk.ScalingTracker.get_window_dpi_scaling(_mock_window(dpi))
    assert result == pytest.approx(expected, abs=0.01)


def test_patch_clamps_minimum():
    _patch_ctk_scaling_for_tkinter_dpi()
    assert ctk.ScalingTracker.get_window_dpi_scaling(_mock_window(1.0)) == 0.75


def test_patch_clamps_maximum():
    _patch_ctk_scaling_for_tkinter_dpi()
    assert ctk.ScalingTracker.get_window_dpi_scaling(_mock_window(10000.0)) == 3.0


def test_patch_fallback_does_not_raise_when_winfo_fpixels_unavailable():
    """When the window object has no winfo_fpixels, the patched function must
    not raise — it falls back to the original method or returns 1.0."""
    _patch_ctk_scaling_for_tkinter_dpi()

    class BadWindow:
        def winfo_fpixels(self, _spec):
            raise RuntimeError("no display")

    result = ctk.ScalingTracker.get_window_dpi_scaling(BadWindow())
    assert isinstance(result, float)
    assert 0.75 <= result <= 3.0


def test_patch_is_idempotent():
    """Calling the patch twice should not break the scaling logic."""
    _patch_ctk_scaling_for_tkinter_dpi()
    _patch_ctk_scaling_for_tkinter_dpi()
    result = ctk.ScalingTracker.get_window_dpi_scaling(_mock_window(96.0))
    assert result == pytest.approx(1.0, abs=0.01)
