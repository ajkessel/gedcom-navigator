"""Opt-in smoke tests that instantiate the real Tk GUI."""

import os
import time
import tkinter as tk
from pathlib import Path

import pytest

from gedcom_config import ConfigManager
from gedcom_tooltip import Tooltip


GUI_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Alice /Smith/
1 SEX F
1 BIRT
2 DATE 1975
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 BIRT
2 DATE 1970
1 FAMS @F1@
0 @I3@ INDI
1 NAME Carol /Smith/
1 SEX F
1 FAMC @F1@
1 _MTTAG @T1@
0 @T1@ _MTTAG
1 NAME DNA Test Tag
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 CHIL @I3@
0 TRLR
"""


def _artifact_dir():
    return Path(os.environ.get(
        "GEDCOM_NAVIGATOR_TEST_ARTIFACTS",
        "test-artifacts/gui-smoke",
    ))


def _write_artifact(name, content):
    path = _artifact_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _widget_dump(widget, depth=0):
    try:
        label = widget.cget("text")
    except Exception:  # pylint: disable=broad-exception-caught
        label = ""
    line = (
        f"{'  ' * depth}{widget.winfo_class()} "
        f"{widget.__class__.__name__} text={label!r}"
    )
    lines = [line]
    for child in widget.winfo_children():
        lines.extend(_widget_dump(child, depth + 1))
    return lines


def _pump_until(root, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            root.update()
            if predicate():
                return
        except tk.TclError as exc:
            last_error = exc
        time.sleep(0.02)
    if last_error is not None:
        raise AssertionError(f"GUI event loop failed: {last_error}") from last_error
    raise AssertionError("Timed out waiting for GUI condition")


def _mainloop_until(root, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    timed_out = {"value": False}

    def poll():
        if predicate():
            root.quit()
            return
        if time.monotonic() >= deadline:
            timed_out["value"] = True
            root.quit()
            return
        root.after(20, poll)

    root.after(20, poll)
    root.mainloop()
    if timed_out["value"]:
        raise AssertionError("Timed out waiting for GUI condition")


def _destroy_window(win):
    try:
        win.grab_release()
    except tk.TclError:
        pass
    win.destroy()


@pytest.fixture
def gui_app(tmp_path, monkeypatch):
    ctk = pytest.importorskip("customtkinter")
    settings_path = tmp_path / "config" / "settings.json"
    monkeypatch.setattr(
        ConfigManager, "default_path", staticmethod(lambda: settings_path))

    try:
        root = ctk.CTk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display is not available: {exc}")

    root.withdraw()
    try:
        from gedcom_navigator_gui import GedcomNavigatorApp

        app = GedcomNavigatorApp(root)
        yield app
    except Exception:
        try:
            _write_artifact("widget-dump.txt", "\n".join(_widget_dump(root)))
        finally:
            raise
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


@pytest.mark.gui
def test_main_window_loads_fixture_and_exercises_core_views(gui_app, tmp_path):
    ged_path = tmp_path / "gui-smoke.ged"
    ged_path.write_text(GUI_GED, encoding="utf-8")
    app = gui_app
    root = app.root

    app.gedcom_path.set(str(ged_path))
    app._load_file()
    _mainloop_until(root, lambda: not app._busy and len(app.individuals) == 3)

    assert app.tree.get_children()
    assert app.status_text.get()
    assert app._select_person_in_main_tree("@I1@")

    app._set_display_mode("profile")
    _pump_until(root, lambda: app.display_mode.get() == "profile")
    app._set_display_mode("matches")
    _pump_until(root, lambda: app.display_mode.get() == "matches")
    app._set_display_mode("paths", refresh=False)
    _pump_until(root, lambda: app.display_mode.get() == "paths")

    before = set(root.winfo_children())
    app._show_keyboard_shortcuts()
    _pump_until(root, lambda: len(set(root.winfo_children()) - before) >= 1)
    shortcut_win = list(set(root.winfo_children()) - before)[0]
    _destroy_window(shortcut_win)
    _pump_until(root, lambda: not shortcut_win.winfo_exists())

    before = set(root.winfo_children())
    app._show_preferences()
    _pump_until(root, lambda: len(set(root.winfo_children()) - before) >= 1)
    prefs_win = list(set(root.winfo_children()) - before)[0]
    _destroy_window(prefs_win)
    _pump_until(root, lambda: not prefs_win.winfo_exists())

    app._set_display_mode("profile")
    app._show_person()
    _pump_until(root, lambda: getattr(app, "_secondary_win", None) is not None)
    _destroy_window(app._secondary_win)
    app._secondary_win = None
    _pump_until(root, lambda: getattr(app, "_secondary_win", None) is None)


@pytest.mark.gui
def test_tree_view_opens_when_zoomed_attribute_raises(gui_app, tmp_path, monkeypatch):
    """Tree view must not crash when win.attributes('-zoomed', True) raises TclError.

    Regression: -zoomed is invalid on macOS Aqua Tk. The maximize path must
    fall back to geometry() instead of propagating the error.
    """
    ged_path = tmp_path / "tree.ged"
    ged_path.write_text(GUI_GED, encoding="utf-8")
    app = gui_app
    app.gedcom_path.set(str(ged_path))
    app._load_file()
    _mainloop_until(app.root, lambda: not app._busy)

    # Shrink the apparent screen so _twants_max becomes True even for a tiny tree.
    monkeypatch.setattr(app.root, "winfo_screenwidth", lambda: 100)
    monkeypatch.setattr(app.root, "winfo_screenheight", lambda: 100)

    # Simulate macOS Aqua Tk: any attempt to read or set -zoomed raises TclError.
    original = tk.Wm.wm_attributes

    def _no_zoomed(self, *args, **kw):
        if args and args[0] == "-zoomed":
            raise tk.TclError('bad attribute "-zoomed"')
        return original(self, *args, **kw)

    monkeypatch.setattr(tk.Wm, "wm_attributes", _no_zoomed)

    app._show_person_for("@I1@", initial_view="tree")
    _pump_until(app.root, lambda: getattr(app, "_secondary_win", None) is not None)

    win = app._secondary_win
    assert win.winfo_exists()
    assert win.winfo_width() > 0


def _pump(root, seconds):
    """Pump the event loop for a fixed duration (non-raising)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            root.update()
        except tk.TclError:
            pass
        time.sleep(0.02)


