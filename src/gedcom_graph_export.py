#!/usr/bin/env python3
"""
gedcom_graph_export.py

SVG and PNG export helpers for relationship graph canvases.
"""

import io
import math
import os
import tkinter as tk
import tkinter.font as tkfont


def _svg_escape(value):
    """Escape text for XML/SVG output."""
    return str(value).replace('&', '&amp;').replace(
        '<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _svg_number(value):
    """Return a compact SVG-compatible numeric string."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f'{number:.3f}'.rstrip('0').rstrip('.')


def _canvas_color_to_rgb(value, default=(0, 0, 0)):
    """Return an RGB tuple for a Tk color value."""
    if not value:
        return default
    try:
        from PIL import ImageColor  # pylint: disable=import-outside-toplevel

        return ImageColor.getrgb(value)
    except (ImportError, ValueError):
        return default


def _tk_canvas_font_actual(font_name):
    """Return normalized Tk font details for a canvas font name."""
    try:
        actual = tkfont.Font(font=font_name).actual()
        return {
            'family': actual.get('family') or '',
            'size': abs(int(actual.get('size') or 10)),
            'weight': actual.get('weight') or 'normal',
            'slant': actual.get('slant') or 'roman',
        }
    except (tk.TclError, TypeError, ValueError):
        return {
            'family': '',
            'size': 10,
            'weight': 'normal',
            'slant': 'roman',
        }


def _font_search_dirs():
    """Return likely platform font directories."""
    dirs = []
    windir = os.environ.get('WINDIR')
    if windir:
        dirs.append(os.path.join(windir, 'Fonts'))
    dirs.extend([
        r'C:\Windows\Fonts',
        '/System/Library/Fonts',
        '/System/Library/Fonts/Supplemental',
        '/Library/Fonts',
        '/usr/share/fonts/truetype',
        '/usr/share/fonts',
    ])
    seen = set()
    for directory in dirs:
        if directory and directory not in seen and os.path.isdir(directory):
            seen.add(directory)
            yield directory


def _font_file_candidates(family, bold, italic):
    """Yield likely font filenames for the requested Tk font style."""
    family = family or ''
    compact = family.replace(' ', '')
    lower = family.strip().lower()
    windows_names = {
        'segoe ui': {
            (False, False): 'segoeui.ttf',
            (True, False): 'segoeuib.ttf',
            (False, True): 'segoeuii.ttf',
            (True, True): 'segoeuiz.ttf',
        },
        'arial': {
            (False, False): 'arial.ttf',
            (True, False): 'arialbd.ttf',
            (False, True): 'ariali.ttf',
            (True, True): 'arialbi.ttf',
        },
        'calibri': {
            (False, False): 'calibri.ttf',
            (True, False): 'calibrib.ttf',
            (False, True): 'calibrii.ttf',
            (True, True): 'calibriz.ttf',
        },
        'courier new': {
            (False, False): 'cour.ttf',
            (True, False): 'courbd.ttf',
            (False, True): 'couri.ttf',
            (True, True): 'courbi.ttf',
        },
        'times new roman': {
            (False, False): 'times.ttf',
            (True, False): 'timesbd.ttf',
            (False, True): 'timesi.ttf',
            (True, True): 'timesbi.ttf',
        },
    }
    mapped = windows_names.get(lower, {}).get((bold, italic))
    if mapped:
        yield mapped, True

    style_names = []
    if bold and italic:
        style_names.extend(['Bold Italic', 'BoldItalic', 'BoldOblique'])
    elif bold:
        style_names.extend(['Bold', 'Semibold', 'DemiBold'])
    elif italic:
        style_names.extend(['Italic', 'Oblique'])
    for style in style_names:
        for extension in ('.ttf', '.otf', '.ttc'):
            yield f'{family} {style}{extension}', True
            if compact:
                yield f'{compact}-{style}{extension}', True
                yield f'{compact}{style}{extension}', True

    for extension in ('.ttf', '.otf', '.ttc'):
        if family:
            yield f'{family}{extension}', not (bold or italic)
        if compact and compact != family:
            yield f'{compact}{extension}', not (bold or italic)
    regular_mapped = windows_names.get(lower, {}).get((False, False))
    if regular_mapped and regular_mapped != mapped:
        yield regular_mapped, not (bold or italic)
    if family:
        yield family, not (bold or italic)


def _pillow_font_from_actual(actual):
    """Return a Pillow font and whether it matched the requested style."""
    try:
        from PIL import ImageFont  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise tk.TclError(
            "Pillow is required for macOS graph clipboard copy."
        ) from exc

    family = actual.get('family') or ''
    size = abs(int(actual.get('size') or 10))
    bold = actual.get('weight') == 'bold'
    italic = actual.get('slant') == 'italic'
    for candidate, style_match in _font_file_candidates(family, bold, italic):
        for directory in (None, *_font_search_dirs()):
            path = candidate if directory is None else os.path.join(
                directory, candidate)
            try:
                return ImageFont.truetype(path, size=size), style_match
            except OSError:
                continue
    return ImageFont.load_default(size=size), not (bold or italic)


def _pillow_canvas_font(font_name):
    """Return a Pillow font that approximates a Tk canvas font."""
    font, _style_match = _pillow_font_from_actual(
        _tk_canvas_font_actual(font_name))
    return font


def _draw_pillow_text(draw, xy, text, fill, font, faux_bold=False):
    """Draw text, adding a small second pass when no bold face is available."""
    draw.text(xy, text, fill=fill, font=font)
    if faux_bold:
        x, y = xy
        draw.text((x + 1, y), text, fill=fill, font=font)


def _draw_dashed_line(draw, xy, fill, width, dash):
    """Draw a dashed line segment."""
    x1, y1, x2, y2 = xy
    dash_values = [float(value) for value in dash.split() if value]
    if len(dash_values) < 2:
        draw.line(xy, fill=fill, width=width)
        return
    dash_len, gap_len = dash_values[:2]
    total = math.hypot(x2 - x1, y2 - y1)
    if total <= 0:
        return
    ux = (x2 - x1) / total
    uy = (y2 - y1) / total
    pos = 0.0
    while pos < total:
        end = min(pos + dash_len, total)
        draw.line(
            (x1 + ux * pos, y1 + uy * pos, x1 + ux * end, y1 + uy * end),
            fill=fill, width=width)
        pos = end + gap_len


def _draw_arrowhead(draw, x1, y1, x2, y2, fill, width):
    """Draw an arrowhead at the end of a line."""
    angle = math.atan2(y2 - y1, x2 - x1)
    length = max(width * 4, 12)
    spread = math.radians(28)
    points = [(x2, y2)]
    for sign in (1, -1):
        points.append((
            x2 - length * math.cos(angle + sign * spread),
            y2 - length * math.sin(angle + sign * spread),
        ))
    draw.polygon(points, fill=fill)


def _pillow_text_width(draw, text, font):
    """Return the rendered width of text for a Pillow font."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_pillow_text(draw, text, font, max_width):
    """Wrap text to match a Tk canvas text width constraint."""
    if not max_width or max_width <= 0:
        return text.splitlines() or ['']

    wrapped = []
    for raw_line in text.splitlines() or ['']:
        words = raw_line.split()
        if not words:
            wrapped.append('')
            continue
        current = ''
        for word in words:
            trial = word if not current else f'{current} {word}'
            if _pillow_text_width(draw, trial, font) <= max_width:
                current = trial
            else:
                if current:
                    wrapped.append(current)
                current = word
        if current:
            wrapped.append(current)
    return wrapped or ['']


def _draw_canvas_text_png(draw, canvas, item_id):
    """Draw a Tk canvas text item into a Pillow image."""
    x, y = canvas.coords(item_id)
    text = canvas.itemcget(item_id, 'text')
    fill = _canvas_color_to_rgb(canvas.itemcget(item_id, 'fill'))
    anchor = canvas.itemcget(item_id, 'anchor') or 'center'
    justify = canvas.itemcget(item_id, 'justify') or 'center'
    actual = _tk_canvas_font_actual(canvas.itemcget(item_id, 'font'))
    font, style_match = _pillow_font_from_actual(actual)
    faux_bold = actual.get('weight') == 'bold' and not style_match
    try:
        max_width = float(canvas.itemcget(item_id, 'width') or 0)
    except ValueError:
        max_width = 0
    lines = _wrap_pillow_text(draw, text, font, max_width)
    line_spacing = max(
        font.getbbox('Mg')[3] - font.getbbox('Mg')[1] + 3, 12)
    sizes = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
    total_h = line_spacing * (len(lines) - 1) + max(
        (height for _, height in sizes), default=line_spacing)
    max_w = max((width for width, _ in sizes), default=0)

    if anchor in ('n', 'ne', 'nw'):
        top = y
    elif anchor in ('s', 'se', 'sw'):
        top = y - total_h
    else:
        top = y - total_h / 2
    for index, line in enumerate(lines):
        line_w = sizes[index][0]
        if anchor in ('w', 'nw', 'sw'):
            box_left = x
        elif anchor in ('e', 'ne', 'se'):
            box_left = x - max_w
        else:
            box_left = x - max_w / 2
        if justify == 'left':
            left = box_left
        elif justify == 'right':
            left = box_left + max_w - line_w
        else:
            left = box_left + (max_w - line_w) / 2
        _draw_pillow_text(
            draw, (left, top + index * line_spacing),
            line, fill, font, faux_bold=faux_bold)
    return max_w, total_h


def canvas_to_png_bytes(canvas, width, height):
    """Return PNG bytes for the full graph canvas."""
    try:
        from PIL import Image, ImageDraw  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise tk.TclError(
            "Pillow is required for macOS graph clipboard copy."
        ) from exc

    width = int(round(width))
    height = int(round(height))
    bg = _canvas_color_to_rgb(canvas.cget('bg'), default=(255, 255, 255))
    image = Image.new('RGB', (width, height), bg)
    draw = ImageDraw.Draw(image)

    for item_id in canvas.find_all():
        if canvas.itemcget(item_id, 'state') == 'hidden':
            continue
        item_type = canvas.type(item_id)
        if item_type == 'rectangle':
            x1, y1, x2, y2 = canvas.coords(item_id)
            fill = _canvas_color_to_rgb(
                canvas.itemcget(item_id, 'fill'), default=None)
            outline = _canvas_color_to_rgb(
                canvas.itemcget(item_id, 'outline'), default=None)
            item_width = max(
                int(float(canvas.itemcget(item_id, 'width') or 1)), 1)
            draw.rectangle(
                (x1, y1, x2, y2), fill=fill, outline=outline,
                width=item_width)
        elif item_type == 'line':
            coords = canvas.coords(item_id)
            if len(coords) < 4:
                continue
            fill = _canvas_color_to_rgb(canvas.itemcget(item_id, 'fill'))
            item_width = max(
                int(float(canvas.itemcget(item_id, 'width') or 1)), 1)
            dash = canvas.itemcget(item_id, 'dash').strip('{}')
            if dash and len(coords) == 4:
                _draw_dashed_line(draw, coords, fill, item_width, dash)
            else:
                draw.line(coords, fill=fill, width=item_width)
            if canvas.itemcget(item_id, 'arrow') in ('last', 'both'):
                _draw_arrowhead(
                    draw, coords[-4], coords[-3], coords[-2], coords[-1],
                    fill, item_width)
        elif item_type == 'text':
            _draw_canvas_text_png(draw, canvas, item_id)

    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def _svg_attrs(**attrs):
    """Return formatted SVG attributes, omitting empty values."""
    parts = []
    for name, value in attrs.items():
        if value in (None, ''):
            continue
        parts.append(f' {name.replace("_", "-")}="{_svg_escape(value)}"')
    return ''.join(parts)


def _canvas_text_svg(canvas, item_id):
    """Return SVG markup for a Tk canvas text item."""
    x, y = canvas.coords(item_id)
    text = canvas.itemcget(item_id, 'text')
    fill = canvas.itemcget(item_id, 'fill') or '#000000'
    anchor = canvas.itemcget(item_id, 'anchor') or 'center'
    justify = canvas.itemcget(item_id, 'justify') or 'center'
    font_name = canvas.itemcget(item_id, 'font')
    try:
        font = tkfont.Font(font=font_name)
        actual = font.actual()
        line_space = font.metrics('linespace')
    except tk.TclError:
        actual = {'family': 'sans-serif', 'size': 10, 'weight': 'normal'}
        line_space = 12

    family = actual.get('family') or 'sans-serif'
    size = abs(int(actual.get('size') or 10))
    weight = 'bold' if actual.get('weight') == 'bold' else 'normal'
    slant = 'italic' if actual.get('slant') == 'italic' else 'normal'
    text_anchor = {
        'w': 'start',
        'nw': 'start',
        'sw': 'start',
        'e': 'end',
        'ne': 'end',
        'se': 'end',
    }.get(anchor, 'middle')
    dominant = 'central'
    if anchor in ('n', 'ne', 'nw'):
        dominant = 'text-before-edge'
    elif anchor in ('s', 'se', 'sw'):
        dominant = 'text-after-edge'
    if justify == 'left':
        text_anchor = 'start'
    elif justify == 'right':
        text_anchor = 'end'

    lines = text.splitlines() or ['']
    attrs = _svg_attrs(
        x=_svg_number(x), y=_svg_number(y),
        fill=fill, font_family=family, font_size=size,
        font_weight=weight, font_style=slant,
        text_anchor=text_anchor, dominant_baseline=dominant)
    if len(lines) == 1:
        return f'  <text{attrs}>{_svg_escape(lines[0])}</text>'

    first_dy = -((len(lines) - 1) * line_space / 2)
    tspans = []
    for index, line in enumerate(lines):
        dy = first_dy if index == 0 else line_space
        tspans.append(
            f'<tspan x="{_svg_number(x)}" '
            f'dy="{_svg_number(dy)}">'
            f'{_svg_escape(line)}</tspan>')
    return f'  <text{attrs}>{"".join(tspans)}</text>'


def canvas_to_svg(canvas, width, height):
    """Return SVG markup for the full graph canvas."""
    width = int(round(width))
    height = int(round(height))
    bg = canvas.cget('bg')
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        ),
        f'  <rect width="100%" height="100%" fill="{_svg_escape(bg)}"/>',
    ]
    markers = {}

    def marker_id(color):
        if color not in markers:
            markers[color] = f'arrow{len(markers) + 1}'
        return markers[color]

    body = []
    for item_id in canvas.find_all():
        if canvas.itemcget(item_id, 'state') == 'hidden':
            continue
        item_type = canvas.type(item_id)
        if item_type == 'rectangle':
            x1, y1, x2, y2 = canvas.coords(item_id)
            attrs = _svg_attrs(
                x=_svg_number(x1),
                y=_svg_number(y1),
                width=_svg_number(x2 - x1),
                height=_svg_number(y2 - y1),
                fill=canvas.itemcget(item_id, 'fill'),
                stroke=canvas.itemcget(item_id, 'outline'),
                stroke_width=canvas.itemcget(item_id, 'width'),
            )
            body.append(f'  <rect{attrs}/>')
        elif item_type == 'line':
            coords = canvas.coords(item_id)
            fill = canvas.itemcget(item_id, 'fill') or '#000000'
            dash = canvas.itemcget(item_id, 'dash').strip('{}')
            attrs = {
                'fill': 'none',
                'stroke': fill,
                'stroke_width': canvas.itemcget(item_id, 'width'),
                'stroke_dasharray': dash,
                'marker_end': (
                    f'url(#{marker_id(fill)})'
                    if canvas.itemcget(item_id, 'arrow') in ('last', 'both')
                    else None
                ),
            }
            if len(coords) == 4:
                x1, y1, x2, y2 = coords
                attrs.update({
                    'x1': _svg_number(x1),
                    'y1': _svg_number(y1),
                    'x2': _svg_number(x2),
                    'y2': _svg_number(y2),
                })
                body.append(f'  <line{_svg_attrs(**attrs)}/>')
            else:
                points = ' '.join(
                    f'{_svg_number(coords[i])},'
                    f'{_svg_number(coords[i + 1])}'
                    for i in range(0, len(coords), 2))
                attrs['points'] = points
                body.append(f'  <polyline{_svg_attrs(**attrs)}/>')
        elif item_type == 'text':
            body.append(_canvas_text_svg(canvas, item_id))

    if markers:
        lines.append('  <defs>')
        for color, ident in markers.items():
            lines.append(
                f'    <marker id="{ident}" viewBox="0 0 12 12" '
                'refX="10" refY="6" markerWidth="8" markerHeight="8" '
                'orient="auto" markerUnits="strokeWidth">'
                f'<path d="M 0 0 L 12 6 L 0 12 z" fill="{_svg_escape(color)}"/>'
                '</marker>')
        lines.append('  </defs>')
    lines.extend(body)
    lines.append('</svg>')
    return '\n'.join(lines) + '\n'
