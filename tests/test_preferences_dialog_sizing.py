"""Tests for Preferences dialog sizing helpers."""

from gedcom_gui_dialogs import DialogsMixin


class _RequestedHeight:
    def __init__(self, height):
        self._height = height

    def winfo_reqheight(self):
        return self._height


class _WindowWidth:
    def __init__(self, width, geometry):
        self._width = width
        self._geometry = geometry

    def winfo_width(self):
        return self._width

    def geometry(self):
        return self._geometry


def test_preferences_dialog_target_height_uses_content_when_under_screen_cap():
    assert DialogsMixin._preferences_dialog_target_height(
        _RequestedHeight(360),
        _RequestedHeight(42),
        900,
    ) == 450


def test_preferences_dialog_target_height_clamps_to_screen():
    assert DialogsMixin._preferences_dialog_target_height(
        _RequestedHeight(900),
        _RequestedHeight(80),
        700,
    ) == 630


def test_preferences_dialog_width_falls_back_to_geometry_during_early_layout():
    assert DialogsMixin._preferences_dialog_width(
        _WindowWidth(1, "640x420+10+20")
    ) == DialogsMixin._PREFS_MIN_WIDTH


def test_preferences_dialog_width_keeps_minimum_for_invalid_early_geometry():
    assert DialogsMixin._preferences_dialog_width(
        _WindowWidth(1, "bad-geometry")
    ) == DialogsMixin._PREFS_MIN_WIDTH


def test_preferences_dialog_uses_wider_professional_layout():
    assert DialogsMixin._PREFS_MIN_WIDTH == 650
    assert DialogsMixin._PREFS_LABEL_WIDTH == 145
