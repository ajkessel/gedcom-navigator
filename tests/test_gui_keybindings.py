"""Tests for main-window keyboard shortcut registration."""

import inspect
import pathlib

import gedcom_strings as _gs
from gedcom_gui_appearance import AppearanceMixin
from gedcom_shortcuts import (
    keyboard_shortcut_rows,
    main_window_shortcuts,
    shortcut_by_action,
)
from gedcom_strings import get_keyboard_shortcut_rows

_DOCS_ROOT = pathlib.Path(__file__).parent.parent / "docs"

# Shortcuts that legitimately have no UI button with a tooltip:
# help/keyboard_shortcuts/preferences → F-key only, no button
# open_gedcom → accessible via File menu, no dedicated toolbar button
# back/forward → keyboard-only navigation; no button in the toolbar
# zoom_in_out/zoom_reset → global modifier shortcuts; no dedicated button
_NO_BUTTON_TOOLTIP_ACTIONS = frozenset({
    "help",
    "keyboard_shortcuts",
    "preferences",
    "open_gedcom",
    "back",
    "forward",
    "zoom_in_out",
    "zoom_reset",
})


def _all_tip_text():
    """Return joined output of every get_tip_* function in gedcom_strings."""
    return "\n".join(
        fn()
        for name, fn in inspect.getmembers(_gs)
        if name.startswith("get_tip_") and callable(fn)
    )


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

    def _show_current_profile_gallery(self):
        pass

    def _save_results(self):
        pass

    def _reverse_results(self):
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


def test_removed_result_reset_shortcuts_are_not_registered():
    removed_action_keys = {"clear" + "_results", "close_or" + "_clear"}
    for platform in ("linux", "win32", "darwin"):
        shortcuts = main_window_shortcuts(platform)
        assert all(shortcut.action_key not in removed_action_keys
                   for shortcut in shortcuts)
        assert all(shortcut.key not in removed_action_keys for shortcut in shortcuts)
        assert all(shortcut.sequence != "<Escape>" for shortcut in shortcuts)


def test_keyboard_shortcut_rows_match_metadata(monkeypatch):
    for platform in ("linux", "win32", "darwin"):
        monkeypatch.setattr("gedcom_strings.sys.platform", platform)
        expected = [shortcut.display for shortcut in keyboard_shortcut_rows(platform)]

        rows = get_keyboard_shortcut_rows()

        assert [shortcut for shortcut, _action in rows] == expected


# ---------------------------------------------------------------------------
# OS-reserved shortcut conflict tests
# ---------------------------------------------------------------------------

# macOS intercepts these sequences at the window-server level before Tkinter
# sees the event, making them impossible to override in a Tkinter app.
_MACOS_SYSTEM_SEQUENCES = frozenset({
    "<Command-h>",  # Hide application
    "<Command-m>",  # Minimize window to Dock
    "<Command-q>",  # Quit application
    "<Command-w>",  # Close window
})

# Windows OS-level shortcuts that are consumed before reaching the app.
_WINDOWS_SYSTEM_SEQUENCES = frozenset({
    "<Alt-F4>",          # Close window
    "<Control-Escape>",  # Open Start menu
})


def test_no_macos_system_shortcut_conflicts():
    """No app shortcut may use a sequence that macOS intercepts system-wide."""
    conflicts = [
        shortcut
        for shortcut in main_window_shortcuts("darwin")
        if shortcut.sequence in _MACOS_SYSTEM_SEQUENCES
    ]
    assert not conflicts, (
        "App shortcuts conflict with macOS system sequences: "
        + ", ".join(f"{s.action_key!r} -> {s.sequence!r}" for s in conflicts)
    )


def test_no_windows_system_shortcut_conflicts():
    """No app shortcut may use a sequence Windows consumes before the app."""
    conflicts = [
        shortcut
        for shortcut in main_window_shortcuts("win32")
        if shortcut.sequence in _WINDOWS_SYSTEM_SEQUENCES
    ]
    assert not conflicts, (
        "App shortcuts conflict with Windows system sequences: "
        + ", ".join(f"{s.action_key!r} -> {s.sequence!r}" for s in conflicts)
    )


def test_macos_cmd_h_and_cmd_m_use_shift():
    """set_home and toggle_married_name_search must use Shift on macOS.

    Cmd+H (hide app) and Cmd+M (minimize) are intercepted by macOS before
    Tkinter sees them, so these actions require Cmd+Shift on macOS.
    """
    set_home = shortcut_by_action("set_home", "darwin")
    assert set_home.sequence == "<Command-Shift-H>", (
        f"set_home uses macOS-reserved <Command-h>; expected <Command-Shift-H>, "
        f"got {set_home.sequence!r}"
    )

    married = shortcut_by_action("toggle_married_name_search", "darwin")
    assert married.sequence == "<Command-Shift-M>", (
        f"toggle_married_name_search uses macOS-reserved <Command-m>; "
        f"expected <Command-Shift-M>, got {married.sequence!r}"
    )


