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
