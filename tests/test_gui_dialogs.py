"""Tests for shared GUI dialog helpers."""

import tkinter as tk

from gedcom_gui_dialogs import DialogsMixin


class _FocusDialog:
    def __init__(self, calls):
        self._calls = calls

    def focus_force(self):
        self._calls.append(("dialog", "focus_force"))


class _BrokenDialog:
    def focus_force(self):
        raise tk.TclError("window is gone")


class _FocusEntry:
    def __init__(self, name, calls, inner=None):
        self._name = name
        self._calls = calls
        if inner is not None:
            self._entry = inner

    def focus_set(self):
        self._calls.append((self._name, "focus_set"))

    def select_range(self, start, end):
        self._calls.append((self._name, "select_range", start, end))


def test_person_picker_focuses_find_entry_and_ctk_inner_entry():
    calls = []
    inner = _FocusEntry("inner", calls)
    entry = _FocusEntry("entry", calls, inner=inner)

    DialogsMixin()._focus_person_picker_find_entry(_FocusDialog(calls), entry)

    assert calls == [
        ("dialog", "focus_force"),
        ("entry", "focus_set"),
        ("entry", "select_range", 0, "end"),
        ("inner", "focus_set"),
        ("inner", "select_range", 0, "end"),
    ]


def test_person_picker_focus_helper_ignores_destroyed_dialog():
    calls = []
    entry = _FocusEntry("entry", calls)

    DialogsMixin()._focus_person_picker_find_entry(_BrokenDialog(), entry)

    assert calls == []