def test_windows_linux_use_standard_ctrl_for_h_and_m():
    """On Windows and Linux, H and M keep the standard Ctrl+ modifier."""
    for platform in ("linux", "win32"):
        set_home = shortcut_by_action("set_home", platform)
        assert set_home.sequence == "<Control-h>", (
            f"set_home on {platform}: expected <Control-h>, got {set_home.sequence!r}"
        )
        married = shortcut_by_action("toggle_married_name_search", platform)
        assert married.sequence == "<Control-m>", (
            f"toggle_married_name_search on {platform}: expected <Control-m>, "
            f"got {married.sequence!r}"
        )


# ---------------------------------------------------------------------------
# Coverage tests: tooltip text, KEYBOARD_SHORTCUTS.md, in-app help dialog
# ---------------------------------------------------------------------------

def test_every_button_shortcut_has_tooltip_mentioning_it(monkeypatch):
    """Every shortcut bound to a UI button must appear in at least one tooltip string.

    Shortcuts in _NO_BUTTON_TOOLTIP_ACTIONS are exempt because they are
    keyboard-only (F-keys, zoom), menu-only (Open), or navigation-only
    (Back/Forward) with no labeled toolbar button.
    """
    for platform in ("linux", "darwin"):
        monkeypatch.setattr("gedcom_strings.sys.platform", platform)
        monkeypatch.setattr("gedcom_shortcuts.sys.platform", platform)
        all_tips = _all_tip_text()
        missing = [
            f"  {s.display!r} (action={s.action_key!r})"
            for s in keyboard_shortcut_rows(platform)
            if (s.sequence is not None
                and s.action_key not in _NO_BUTTON_TOOLTIP_ACTIONS
                and s.display not in all_tips)
        ]
        assert not missing, (
            f"Shortcuts on {platform!r} with no tooltip text that mentions them:\n"
            + "\n".join(missing)
        )


def test_every_shortcut_in_keyboard_shortcuts_md():
    """Every Linux/Windows shortcut must be listed in docs/KEYBOARD_SHORTCUTS.md.

    The doc uses Ctrl+ notation (Linux/Windows) throughout.  On macOS,
    ⌘ replaces Ctrl+ for most shortcuts — that replacement is implied by
    convention and not verified here.  The exception is shortcuts that use a
    non-obvious macOS key combination (⌘⇧M, ⌘⇧H), which are explicitly
    called out in the doc and must stay there.
    """
    content = (_DOCS_ROOT / "KEYBOARD_SHORTCUTS.md").read_text(encoding="utf-8")

    # Check Linux/Windows display strings.
    missing = [
        f"  {s.display!r} (action={s.action_key!r})"
        for s in keyboard_shortcut_rows("linux")
        if s.sequence is not None and s.display not in content
    ]
    assert not missing, (
        "Shortcuts missing from docs/KEYBOARD_SHORTCUTS.md:\n" + "\n".join(missing)
    )

    # Verify macOS shortcuts that deviate from the standard ⌘+letter pattern
    # are still explicitly present.  Standard conversions (Ctrl+F → ⌘F, etc.)
    # are not checked because the doc doesn't list them individually.
    linux_by_action = {s.action_key: s.display for s in keyboard_shortcut_rows("linux")}
    macos_missing = []
    for s in keyboard_shortcut_rows("darwin"):
        if s.sequence is None:
            continue
        # Keyboard-only / menu-only shortcuts whose macOS form differs from the
        # Linux F-key or Alt+* form need not be listed explicitly in the doc
        # (their Linux equivalents are already there).
        if s.action_key in _NO_BUTTON_TOOLTIP_ACTIONS:
            continue
        linux_display = linux_by_action.get(s.action_key, "")
        # Build the "trivially converted" macOS display: drop "Ctrl+" and prepend "⌘".
        trivial_mac = (
            "⌘" + linux_display[len("Ctrl+"):]
            if linux_display.startswith("Ctrl+")
            else ""
        )
        if s.display == trivial_mac:
            continue  # implied by doc convention — no explicit entry required
        if s.display not in content:
            macos_missing.append(f"  {s.display!r} (action={s.action_key!r}, macOS)")
    assert not macos_missing, (
        "Non-standard macOS shortcuts missing from docs/KEYBOARD_SHORTCUTS.md:\n"
        + "\n".join(macos_missing)
    )


def test_every_shortcut_in_app_help_rows(monkeypatch):
    """Every registered shortcut must appear in the in-app keyboard help dialog."""
    for platform in ("linux", "darwin"):
        monkeypatch.setattr("gedcom_strings.sys.platform", platform)
        rows_displayed = {key for key, _ in get_keyboard_shortcut_rows()}
        missing = [
            f"  {s.display!r} (action={s.action_key!r})"
            for s in keyboard_shortcut_rows(platform)
            if s.display not in rows_displayed
        ]
        assert not missing, (
            f"Shortcuts on {platform!r} missing from in-app keyboard help dialog:\n"
            + "\n".join(missing)
        )
