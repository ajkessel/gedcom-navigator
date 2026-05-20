"""Tests for graph canvas export helpers."""

from gedcom_graph_export import (
    _canvas_text_svg,
    _draw_canvas_text_png,
    _font_file_candidates,
)


class _FakeCanvas:
    def __init__(self):
        self.values = {
            'text': 'John Q.',
            'fill': '#111111',
            'anchor': 'center',
            'justify': 'center',
            'font': 'fake_font',
            'width': '120',
        }

    @staticmethod
    def coords(_item_id):
        return (50, 40)

    def itemcget(self, _item_id, option):
        return self.values.get(option, '')


class _FakeSvgFont:
    def __init__(self, font=None):  # pylint: disable=unused-argument
        pass

    @staticmethod
    def actual():
        return {
            'family': 'Segoe UI',
            'size': 11,
            'weight': 'bold',
            'slant': 'roman',
        }

    @staticmethod
    def metrics(_name):
        return 14


class _FakeDraw:
    def __init__(self):
        self.text_calls = []

    @staticmethod
    def textbbox(_xy, text, font=None):  # pylint: disable=unused-argument
        return (0, 0, len(text) * 8, 10)

    def text(self, xy, text, fill=None, font=None):
        self.text_calls.append((xy, text, fill, font))


class _FakePillowFont:
    @staticmethod
    def getbbox(text):
        return (0, 0, len(text) * 8, 10)


def test_font_file_candidates_prefers_windows_bold_face():
    """Windows font lookup asks for the bold face before the regular family."""
    candidates = list(_font_file_candidates('Segoe UI', True, False))

    assert candidates[0] == ('segoeuib.ttf', True)
    assert ('segoeui.ttf', False) in candidates


def test_canvas_text_svg_preserves_bold_font_weight(monkeypatch):
    """SVG export emits the Tk text item's bold weight."""
    monkeypatch.setattr('gedcom_graph_export.tkfont.Font', _FakeSvgFont)

    svg = _canvas_text_svg(_FakeCanvas(), 1)

    assert 'font-weight="bold"' in svg


def test_canvas_text_png_uses_faux_bold_when_style_face_missing(monkeypatch):
    """PNG export keeps bold text visible when Pillow cannot load a bold face."""
    monkeypatch.setattr(
        'gedcom_graph_export._tk_canvas_font_actual',
        lambda _font_name: {
            'family': 'Missing Font',
            'size': 11,
            'weight': 'bold',
            'slant': 'roman',
        })
    monkeypatch.setattr(
        'gedcom_graph_export._pillow_font_from_actual',
        lambda _actual: (_FakePillowFont(), False))
    draw = _FakeDraw()

    _draw_canvas_text_png(draw, _FakeCanvas(), 1)

    assert len(draw.text_calls) == 2
    assert draw.text_calls[1][0][0] == draw.text_calls[0][0][0] + 1
