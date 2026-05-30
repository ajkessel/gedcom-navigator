"""Regression tests for macOS-safe clipboard copy.

The Mac App Store build runs sandboxed with a patched Tk whose lazy clipboard
owner does not reach NSPasteboard, so plain-text copy silently did nothing.
These tests pin the shared helper's behaviour and verify the result-copy path
routes through it instead of touching Tk's clipboard directly.
"""

import sys
import types

import gedcom_gui_results
import gedcom_platform


class FakeWidget:
    """Stand-in for a Tk widget that records clipboard calls."""

    def __init__(self):
        self.cleared = 0
        self.appended = []

    def clipboard_clear(self):
        self.cleared += 1

    def clipboard_append(self, text):
        self.appended.append(text)


def _install_fake_appkit(monkeypatch, pasteboard):
    fake_appkit = types.ModuleType("AppKit")
    fake_appkit.NSPasteboard = types.SimpleNamespace(
        generalPasteboard=lambda: pasteboard)
    fake_appkit.NSPasteboardTypeString = "public.utf8-plain-text"
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit)


def test_copy_text_uses_tk_clipboard_off_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    widget = FakeWidget()

    gedcom_platform.copy_text_to_clipboard(widget, "hello")

    assert widget.cleared == 1
    assert widget.appended == ["hello"]


def test_copy_text_uses_nspasteboard_on_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    written = {}

    class FakePasteboard:
        def clearContents(self):
            written["cleared"] = True

        def setString_forType_(self, text, ptype):
            written["text"] = text
            written["type"] = ptype
            return True

    _install_fake_appkit(monkeypatch, FakePasteboard())
    widget = FakeWidget()

    gedcom_platform.copy_text_to_clipboard(widget, "hello")

    assert written == {
        "cleared": True,
        "text": "hello",
        "type": "public.utf8-plain-text",
    }
    # Tk's clipboard must not be used when NSPasteboard accepts the data.
    assert widget.cleared == 0
    assert widget.appended == []


def test_copy_text_falls_back_to_tk_when_pasteboard_fails(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    class FakePasteboard:
        def clearContents(self):
            pass

        def setString_forType_(self, text, ptype):
            return False  # NSPasteboard refused the write

    _install_fake_appkit(monkeypatch, FakePasteboard())
    widget = FakeWidget()

    gedcom_platform.copy_text_to_clipboard(widget, "hello")

    assert widget.cleared == 1
    assert widget.appended == ["hello"]


def test_copy_results_routes_header_and_body_through_helper(monkeypatch):
    """Results copy assembles header + body and delegates to the helper."""

    class FakeText:
        def get(self, start, end):
            return "Body line 1\nBody line 2\n"

    class FakeVar:
        def get(self):
            return "Header"

    class App(gedcom_gui_results.ResultsMixin):
        pass

    app = App()
    app.results = FakeText()
    app._results_header_var = FakeVar()
    app.root = object()

    captured = {}
    monkeypatch.setattr(
        gedcom_gui_results, "copy_text_to_clipboard",
        lambda widget, text: captured.update(widget=widget, text=text))

    app._copy_results()

    assert captured["widget"] is app.root
    assert captured["text"] == "Header\n\nBody line 1\nBody line 2"
