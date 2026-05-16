#!/usr/bin/env python3
"""
gedcom_gui_results.py

Result rendering, path reversal, person navigation, and family-summary helpers.
"""

import io
import math
import os
import re
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gedcom_display import describe
from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)
from gedcom_search import bfs_find_all_paths, bfs_find_dna_matches
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_theme import get_link_color, ttk_colors
from gedcom_tooltip import TextTagTooltip, Tooltip


class ResultsMixin:
    """Render search results and handle result-pane navigation."""

    @staticmethod
    def _mix_hex_color(color_a, color_b, weight_b):
        """Return a hex color mixed between two #RRGGBB values."""
        weight_b = min(max(weight_b, 0), 1)
        weight_a = 1 - weight_b
        a = color_a.lstrip('#')
        b = color_b.lstrip('#')
        mixed = []
        for pos in (0, 2, 4):
            value = round(int(a[pos:pos + 2], 16) * weight_a
                          + int(b[pos:pos + 2], 16) * weight_b)
            mixed.append(f'{value:02x}')
        return '#' + ''.join(mixed)

    @staticmethod
    def _readable_text_color(bg_color):
        """Return black or white text for readable contrast on a hex background."""
        rgb = [
            int(bg_color.lstrip('#')[pos:pos + 2], 16)
            for pos in (0, 2, 4)
        ]
        luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
        return '#1a1a1a' if luminance > 150 else '#ffffff'

    @classmethod
    def _path_graph_colors(cls, is_dark, theme_name):
        """Return graph colors derived from the active application theme."""
        theme = ttk_colors(is_dark, theme_name)
        accent = get_link_color(is_dark, theme_name)
        return {
            'bg': theme['bg'],
            'guide': theme['trough'],
            'node_fill': theme['field_bg'],
            'endpoint_fill': cls._mix_hex_color(
                accent, theme['field_bg'], 0.78 if is_dark else 0.88),
            'node_outline': cls._mix_hex_color(accent, theme['fg'], 0.38),
            'text': theme['fg'],
            'badge_fill': accent,
            'badge_text': cls._readable_text_color(accent),
            'parent': accent,
            'spouse': cls._mix_hex_color(accent, theme['fg'], 0.28),
            'sibling': cls._mix_hex_color(accent, theme['trough'], 0.45),
        }

    @staticmethod
    def _svg_escape(value):
        """Return text with XML special characters escaped."""
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace(
            '>', '&gt;').replace('"', '&quot;')

    @staticmethod
    def _svg_number(value):
        """Return a compact SVG-compatible numeric string."""
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f'{number:.3f}'.rstrip('0').rstrip('.')

    @staticmethod
    def _canvas_color_to_rgb(value, default=(0, 0, 0)):
        """Return an RGB tuple for a Tk color value."""
        if not value:
            return default
        try:
            from PIL import ImageColor  # pylint: disable=import-outside-toplevel

            return ImageColor.getrgb(value)
        except (ImportError, ValueError):
            return default

    @staticmethod
    def _pillow_canvas_font(font_name):
        """Return a Pillow font that approximates a Tk canvas font."""
        try:
            from PIL import ImageFont  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise tk.TclError(
                "Pillow is required for macOS graph clipboard copy."
            ) from exc

        try:
            actual = tkfont.Font(font=font_name).actual()
            family = actual.get('family') or ''
            size = abs(int(actual.get('size') or 10))
        except tk.TclError:
            family = ''
            size = 10
        for candidate in (family, f'{family}.ttf' if family else ''):
            if not candidate:
                continue
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        return ImageFont.load_default(size=size)

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def _pillow_text_width(draw, text, font):
        """Return the rendered width of text for a Pillow font."""
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    @classmethod
    def _wrap_pillow_text(cls, draw, text, font, max_width):
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
                if cls._pillow_text_width(draw, trial, font) <= max_width:
                    current = trial
                else:
                    if current:
                        wrapped.append(current)
                    current = word
            if current:
                wrapped.append(current)
        return wrapped or ['']

    @classmethod
    def _draw_canvas_text_png(cls, draw, canvas, item_id):
        """Draw a Tk canvas text item into a Pillow image."""
        x, y = canvas.coords(item_id)
        text = canvas.itemcget(item_id, 'text')
        fill = cls._canvas_color_to_rgb(canvas.itemcget(item_id, 'fill'))
        anchor = canvas.itemcget(item_id, 'anchor') or 'center'
        justify = canvas.itemcget(item_id, 'justify') or 'center'
        font = cls._pillow_canvas_font(canvas.itemcget(item_id, 'font'))
        try:
            max_width = float(canvas.itemcget(item_id, 'width') or 0)
        except ValueError:
            max_width = 0
        lines = cls._wrap_pillow_text(draw, text, font, max_width)
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
            draw.text((left, top + index * line_spacing),
                      line, fill=fill, font=font)
        return max_w, total_h

    @classmethod
    def _canvas_to_png_bytes(cls, canvas, width, height):
        """Return PNG bytes for the full graph canvas."""
        try:
            from PIL import Image, ImageDraw  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise tk.TclError(
                "Pillow is required for macOS graph clipboard copy."
            ) from exc

        width = int(round(width))
        height = int(round(height))
        bg = cls._canvas_color_to_rgb(
            canvas.cget('bg'), default=(255, 255, 255))
        image = Image.new('RGB', (width, height), bg)
        draw = ImageDraw.Draw(image)

        for item_id in canvas.find_all():
            item_type = canvas.type(item_id)
            if item_type == 'rectangle':
                x1, y1, x2, y2 = canvas.coords(item_id)
                fill = cls._canvas_color_to_rgb(
                    canvas.itemcget(item_id, 'fill'), default=None)
                outline = cls._canvas_color_to_rgb(
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
                fill = cls._canvas_color_to_rgb(
                    canvas.itemcget(item_id, 'fill'))
                item_width = max(
                    int(float(canvas.itemcget(item_id, 'width') or 1)), 1)
                dash = canvas.itemcget(item_id, 'dash').strip('{}')
                if dash and len(coords) == 4:
                    cls._draw_dashed_line(draw, coords, fill, item_width, dash)
                else:
                    draw.line(coords, fill=fill, width=item_width)
                if canvas.itemcget(item_id, 'arrow') in ('last', 'both'):
                    cls._draw_arrowhead(
                        draw, coords[-4], coords[-3], coords[-2], coords[-1],
                        fill, item_width)
            elif item_type == 'text':
                cls._draw_canvas_text_png(draw, canvas, item_id)

        out = io.BytesIO()
        image.save(out, format='PNG')
        return out.getvalue()

    @classmethod
    def _svg_attrs(cls, **attrs):
        """Return formatted SVG attributes, omitting empty values."""
        parts = []
        for name, value in attrs.items():
            if value in (None, ''):
                continue
            parts.append(
                f' {name.replace("_", "-")}="{cls._svg_escape(value)}"')
        return ''.join(parts)

    @classmethod
    def _canvas_text_svg(cls, canvas, item_id):
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
        attrs = cls._svg_attrs(
            x=cls._svg_number(x), y=cls._svg_number(y),
            fill=fill, font_family=family, font_size=size,
            font_weight=weight, font_style=slant,
            text_anchor=text_anchor, dominant_baseline=dominant)
        if len(lines) == 1:
            return f'  <text{attrs}>{cls._svg_escape(lines[0])}</text>'

        first_dy = -((len(lines) - 1) * line_space / 2)
        tspans = []
        for index, line in enumerate(lines):
            dy = first_dy if index == 0 else line_space
            tspans.append(
                f'<tspan x="{cls._svg_number(x)}" '
                f'dy="{cls._svg_number(dy)}">'
                f'{cls._svg_escape(line)}</tspan>')
        return f'  <text{attrs}>{"".join(tspans)}</text>'

    @classmethod
    def _canvas_to_svg(cls, canvas, width, height):
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
            f'  <rect width="100%" height="100%" fill="{cls._svg_escape(bg)}"/>',
        ]
        markers = {}

        def marker_id(color):
            if color not in markers:
                markers[color] = f'arrow{len(markers) + 1}'
            return markers[color]

        body = []
        for item_id in canvas.find_all():
            item_type = canvas.type(item_id)
            if item_type == 'rectangle':
                x1, y1, x2, y2 = canvas.coords(item_id)
                attrs = cls._svg_attrs(
                    x=cls._svg_number(x1),
                    y=cls._svg_number(y1),
                    width=cls._svg_number(x2 - x1),
                    height=cls._svg_number(y2 - y1),
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
                        'x1': cls._svg_number(x1),
                        'y1': cls._svg_number(y1),
                        'x2': cls._svg_number(x2),
                        'y2': cls._svg_number(y2),
                    })
                    body.append(f'  <line{cls._svg_attrs(**attrs)}/>')
                else:
                    points = ' '.join(
                        f'{cls._svg_number(coords[i])},'
                        f'{cls._svg_number(coords[i + 1])}'
                        for i in range(0, len(coords), 2))
                    attrs['points'] = points
                    body.append(f'  <polyline{cls._svg_attrs(**attrs)}/>')
            elif item_type == 'text':
                body.append(cls._canvas_text_svg(canvas, item_id))

        if markers:
            lines.append('  <defs>')
            for color, ident in markers.items():
                lines.append(
                    f'    <marker id="{ident}" viewBox="0 0 12 12" '
                    'refX="10" refY="6" markerWidth="8" markerHeight="8" '
                    'orient="auto" markerUnits="strokeWidth">'
                    f'<path d="M 0 0 L 12 6 L 0 12 z" fill="{cls._svg_escape(color)}"/>'
                    '</marker>')
            lines.append('  </defs>')
        lines.extend(body)
        lines.append('</svg>')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _simplify_path_for_graph(path):
        """Collapse parent-child sibling detours before graphing a path."""
        if len(path) < 3:
            return list(path)

        simplified = [path[0]]
        index = 1
        while index < len(path):
            if (index + 1 < len(path)
                    and path[index][1] in ('father', 'mother')
                    and path[index + 1][1] == 'child'):
                simplified.append((path[index + 1][0], 'sibling'))
                index += 2
                continue
            simplified.append(path[index])
            index += 1
        return simplified

    @staticmethod
    def _path_graph_layout(path):
        """Return path nodes annotated with generation and column offsets."""
        generation = 0
        column = 0
        layout = []
        occupied = set()
        for index, (node_id, edge) in enumerate(path):
            if index > 0:
                if edge in ('father', 'mother'):
                    generation -= 1
                elif edge == 'child':
                    generation += 1
                elif edge in ('sibling', 'spouse'):
                    column += 1
            while (generation, column) in occupied:
                column += 1
            occupied.add((generation, column))
            layout.append({
                'id': node_id,
                'edge': edge,
                'generation': generation,
                'column': column,
                'index': index,
            })
        return layout

    @staticmethod
    def _wrap_canvas_label(text, font, max_width):
        """Wrap a canvas label using measured pixel width."""
        words = text.split()
        if not words:
            return text
        lines = []
        current = ''
        for word in words:
            trial = word if not current else f'{current} {word}'
            if font.measure(trial) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return '\n'.join(lines)

    @staticmethod
    def _path_graph_window_geometry(content_w, content_h, screen_w, screen_h,
                                    screen_x=0, screen_y=0):
        """Return geometry for a graph window sized to content or display."""
        chrome_w = 56
        chrome_h = 128
        min_w = min(640, screen_w)
        min_h = min(420, screen_h)
        desired_w = max(int(content_w) + chrome_w, min_w)
        desired_h = max(int(content_h) + chrome_h, min_h)
        if desired_w > screen_w or desired_h > screen_h:
            return screen_w, screen_h, screen_x, screen_y

        x = screen_x + max((screen_w - desired_w) // 2, 0)
        y = screen_y + max((screen_h - desired_h) // 2, 0)
        return desired_w, desired_h, x, y

    @staticmethod
    def _copy_windows_widget_bitmap(widget):
        """Copy a visible Tk widget to the Windows clipboard as a bitmap."""
        import ctypes  # pylint: disable=import-outside-toplevel
        import time  # pylint: disable=import-outside-toplevel

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        handle = ctypes.c_void_p

        user32.GetDC.argtypes = [handle]
        user32.GetDC.restype = handle
        user32.ReleaseDC.argtypes = [handle, handle]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.OpenClipboard.argtypes = [handle]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, handle]
        user32.SetClipboardData.restype = handle
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool

        gdi32.CreateCompatibleDC.argtypes = [handle]
        gdi32.CreateCompatibleDC.restype = handle
        gdi32.CreateCompatibleBitmap.argtypes = [
            handle, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = handle
        gdi32.SelectObject.argtypes = [handle, handle]
        gdi32.SelectObject.restype = handle
        gdi32.BitBlt.argtypes = [
            handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            handle, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        gdi32.BitBlt.restype = ctypes.c_bool
        gdi32.DeleteDC.argtypes = [handle]
        gdi32.DeleteDC.restype = ctypes.c_bool
        gdi32.DeleteObject.argtypes = [handle]
        gdi32.DeleteObject.restype = ctypes.c_bool

        cf_bitmap = 2
        srccopy = 0x00CC0020
        hwnd = handle(widget.winfo_id())
        width = max(widget.winfo_width(), 1)
        height = max(widget.winfo_height(), 1)

        source_dc = user32.GetDC(hwnd)
        if not source_dc:
            raise tk.TclError("Could not get widget device context.")

        memory_dc = None
        bitmap = None
        clipboard_open = False
        try:
            memory_dc = gdi32.CreateCompatibleDC(source_dc)
            if not memory_dc:
                raise tk.TclError("Could not create clipboard device context.")
            bitmap = gdi32.CreateCompatibleBitmap(source_dc, width, height)
            if not bitmap:
                raise tk.TclError("Could not create clipboard bitmap.")
            old_obj = gdi32.SelectObject(memory_dc, bitmap)
            try:
                if not gdi32.BitBlt(
                        memory_dc, 0, 0, width, height,
                        source_dc, 0, 0, srccopy):
                    raise tk.TclError("Could not copy graph bitmap.")
            finally:
                if old_obj:
                    gdi32.SelectObject(memory_dc, old_obj)

            for _ in range(8):
                if user32.OpenClipboard(hwnd):
                    clipboard_open = True
                    break
                time.sleep(0.05)
            if not clipboard_open:
                raise tk.TclError("Could not open the Windows clipboard.")
            if not user32.EmptyClipboard():
                raise tk.TclError("Could not clear the Windows clipboard.")
            if not user32.SetClipboardData(cf_bitmap, bitmap):
                raise tk.TclError("Could not set Windows clipboard bitmap.")
            bitmap = None
        finally:
            if clipboard_open:
                user32.CloseClipboard()
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(hwnd, source_dc)

    @classmethod
    def _copy_macos_canvas_png(cls, canvas, width, height):
        """Copy a Tk canvas to the macOS pasteboard as PNG image data."""
        try:
            from AppKit import (  # pylint: disable=import-outside-toplevel
                NSPasteboard,
                NSPasteboardTypePNG,
            )
            from Foundation import NSData  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise tk.TclError(
                "PyObjC is required for macOS graph clipboard copy."
            ) from exc

        png_bytes = cls._canvas_to_png_bytes(canvas, width, height)
        png_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if not pasteboard.setData_forType_(png_data, NSPasteboardTypePNG):
            raise tk.TclError("Could not set macOS clipboard image data.")

    @staticmethod
    def _reverse_path(path, individuals):
        """Return path reversed with edge labels recalculated for the new direction."""
        if len(path) <= 1:
            return list(path)
        n = len(path)
        result = [(path[n - 1][0], None)]
        for i in range(n - 2, -1, -1):
            orig_edge = path[i + 1][1]
            src_id = path[i][0]
            if orig_edge in ('father', 'mother'):
                rev_edge = 'child'
            elif orig_edge == 'child':
                sex = individuals.get(src_id, {}).get('sex', '')
                rev_edge = 'father' if sex == 'M' else (
                    'mother' if sex == 'F' else 'father')
            else:
                rev_edge = orig_edge
            result.append((src_id, rev_edge))
        return result

    @staticmethod
    def _path_edge_prefix(edge, indent):
        """Return a fixed-width visual connector for an edge label."""
        label = EDGE_LABELS.get(edge, edge)
        label_width = max(len(value) for value in EDGE_LABELS.values())
        return f"{indent}──{label.center(label_width, "─")}──▶ "

    def _show_path_graph(self, path, relationship):
        """Open a scrollable graphical view of a relationship path."""
        if not path:
            return

        graph_path = self._simplify_path_for_graph(path)
        layout = self._path_graph_layout(graph_path)
        labels = [
            describe(self.individuals[node['id']], show_id=self.show_ids.get())
            if node['id'] in self.individuals else node['id']
            for node in layout
        ]

        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_PATH_GRAPH)
        win.resizable(True, True)
        win.transient(self.root)

        is_dark = ctk.get_appearance_mode() == 'Dark'
        colors = self._path_graph_colors(
            is_dark, getattr(self, '_theme_pref', None))

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            outer,
            text=RESULT_RELATIONSHIP.format(rel=relationship),
            anchor='w',
            justify='left',
            wraplength=1000,
            font=ctk.CTkFont(weight='bold'),
        ).pack(fill='x', pady=(0, 8))

        canvas_frame = ctk.CTkFrame(outer, fg_color='transparent')
        canvas_frame.pack(fill='both', expand=True)
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        canvas = tk.Canvas(canvas_frame, bg=colors['bg'], highlightthickness=0)
        ybar = tk.Scrollbar(canvas_frame, orient='vertical',
                            command=canvas.yview)
        xbar = tk.Scrollbar(canvas_frame, orient='horizontal',
                            command=canvas.xview)
        canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        ybar.grid(row=0, column=1, sticky='ns')
        xbar.grid(row=1, column=0, sticky='ew')

        label_font = tkfont.Font(
            family=self._mono_family, size=max(self._mono_size - 2, 9))
        edge_font = tkfont.Font(
            family=self._mono_family, size=max(self._mono_size - 3, 8),
            weight='bold')
        badge_font = tkfont.Font(
            family=self._mono_family, size=max(self._mono_size - 5, 7),
            weight='bold')
        longest = max((label_font.measure(label)
                      for label in labels), default=0)
        node_w = min(max(longest + 28, 180), 320)
        wrapped_labels = [
            self._wrap_canvas_label(label, label_font, node_w - 22)
            for label in labels
        ]
        line_space = label_font.metrics('linespace')
        max_lines = max((label.count('\n') + 1 for label in wrapped_labels),
                        default=1)
        base_node_h = max(58, max_lines * line_space + 22)
        badge_h = badge_font.metrics('linespace') + 4
        endpoint_header_h = badge_h + 14
        node_heights = [
            base_node_h + endpoint_header_h
            if index in (0, len(layout) - 1) else base_node_h
            for index in range(len(layout))
        ]
        max_node_h = max(node_heights, default=base_node_h)
        h_gap = node_w + 90
        v_gap = max(max_node_h + 82, 140)
        margin = 44

        min_generation = min(node['generation'] for node in layout)
        max_generation = max(node['generation'] for node in layout)
        min_column = min(node['column'] for node in layout)
        max_column = max(node['column'] for node in layout)
        positions = []
        for node in layout:
            x = margin + node_w / 2 + (node['column'] - min_column) * h_gap
            y = margin + max_node_h / 2 + (
                node['generation'] - min_generation) * v_gap
            positions.append((x, y))

        canvas_w = margin * 2 + node_w + (max_column - min_column) * h_gap
        canvas_h = margin * 2 + max_node_h + (
            max_generation - min_generation) * v_gap

        for generation in range(min_generation, max_generation + 1):
            y = margin + max_node_h / 2 + (
                generation - min_generation) * v_gap
            canvas.create_line(
                margin / 2, y, canvas_w - margin / 2, y,
                fill=colors['guide'], dash=(3, 8))

        for index in range(1, len(layout)):
            edge = layout[index]['edge']
            label = EDGE_LABELS.get(edge, edge)
            x1, y1 = positions[index - 1]
            x2, y2 = positions[index]

            if edge == 'spouse':
                current_h = node_heights[index - 1]
                start_x = x1 + node_w / 2
                end_x = x2 - node_w / 2
                mid_x = (start_x + end_x) / 2
                for offset in (-4, 4):
                    canvas.create_line(
                        start_x, y1 + offset, end_x, y2 + offset,
                        fill=colors['spouse'], width=2)
                line_color = colors['spouse']
                label_y = y1 - current_h / 2 - 14
            elif edge == 'sibling':
                current_h = node_heights[index - 1]
                start_x = x1 + node_w / 2
                end_x = x2 - node_w / 2
                mid_x = (start_x + end_x) / 2
                canvas.create_line(
                    start_x, y1, end_x, y2,
                    fill=colors['sibling'], width=3, dash=(10, 5))
                line_color = colors['sibling']
                label_y = y1 - current_h / 2 - 14
            else:
                from_h = node_heights[index - 1]
                to_h = node_heights[index]
                mid_x = x1
                mid_y = (y1 + y2) / 2
                start_y = y1 + (from_h / 2 if y2 > y1 else -from_h / 2)
                end_y = y2 - (to_h / 2 if y2 > y1 else -to_h / 2)
                canvas.create_line(
                    x1, start_y, x2, end_y,
                    fill=colors['parent'], width=3, arrow='last',
                    arrowshape=(12, 14, 5))
                line_color = colors['parent']
                label_y = mid_y

            canvas.create_text(
                mid_x, label_y, text=label, fill=line_color,
                font=edge_font, anchor='center')

        for index, ((x, y), label) in enumerate(zip(positions, wrapped_labels)):
            node_h = node_heights[index]
            x1 = x - node_w / 2
            y1 = y - node_h / 2
            x2 = x + node_w / 2
            y2 = y + node_h / 2
            is_endpoint = index in (0, len(layout) - 1)
            fill = colors['endpoint_fill'] if is_endpoint else colors['node_fill']
            outline_width = 3 if is_endpoint else 2
            canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline=colors['node_outline'],
                width=outline_width)
            if is_endpoint:
                badge = PATH_GRAPH_START if index == 0 else PATH_GRAPH_END
                badge_w = badge_font.measure(badge) + 12
                badge_x1 = x1 + 8
                badge_y1 = y1 + 6
                badge_x2 = badge_x1 + badge_w
                badge_y2 = badge_y1 + badge_h
                canvas.create_rectangle(
                    badge_x1, badge_y1, badge_x2, badge_y2,
                    fill=colors['badge_fill'], outline=colors['badge_fill'])
                canvas.create_text(
                    (badge_x1 + badge_x2) / 2, (badge_y1 + badge_y2) / 2,
                    text=badge, fill=colors['badge_text'], font=badge_font,
                    anchor='center')
                text_y = y1 + endpoint_header_h + (
                    node_h - endpoint_header_h) / 2
            else:
                text_y = y
            canvas.create_text(
                x, text_y, text=label, fill=colors['text'], font=label_font,
                width=node_w - 22, justify='center')

        canvas.configure(scrollregion=(0, 0, canvas_w, canvas_h))

        def _save_graph(*_):
            canvas.update_idletasks()
            path = filedialog.asksaveasfilename(
                parent=win,
                title=DLG_SAVE_GRAPH,
                defaultextension='.png',
                filetypes=[
                    ("PNG images", "*.png"),
                    ("SVG images", "*.svg"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return 'break'
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext == '.svg':
                    svg = self._canvas_to_svg(canvas, canvas_w, canvas_h)
                    with open(path, 'w', encoding='utf-8') as svg_file:
                        svg_file.write(svg)
                else:
                    png = self._canvas_to_png_bytes(canvas, canvas_w, canvas_h)
                    with open(path, 'wb') as png_file:
                        png_file.write(png)
            except (OSError, tk.TclError) as exc:
                messagebox.showerror(
                    ERR_SAVE_GRAPH_TITLE,
                    ERR_SAVE_GRAPH_MSG.format(error=exc),
                    parent=win,
                )
            return 'break'

        def _copy_graph(*_):
            canvas.update_idletasks()
            if sys.platform == 'win32':
                self._copy_windows_widget_bitmap(canvas)
            elif sys.platform == 'darwin':
                self._copy_macos_canvas_png(canvas, canvas_w, canvas_h)
            else:
                postscript = canvas.postscript(
                    colormode='color', x=0, y=0,
                    width=canvas_w, height=canvas_h)
                win.clipboard_clear()
                try:
                    win.clipboard_append(postscript, type='PostScript')
                except tk.TclError:
                    win.clipboard_append(postscript)
                win.update()
            return 'break'

        btn_frame = ctk.CTkFrame(outer, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(8, 0))
        close_btn = ctk.CTkButton(
            btn_frame, text=BTN_CLOSE, width=80, command=win.destroy)
        close_btn.pack(side='right')
        copy_btn = ctk.CTkButton(
            btn_frame, text=BTN_COPY_GRAPH, width=80, command=_copy_graph)
        copy_btn.pack(side='right', padx=(0, 8))
        Tooltip(copy_btn, TIP_COPY_GRAPH)
        save_btn = ctk.CTkButton(
            btn_frame, text=BTN_SAVE_GRAPH, width=80, command=_save_graph)
        save_btn.pack(side='right', padx=(0, 8))
        Tooltip(save_btn, TIP_SAVE_GRAPH)

        copy_shortcut = '<Command-c>' if sys.platform == 'darwin' else '<Control-c>'
        save_shortcut = '<Command-s>' if sys.platform == 'darwin' else '<Control-s>'
        win.bind('<Escape>', lambda *_: win.destroy())
        win.bind(copy_shortcut, _copy_graph)
        win.bind(save_shortcut, _save_graph)
        win.grab_set()
        win.update_idletasks()
        try:
            screen_x = win.winfo_vrootx()
            screen_y = win.winfo_vrooty()
            screen_w = win.winfo_vrootwidth()
            screen_h = win.winfo_vrootheight()
        except tk.TclError:
            screen_x = 0
            screen_y = 0
            screen_w = win.winfo_screenwidth()
            screen_h = win.winfo_screenheight()
        width, height, x, y = self._path_graph_window_geometry(
            canvas_w, canvas_h, screen_w, screen_h, screen_x, screen_y)
        win.geometry(f'{width}x{height}+{x}+{y}')
        win.deiconify()
        win.lift()
        win.focus_force()

    def _reverse_results(self):
        """Toggle reversed display of the current results."""
        if not self._last_result:
            return
        self._results_reversed = not self._results_reversed
        self._reverse_btn.configure(
            text=BTN_REVERSE_RESTORE if self._results_reversed else BTN_REVERSE)
        kind = self._last_result['type']
        if kind == 'dna_matches':
            self._render_results(
                self._last_result['start_id'],
                self._last_result.get('results', []),
                home_paths=self._last_result.get('home_paths'),
            )
        elif kind == 'path':
            self._render_path_results(
                self._last_result['start_id'],
                self._last_result['end_id'],
                self._last_result.get('paths', []),
                self._last_result.get('truncated', False),
            )

    def _render_results(self, start_id, results, home_paths=None):
        """Render DNA match search results and family context."""
        if self._last_result and self._last_result.get('type') == 'dna_matches':
            self._last_result['results'] = results
            self._last_result['home_paths'] = home_paths
        w = self.results
        tw = w._textbox
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        tw.update_idletasks()
        sep_width = max(tw.winfo_width() - 4, 100)
        is_dark = ctk.get_appearance_mode() == 'Dark'
        sep_color = '#DCE4EE' if is_dark else '#1a1a1a'

        tag_to_id = {}
        tw.tag_configure('person_link', foreground=self._link_color)
        tw.tag_bind('person_link', '<Enter>',
                    lambda *_: tw.config(cursor='hand2'))
        tw.tag_bind('person_link', '<Leave>',
                    lambda *_: tw.config(cursor=''))
        tw.tag_configure('relationship_link',
                         foreground=self._link_color, underline=1)

        relationship_tooltip = getattr(self, '_relationship_tooltip', None)
        if relationship_tooltip is None:
            relationship_tooltip = TextTagTooltip(tw, TIP_RELATIONSHIP)
            self._relationship_tooltip = relationship_tooltip
        tw.tag_bind('relationship_link', '<Enter>',
                    lambda e: (tw.config(cursor='hand2'),
                               relationship_tooltip.on_enter(e)))
        tw.tag_bind('relationship_link', '<Motion>',
                    relationship_tooltip.on_enter)
        tw.tag_bind('relationship_link', '<Leave>',
                    lambda e: (tw.config(cursor=''),
                               relationship_tooltip.on_leave(e)))

        def _on_person_click(event):
            idx = tw.index(f'@{event.x},{event.y}')
            for t in tw.tag_names(idx):
                if t.startswith('pers_'):
                    iid = tag_to_id.get(t)
                    if iid:
                        self._navigate_to(iid)
                    break
        tw.tag_bind('person_link', '<Button-1>', _on_person_click)

        def nl(text='', bold=False):
            w.insert('end', text + '\n', ('bold',) if bold else ())

        def hr():
            sep = tk.Frame(tw, height=2, width=sep_width,
                           bg=sep_color, bd=0, relief='flat')
            tw.window_create('end', window=sep)
            tw.insert('end', '\n')

        def person(indi_id, prefix='', bold=False):
            base = ('bold',) if bold else ()
            if prefix:
                w.insert('end', prefix, base)
            tag = f'pers_{indi_id.strip("@")}'
            tag_to_id[tag] = indi_id
            w.insert('end', describe(self.individuals[indi_id], show_id=self.show_ids.get()),
                     base + ('person_link', tag))
            w.insert('end', '\n')

        def person_inline(indi_id, prefix='', suffix=''):
            if prefix:
                w.insert('end', prefix)
            tag = f'pers_{indi_id.strip("@")}'
            tag_to_id[tag] = indi_id
            w.insert('end', describe(self.individuals[indi_id],
                                     show_id=self.show_ids.get()),
                     ('person_link', tag))
            if suffix:
                w.insert('end', suffix)

        relationship_link_count = 0

        def relationship_line(rel, path, prefix=''):
            nonlocal relationship_link_count
            tag = f'path_graph_{relationship_link_count}'
            relationship_link_count += 1
            if prefix:
                w.insert('end', prefix)
            w.insert('end', RESULT_RELATIONSHIP.format(rel=rel),
                     ('relationship_link', tag))
            tw.tag_bind(
                tag, '<Button-1>',
                lambda _, p=tuple(path), r=rel: self._show_path_graph(p, r))
            w.insert('end', '\n')

        def common_ancestor_line(ancestor_ids, prefix='', item_prefix='    '):
            if prefix:
                w.insert('end', prefix)
            if not ancestor_ids:
                w.insert('end', RESULT_COMMON_ANCESTOR)
                w.insert('end', RESULT_COMMON_ANCESTOR_NONE)
                w.insert('end', '\n')
                return
            if len(ancestor_ids) == 1:
                w.insert('end', RESULT_COMMON_ANCESTOR)
                person_inline(ancestor_ids[0])
                w.insert('end', '\n')
                return
            w.insert('end', RESULT_COMMON_ANCESTORS + '\n')
            for ancestor_id in ancestor_ids:
                person_inline(ancestor_id, prefix=item_prefix)
                w.insert('end', '\n')

        result_detail_indent = "   "
        result_edge_indent = "       "
        home_edge_indent = "    "

        start = self.individuals[start_id]
        name = self._display_name(start)
        b, d = start.get('birth_year'), start.get('death_year')
        if b and d:
            lifespan = f" ({b}–{d})"
        elif b:
            lifespan = f" (b. {b})"
        elif d:
            lifespan = f" (d. {d})"
        else:
            lifespan = ""
        self._results_header_var.set(name + lifespan)
        self._update_header_label_style()

        nl(RESULT_CLOSEST_MATCHES, bold=True)
        if start['dna_markers']:
            nl(RESULT_DNA_FLAGGED_NOTE)
            for m in start['dna_markers']:
                nl(f"    - {self._format_marker(m)}")
        nl()

        if not results:
            nl(RESULT_NO_DNA_FOUND)
        else:
            hr()
            if self._results_reversed:
                for rank, (dist, path) in enumerate(results, 1):
                    match_id = path[-1][0]
                    rev_path = self._reverse_path(path, self.individuals)
                    m_anc = get_ancestor_depths(
                        match_id, self.individuals, self.families)
                    m_desc = get_descendant_depths(
                        match_id, self.individuals, self.families)
                    rel = describe_relationship(
                        rev_path, self.individuals,
                        ancestors=m_anc, descendants=m_desc,
                        families=self.families)
                    person(match_id,
                           prefix=RESULT_RANK_PREFIX.format(rank=rank), bold=True)
                    relationship_line(
                        rel, rev_path, prefix=result_detail_indent)
                    common_ancestor_line(
                        self._model.find_common_ancestors(
                            rev_path[0][0], rev_path[-1][0]),
                        prefix=result_detail_indent,
                        item_prefix="     ")
                    nl(result_detail_indent + RESULT_PATH)
                    for i, (node_id, edge) in enumerate(rev_path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(RESULT_DNA_MARKERS)
                    for m in self.individuals[match_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()
            else:
                ancestors = get_ancestor_depths(
                    start_id, self.individuals, self.families)
                descendants = get_descendant_depths(
                    start_id, self.individuals, self.families)
                for rank, (dist, path) in enumerate(results, 1):
                    end_id = path[-1][0]
                    person(end_id,
                           prefix=RESULT_RANK_PREFIX.format(rank=rank),
                           bold=True)
                    rel = describe_relationship(
                        path, self.individuals,
                        ancestors=ancestors, descendants=descendants,
                        families=self.families)
                    relationship_line(rel, path, prefix=result_detail_indent)
                    common_ancestor_line(
                        self._model.find_common_ancestors(
                            path[0][0], path[-1][0]),
                        prefix=result_detail_indent,
                        item_prefix="     ")
                    nl(result_detail_indent + RESULT_PATH)
                    for i, (node_id, edge) in enumerate(path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(RESULT_DNA_MARKERS)
                    for m in self.individuals[end_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()

        # Family section
        nl(FAM_SECTION, bold=True)
        family_found = False
        parents, siblings, spouses, children = self._get_family_members(
            start_id)

        if parents:
            family_found = True
            nl(FAM_PARENTS)
            for pid in parents:
                person(pid, prefix="    ")
        if siblings:
            family_found = True
            nl(FAM_SIBLINGS)
            for sib_id in siblings:
                person(sib_id, prefix="    ")
        if spouses:
            family_found = True
            nl(FAM_SPOUSES if len(spouses) > 1 else FAM_SPOUSE)
            for sid in spouses:
                person(sid, prefix="    ")
        if children:
            family_found = True
            nl(FAM_CHILDREN)
            for child_id in children:
                person(child_id, prefix="    ")
        if not family_found:
            nl(FAM_NO_INFO)
        nl()

        # Home person relationship
        home_id = self._home_person_id
        if home_id and home_id != start_id and home_id in self.individuals:
            hr()
            nl(RESULT_PATH_SECTION, bold=True)
            person(home_id, prefix=RESULT_HOME)
            if not home_paths:
                nl(RESULT_NO_HOME_PATH)
            else:
                raw_path = home_paths[0]
                if self._results_reversed:
                    disp_path = self._reverse_path(raw_path, self.individuals)
                    h_anc = get_ancestor_depths(
                        home_id, self.individuals, self.families)
                    h_desc = get_descendant_depths(
                        home_id, self.individuals, self.families)
                    rel = describe_relationship(
                        disp_path, self.individuals,
                        ancestors=h_anc, descendants=h_desc,
                        families=self.families)
                else:
                    disp_path = raw_path
                    ancestors = get_ancestor_depths(
                        start_id, self.individuals, self.families)
                    descendants = get_descendant_depths(
                        start_id, self.individuals, self.families)
                    rel = describe_relationship(
                        disp_path, self.individuals,
                        ancestors=ancestors, descendants=descendants,
                        families=self.families)
                relationship_line(rel, disp_path)
                common_ancestor_line(self._model.find_common_ancestors(
                    disp_path[0][0], disp_path[-1][0]))
                nl(RESULT_PATH)
                for i, (node_id, edge) in enumerate(disp_path):
                    if i == 0:
                        person(node_id, prefix="  ")
                    else:
                        person(node_id, prefix=self._path_edge_prefix(
                            edge, home_edge_indent))
            nl()

        self._reverse_btn.configure(state='normal')
        w.configure(state='disabled')

    def _copy_results(self):
        """Copy the current results text to the clipboard."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _save_results(self):
        """Save the current results text to a user-selected text file."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title=DLG_SAVE_RESULTS,
            defaultextension='.txt',
            filetypes=[
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as results_file:
                results_file.write(text)
                results_file.write('\n')
        except OSError as exc:
            messagebox.showerror(
                ERR_SAVE_GRAPH_TITLE,
                ERR_SAVE_RESULTS_MSG.format(error=exc),
                parent=self.root,
            )

    def _clear_results(self):
        """Clear result output and reset search focus."""
        self.results.configure(state='normal')
        self.results.delete('1.0', 'end')
        self.results.configure(state='disabled')
        self._results_header_var.set('')
        self._update_header_label_style()
        self.search_text.set('')
        self._last_result = None
        self._results_reversed = False
        self._reverse_btn.configure(state='disabled', text=BTN_REVERSE)
        self._kb_focus_search()

    def _format_marker(self, marker):
        """Strip the trailing (@ref@) from a DNA marker string when Show IDs is off."""
        if self.show_ids.get():
            return marker
        return re.sub(r'\s*\(@[^@]+@\)\s*$', '', marker)

    def _clear_person_tags(self, widget):
        """Remove generated person-link tags from a Text-like widget."""
        tw = getattr(widget, '_textbox', widget)
        for tag in tw.tag_names():
            if tag.startswith('pers_') or tag.startswith('path_graph_'):
                tw.tag_delete(tag)

    def _navigate_to(self, indi_id):
        """Select a person in the tree and refresh the results pane for them.

        If the right pane currently shows DNA matches, shows DNA matches for the
        new person.  If it shows a relationship path, finds the path from the new
        person to the same destination.
        """

        # reset "reverse" button and pull in default search parameters
        self._results_reversed = False
        self._reverse_btn.configure(text=BTN_REVERSE)
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return

        kind = self._last_result.get('type') if self._last_result else None

        # for a "path" search, find the path from the originally selected person
        if kind == 'path':
            # to the newly selected person
            start_id = self._last_result['start_id']
            self._last_result = {'type': 'path',
                                 'start_id': start_id, 'end_id': indi_id}

            def _do_path():
                try:
                    paths, truncated = self._model.find_all_paths(
                        start_id, indi_id, top_n, max_depth)
                    self.root.after(0, lambda: self._render_path_results(
                        start_id, indi_id, paths, truncated))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            threading.Thread(target=_do_path, daemon=True).start()
        # for a "DNA" search, find the closest DNA markers to the newly selected person
        else:
            self._active_id = indi_id
            if not self.tree.exists(indi_id):
                self.search_text.set('')
                self.filter_text.set('')
                self.show_flagged_only.set(False)
                self._populate_tree()
            if self.tree.exists(indi_id):
                self.tree.selection_set(indi_id)
                self.tree.see(indi_id)
                self.tree.focus(indi_id)
            else:
                # Person exceeds max_display even with no filters; clear the stale
                # tree selection so action buttons fall back to _active_id.
                self.tree.selection_remove(*self.tree.selection())
            self._last_result = {'type': 'dna_matches', 'start_id': indi_id}

            def _do_dna():
                try:
                    results = bfs_find_dna_matches(
                        indi_id, self.individuals, self.families,
                        top_n=top_n, max_depth=max_depth,
                    )
                    home_paths = None
                    home_id = self._home_person_id
                    if home_id and home_id != indi_id and home_id in self.individuals:
                        home_paths, _ = bfs_find_all_paths(
                            indi_id, home_id, self.individuals, self.families,
                            top_n=1, max_depth=max_depth,
                        )
                    self.root.after(0, lambda: self._render_results(
                        indi_id, results, home_paths=home_paths))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            threading.Thread(target=_do_dna, daemon=True).start()

    def _display_name(self, indi):
        """Return an individual's display name using the configured name order."""
        if self._name_order == 'last_first':
            surname = indi.get('surname', '')
            given = indi.get('given_name', '')
            if surname and given:
                return f"{surname}, {given}"
            if surname:
                return surname
        return indi['name'] or '(unknown)'

    def _get_family_members(self, indi_id):
        """Return (parents, siblings, spouses, children) lists for an individual."""
        indi = self.individuals[indi_id]
        parents, siblings, spouses, children = [], [], [], []
        for fam_id in indi['famc']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            for pid in (fam['husb'], fam['wife']):
                if pid and pid in self.individuals:
                    parents.append(pid)
            for sib_id in fam['chil']:
                if sib_id != indi_id and sib_id in self.individuals:
                    siblings.append(sib_id)
        for fam_id in indi['fams']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            spouse_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            if spouse_id and spouse_id in self.individuals:
                spouses.append(spouse_id)
            for child_id in fam['chil']:
                if child_id in self.individuals:
                    children.append(child_id)
        return parents, siblings, spouses, children
