"""Tests for main-window keyboard shortcut registration."""

from gedcom_gui_appearance import AppearanceMixin
from gedcom_shortcuts import (
    keyboard_shortcut_rows,
    main_window_shortcuts,
    shortcut_by_action,
)
from gedcom_strings import get_keyboard_shortcut_rows


class _Bindable:
    def __init__(self):
        self.bindings = {}

    def bind(self, sequence, callback, *args, **kwargs):
        self.bindings[sequence] = (callback, args, kwargs)


class _Textbox(_Bindable):
    def configure(self, **_kwargs):
        pass


class _Results:
    def __init__(self):
        self._textbox = _Textbox()

    def yview_scroll(self, *_args):
        return None


class _Selector:
    _buttons_dict = {}

    def winfo_children(self):
        return []


class _Var:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _App(AppearanceMixin):
    def __init__(self):
        self.root = _Bindable()
        self.results = _Results()
        self._display_mode_selector = _Selector()
        self.tree = _Bindable()
        self.top_n_spin = _Bindable()
        self.max_depth_spin = _Bindable()
        self.set_home_btn = _Bindable()
        self.show_flagged_only = _Var()
        self.fuzzy_search = _Var()
        self.married_name_search = _Var()

    def _show_how_to_use(self):
        pass

    def _show_keyboard_shortcuts(self):
        pass

    def _show_preferences(self):
        pass

    def _kb_focus_search(self):
        pass

    def _kb_focus_filter(self):
        pass

    def _set_display_mode(self, *_args, **_kwargs):
        pass

    def _view_tags(self):
        pass

    def _browse(self):
        pass

    def _set_home_person(self):
        pass

    def _save_results(self):
        pass

    def _reverse_results(self):
        pass

    def _clear_results(self):
        pass

    def _navigate_back(self):
        pass

    def _navigate_forward(self):
        pass

    def _kb_copy(self, *_args):
        pass


def test_f3_opens_preferences_on_linux(monkeypatch):
    app = _App()

    monkeypatch.setattr("gedcom_gui_appearance.sys.platform", "linux")
    app._setup_keybindings()

    assert "<F3>" in app.root.bindings


def test_f3_is_not_bound_on_macos(monkeypatch):
    app = _App()

    monkeypatch.setattr("gedcom_gui_appearance.sys.platform", "darwin")
    app._setup_keybindings()

    assert "<F3>" not in app.root.bindings


def test_main_window_shortcuts_have_no_platform_conflicts():
    for platform in ("linux", "win32", "darwin"):
        shortcuts = [
            shortcut for shortcut in main_window_shortcuts(platform)
            if shortcut.sequence is not None
        ]
        by_sequence = {}
        for shortcut in shortcuts:
            existing = by_sequence.setdefault(shortcut.sequence, shortcut.action_key)
            assert existing == shortcut.action_key, (
                platform, shortcut.sequence, existing, shortcut.action_key)


def test_keybinding_registration_matches_shortcut_metadata(monkeypatch):
    for platform in ("linux", "win32", "darwin"):
        monkeypatch.setattr("gedcom_gui_appearance.sys.platform", platform)
        app = _App()

        app._setup_keybindings()

        expected = {
            shortcut.sequence
            for shortcut in main_window_shortcuts(platform)
            if shortcut.sequence is not None
        }
        assert expected.issubset(set(app.root.bindings))


def test_copy_shortcut_uses_platform_specific_modifier():
    assert shortcut_by_action("copy_results", "linux").sequence == "<Control-c>"
    assert shortcut_by_action("copy_results", "win32").sequence == "<Control-c>"
    assert shortcut_by_action("copy_results", "darwin").sequence == "<Command-c>"


def test_keyboard_shortcut_rows_match_metadata(monkeypatch):
    for platform in ("linux", "win32", "darwin"):
        monkeypatch.setattr("gedcom_strings.sys.platform", platform)
        expected = [shortcut.display for shortcut in keyboard_shortcut_rows(platform)]

        rows = get_keyboard_shortcut_rows()

        assert [shortcut for shortcut, _action in rows] == expected