def _pump_while(root, predicate, timeout=20.0):
    """Pump the event loop while ``predicate`` stays true, up to ``timeout``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and predicate():
        try:
            root.update()
        except tk.TclError:
            pass
        time.sleep(0.02)


def _find_widgets(root, kind, text=None):
    found = []

    def visit(widget):
        try:
            matches_text = text is None or widget.cget("text") == text
        except Exception:  # pylint: disable=broad-exception-caught
            matches_text = False
        if isinstance(widget, kind) and matches_text:
            found.append(widget)
        for child in widget.winfo_children():
            visit(child)

    visit(root)
    return found


def _drive_walkthrough_to_end(app, root, timeout=180.0):
    """Step the walkthrough to completion under a real mainloop (so the async
    sample load can post back), returning whether the graph window opened."""
    state = {"saw_graph": False, "done": False, "win_wait": 0}
    deadline = time.monotonic() + timeout

    def poll():
        if not getattr(app, "_wt_active", False):
            state["done"] = True
            root.quit()
            return
        if time.monotonic() >= deadline:
            root.quit()
            return
        if getattr(app, "_busy", False):
            root.after(50, poll)  # wait out an async sample load
            return
        step = app._wt_steps[app._wt_index]
        if step.get("window"):
            win = getattr(app, "_secondary_win", None)
            if win is not None and win.winfo_exists():
                state["saw_graph"] = True
            elif state["win_wait"] < 12:
                state["win_wait"] += 1
                root.after(120, poll)  # give the graph window time to open
                return
        app._wt_next()
        root.after(120, poll)

    root.after(50, poll)
    root.mainloop()
    if not state["done"]:
        raise AssertionError("walkthrough did not finish before timeout")
    return state["saw_graph"]


@pytest.mark.gui
def test_walkthrough_runs_on_loaded_data_and_restores(gui_app, tmp_path):
    """The full walkthrough steps to the end on an already-loaded file."""
    ged_path = tmp_path / "wt.ged"
    ged_path.write_text(GUI_GED, encoding="utf-8")
    app = gui_app
    root = app.root
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(exc)

    app.gedcom_path.set(str(ged_path))
    app._load_file()
    _mainloop_until(root, lambda: not app._busy and len(app.individuals) == 3)

    app._show_walkthrough()
    _pump(root, 0.3)
    assert app._wt_active
    assert app._wt_steps  # built a non-empty step list

    saw_graph = _drive_walkthrough_to_end(app, root)

    assert not app._wt_active, "walkthrough should finish after the last step"
    assert saw_graph, "graph window should open during the tour"
    assert not app._wt_used_sample, "already-loaded data should be reused"
    assert app.individuals, "user's data should remain loaded afterwards"
    assert not errors, f"callback exceptions during walkthrough: {errors}"

    # The graph window opened for the demo must be closed at the end.
    win = getattr(app, "_secondary_win", None)
    assert win is None or not win.winfo_exists()


@pytest.mark.gui
def test_walkthrough_loads_sample_then_unloads(gui_app):
    """With no file loaded, the tour loads the bundled sample then unloads it."""
    app = gui_app
    root = app.root
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(exc)

    app._clear_loaded_data()
    _pump(root, 0.1)
    assert not app.individuals
    recent_before = list(app._recent_files)

    app._show_walkthrough()
    _pump(root, 0.3)
    sample_path = os.path.abspath(app._resource_path(
        "samples/fictional_genealogy.ged"))

    saw_graph = _drive_walkthrough_to_end(app, root)

    assert not app._wt_active
    assert app._wt_used_sample, "an empty app should load the bundled sample"
    assert saw_graph, "graph window should open during the sample tour"
    _pump_while(root, lambda: getattr(app, "_busy", False))
    _pump(root, 0.3)
    assert not app.individuals, "the sample must be unloaded when the tour ends"
    assert app._results_header_var.get() == ""
    assert list(app._recent_files) == recent_before
    assert not any(os.path.abspath(p) == sample_path for p in app._recent_files)
    assert not errors, f"callback exceptions during walkthrough: {errors}"


@pytest.mark.gui
def test_reentry_guard_prevents_second_walkthrough(gui_app):
    app = gui_app
    app._show_walkthrough()
    _pump(app.root, 0.2)
    first_coach = app._wt_coach
    app._show_walkthrough()  # should be a no-op while one is active
    _pump(app.root, 0.2)
    assert app._wt_coach is first_coach
    app._wt_end()
    _pump(app.root, 0.2)
    assert not app._wt_active


@pytest.mark.gui
def test_welcome_window_has_checkbox_and_launches_walkthrough(gui_app):
    import customtkinter as ctk
    import gedcom_strings as gs

    app = gui_app
    root = app.root
    before = set(root.winfo_children())
    app._show_welcome(on_close=lambda: None)
    _pump_until(root, lambda: len(set(root.winfo_children()) - before) >= 1)

    assert _find_widgets(root, ctk.CTkCheckBox, gs.CHK_SHOW_NEXT_TIME)
    buttons = _find_widgets(root, ctk.CTkButton, gs.BTN_WALKTHROUGH)
    assert buttons, "welcome window should have a Walkthrough button"

    buttons[0].invoke()
    _pump(root, 0.3)
    assert app._wt_active, "Walkthrough button should start the tour"
    app._wt_end()


@pytest.mark.gui
def test_help_window_has_walkthrough_button_without_checkbox(gui_app):
    import customtkinter as ctk
    import gedcom_strings as gs

    app = gui_app
    root = app.root
    before = set(root.winfo_children())
    app._show_how_to_use()
    _pump_until(root, lambda: len(set(root.winfo_children()) - before) >= 1)

    assert _find_widgets(root, ctk.CTkButton, gs.BTN_WALKTHROUGH)
    assert not _find_widgets(root, ctk.CTkCheckBox, gs.CHK_SHOW_NEXT_TIME), (
        "the help window should not carry the welcome-only checkbox")


@pytest.mark.gui
def test_onboarding_shows_welcome_once_per_version(gui_app, monkeypatch):
    app = gui_app
    calls = {"welcome": 0, "after": 0}
    monkeypatch.setattr(app, "_show_welcome", lambda on_close=None: calls.__setitem__(
        "welcome", calls["welcome"] + 1))
    monkeypatch.setattr(app, "_after_onboarding", lambda: calls.__setitem__(
        "after", calls["after"] + 1))

    # New version (nothing seen yet) -> show welcome and stamp the version.
    app._config.set_show_welcome_on_startup(False)
    app._config.set_welcome_seen_version("0.0.0-old")
    app._start_onboarding()
    assert calls["welcome"] == 1
    assert app._config.get_welcome_seen_version() == app._version

    # Same version, opted out -> skip welcome, go straight to the open prompt.
    app._start_onboarding()
    assert calls["welcome"] == 1
    assert calls["after"] == 1

    # Same version but opted in -> show welcome every launch.
    app._config.set_show_welcome_on_startup(True)
    app._start_onboarding()
    assert calls["welcome"] == 2


@pytest.mark.gui
def test_main_window_action_controls_have_tooltips(gui_app):
    app = gui_app
    app.root.update_idletasks()
    missing = []
    action_classes = {"CTkButton", "CTkCheckBox", "CTkRadioButton"}
    excluded_text = {"OK", "Cancel", "Close"}

    def visit(widget):
        cls_name = widget.__class__.__name__
        try:
            text = widget.cget("text")
        except Exception:  # pylint: disable=broad-exception-caught
            text = ""
        if cls_name in action_classes and text not in excluded_text:
            if not Tooltip.text_for(widget):
                missing.append(f"{cls_name}:{text}")
        for child in widget.winfo_children():
            visit(child)

    visit(app.root)

    assert missing == []
