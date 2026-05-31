"""Tests for scaled_tag_font, which keeps CTkTextbox tag fonts (set directly on
the inner tk.Text, bypassing CTk's widget scaling) in step with the scaled base
font at high DPI."""

import customtkinter as ctk
import pytest

from gedcom_zoom import scaled_tag_font


@pytest.fixture
def _scaling(monkeypatch):
    """Return a setter that fakes CTk's widget scaling factor."""
    def _set(value):
        monkeypatch.setattr(
            ctk.ScalingTracker, "get_widget_scaling",
            staticmethod(lambda _widget: value))
    return _set


def test_no_weight_returns_two_tuple(_scaling):
    _scaling(1.0)
    assert scaled_tag_font(object(), "Consolas", 13) == ("Consolas", 13)


def test_weight_returns_three_tuple(_scaling):
    _scaling(1.0)
    assert scaled_tag_font(object(), "Consolas", 13, weight="bold") == (
        "Consolas", 13, "bold")


@pytest.mark.parametrize("scale, size, expected", [
    (1.0, 13, 13),    # 100% — no-op (macOS / Linux / Windows 100%)
    (3.0, 14, 42),    # 300% — the reported Matches/bold bug
    (2.0, 13, 26),    # 200%
    (1.5, 14, 21),    # 150%
])
def test_size_scaled_by_widget_scaling(_scaling, scale, size, expected):
    _scaling(scale)
    assert scaled_tag_font(object(), "Consolas", size, weight="bold") == (
        "Consolas", expected, "bold")


def test_size_never_below_one(_scaling):
    _scaling(0.0)
    _family, size, _weight = scaled_tag_font(
        object(), "Consolas", 13, weight="bold")
    assert size >= 1


def test_falls_back_to_unscaled_on_error(monkeypatch):
    def _boom(_widget):
        raise RuntimeError("no scaling tracker")
    monkeypatch.setattr(
        ctk.ScalingTracker, "get_widget_scaling", staticmethod(_boom))
    # On error the helper must not raise and must leave the size unscaled.
    assert scaled_tag_font(object(), "Consolas", 13) == ("Consolas", 13)
