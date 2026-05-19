#!/usr/bin/env python3
"""
gedcom_gui_results.py

Result rendering, path reversal, person navigation, and family-summary helpers.
"""

import io
import json
import math
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gedcom_display import describe, lifespan
from gedcom_family_tree import (
    EXPANDABLE_TREE_CATEGORIES,
    _nearest_unblocked_column,
    build_family_tree_graph,
    family_tree_expansion_options,
    layout_family_tree,
)
from gedcom_graph_export import canvas_to_png_bytes, canvas_to_svg
from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_theme import get_link_color, ttk_colors
from gedcom_tooltip import CanvasTagTooltip, TextTagTooltip, Tooltip
from gedcom_zoom import bind_zoom_shortcuts


class ResultsMixin:
    """Render search results and handle result-pane navigation."""

    PERSON_BOX_FILL_MALE = '#d9ecff'
    PERSON_BOX_FILL_FEMALE = '#ffe1ec'
    PERSON_BOX_FILL_NEUTRAL = '#f2f2f2'
    PERSON_BOX_TEXT = '#1a1a1a'

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
                'is_path_node': True,
                'is_endpoint': False,
            })
        if layout:
            layout[0]['is_endpoint'] = True
            layout[-1]['is_endpoint'] = True
        return layout

    @staticmethod
    def _centered_graph_offsets(count, step=1.4):
        """Return centered column offsets for expanded graph relatives."""
        if count <= 0:
            return []
        start = -((count - 1) * step) / 2
        return [start + index * step for index in range(count)]

    @classmethod
    def _expanded_path_graph_layout(cls, base_layout, expanded,
                                    family_lookup, coparent_lookup=None):
        """Return path layout plus expanded relatives and extra graph edges."""
        layout = [dict(node) for node in base_layout]
        visible = {node['id'] for node in layout}
        occupied = {
            (node['generation'], round(float(node['column']), 3))
            for node in layout
        }
        by_id = {node['id']: node for node in layout}
        extra_edges = []
        extra_edge_set = set()

        min_spacing = 1.0

        def rebuild_occupied():
            occupied.clear()
            occupied.update({
                (node['generation'], round(float(node['column']), 3))
                for node in layout
            })

        def reserve_same_row_slot(generation, column, protected_id):
            """Move same-row nodes so a spouse can sit adjacent to its partner."""
            protected_ids = (
                set(protected_id)
                if isinstance(protected_id, (set, tuple, list))
                else {protected_id}
            )
            column = round(float(column), 3)
            for _ in range(max(20, len(layout) * 4)):
                conflicts = [
                    node for node in layout
                    if (node['id'] not in protected_ids
                        and node['generation'] == generation
                        and abs(node['column'] - column) < min_spacing)
                ]
                if not conflicts:
                    break
                boundary = min(node['column'] for node in conflicts)
                for node in layout:
                    if (node['id'] not in protected_ids
                            and node['generation'] == generation
                            and node['column'] >= boundary):
                        node['column'] = round(node['column'] + min_spacing, 3)
                rebuild_occupied()

        def reserve_same_row_block(generation, columns, protected_id,
                                   direction=1):
            """Move same-row nodes so a related group can stay contiguous."""
            protected_ids = (
                set(protected_id)
                if isinstance(protected_id, (set, tuple, list))
                else {protected_id}
            )
            columns = [round(float(column), 3) for column in columns]
            if not columns:
                return
            for _ in range(max(20, len(layout) * (len(columns) + 2))):
                conflicts = [
                    node for node in layout
                    if (node['id'] not in protected_ids
                        and node['generation'] == generation
                        and any(abs(node['column'] - column) < min_spacing
                                for column in columns))
                ]
                if not conflicts:
                    break
                if direction < 0:
                    boundary = max(node['column'] for node in conflicts)
                    for node in layout:
                        if (node['id'] not in protected_ids
                                and node['generation'] == generation
                                and node['column'] <= boundary):
                            node['column'] = round(
                                node['column'] - min_spacing, 3)
                else:
                    boundary = min(node['column'] for node in conflicts)
                    for node in layout:
                        if (node['id'] not in protected_ids
                                and node['generation'] == generation
                                and node['column'] >= boundary):
                            node['column'] = round(
                                node['column'] + min_spacing, 3)
                rebuild_occupied()

        def place(generation, column):
            column = round(float(column), 3)
            for _ in range(max(20, len(layout) * 4)):
                if not any(
                    gen == generation and abs(
                        column - used_column) < min_spacing
                    for gen, used_column in occupied
                ):
                    break
                column = round(column + min_spacing, 3)
            occupied.add((generation, column))
            return column

        def enforce_spouse_adjacency():
            for source_id, target_id in visible_spouse_pairs():
                source_node = by_id.get(source_id)
                target_node = by_id.get(target_id)
                if not source_node or not target_node:
                    continue
                if source_node['generation'] != target_node['generation']:
                    continue
                desired_column = (
                    source_node['column'] + min_spacing
                    if target_node['column'] >= source_node['column']
                    else source_node['column'] - min_spacing
                )
                source_anchor = visible_parent_anchor(source_id)
                target_anchor = visible_parent_anchor(target_id)
                if (target_anchor is not None
                        and abs(desired_column - target_anchor) >= 0.001):
                    if source_anchor is not None:
                        continue
                    desired_source_column = (
                        target_node['column'] - min_spacing
                        if source_node['column'] <= target_node['column']
                        else target_node['column'] + min_spacing
                    )
                    if abs(source_node['column']
                           - desired_source_column) < 0.001:
                        continue
                    reserve_same_row_slot(
                        source_node['generation'],
                        round(desired_source_column, 3),
                        {source_id, target_id})
                    source_node['column'] = desired_source_column
                    rebuild_occupied()
                    continue
                if abs(target_node['column'] - desired_column) < 0.001:
                    continue
                reserve_same_row_slot(
                    source_node['generation'], round(desired_column, 3),
                    {source_id, target_id})
                target_node['column'] = desired_column
                rebuild_occupied()

        def relationship_matches_or_unknown(source_id, target_id, category):
            source_members = tuple(family_lookup(source_id).get(category, ()))
            target_members = tuple(family_lookup(target_id).get(category, ()))
            if target_id in source_members or source_id in target_members:
                return True
            if source_members or target_members:
                return False
            return True

        def visible_spouse_ids(source_id):
            spouse_ids = []
            for index in range(1, len(layout)):
                if (layout[index - 1].get('is_path_node')
                        and layout[index].get('is_path_node')
                        and layout[index].get('edge') == 'spouse'):
                    left_id = layout[index - 1]['id']
                    right_id = layout[index]['id']
                    if left_id == source_id:
                        if relationship_matches_or_unknown(
                                left_id, right_id, 'spouses'):
                            spouse_ids.append(right_id)
                    elif right_id == source_id:
                        if relationship_matches_or_unknown(
                                left_id, right_id, 'spouses'):
                            spouse_ids.append(left_id)
            for left_id, right_id, category in extra_edges:
                if category != 'spouses':
                    continue
                if left_id == source_id:
                    spouse_ids.append(right_id)
                elif right_id == source_id:
                    spouse_ids.append(left_id)
            return [
                spouse_id for spouse_id in spouse_ids
                if spouse_id in by_id
            ]

        def visible_spouse_pairs():
            pairs = []
            seen = set()
            for node in layout:
                source_id = node['id']
                for spouse_id in visible_spouse_ids(source_id):
                    edge_key = tuple(sorted((source_id, spouse_id)))
                    if edge_key in seen:
                        continue
                    seen.add(edge_key)
                    pairs.append((source_id, spouse_id))
            return pairs

        def same_row_spouse_ids(source_id):
            source_node = by_id.get(source_id)
            if not source_node:
                return []
            return [
                spouse_id for spouse_id in visible_spouse_ids(source_id)
                if by_id[spouse_id]['generation'] == source_node['generation']
            ]

        def visible_parent_ids(child_id):
            child_node = by_id.get(child_id)
            if not child_node:
                return []
            parent_generation = child_node['generation'] - 1
            parent_ids = []
            seen = set()

            def add_parent(parent_id):
                parent_node = by_id.get(parent_id)
                if not parent_node:
                    return
                if parent_node['generation'] != parent_generation:
                    return
                if parent_id in seen:
                    return
                parent_ids.append(parent_id)
                seen.add(parent_id)

            for index in range(1, len(layout)):
                if (not layout[index - 1].get('is_path_node')
                        or not layout[index].get('is_path_node')):
                    continue
                edge = layout[index].get('edge')
                if edge in ('father', 'mother'):
                    edge_child_id = layout[index - 1]['id']
                    edge_parent_id = layout[index]['id']
                elif edge == 'child':
                    edge_parent_id = layout[index - 1]['id']
                    edge_child_id = layout[index]['id']
                else:
                    continue
                if edge_child_id == child_id:
                    add_parent(edge_parent_id)
            for left_id, right_id, category in extra_edges:
                if category == 'parents' and left_id == child_id:
                    add_parent(right_id)
            for parent_id in tuple(parent_ids):
                for spouse_id in same_row_spouse_ids(parent_id):
                    add_parent(spouse_id)
            return parent_ids

        def visible_parent_anchor(child_id):
            parent_ids = visible_parent_ids(child_id)
            if not parent_ids:
                return None
            return sum(by_id[parent_id]['column']
                       for parent_id in parent_ids) / len(parent_ids)

        def anchored_parent_ids(exclude_child_id=None):
            parent_ids = set()
            for child_id, parent_id, category in extra_edges:
                if category != 'parents':
                    continue
                if child_id == exclude_child_id:
                    continue
                parent_ids.add(parent_id)
            for parent_id in tuple(parent_ids):
                parent_ids.update(same_row_spouse_ids(parent_id))
            return parent_ids

        def nearest_local_parent_anchor(
                child_node, parent_ids, direction, start_column=None):
            parent_generation = child_node['generation'] - 1
            offsets = cls._centered_graph_offsets(len(parent_ids), min_spacing)
            protected_anchors = anchored_parent_ids(child_node['id'])
            candidate = round(
                child_node['column'] if start_column is None else start_column,
                3)
            step = min_spacing / 2
            for _ in range(20):
                desired_columns = [
                    round(candidate + offset, 3)
                    for offset in offsets
                ]
                conflicts = [
                    node for node in layout
                    if (node['id'] in protected_anchors
                        and node['generation'] == parent_generation
                        and any(abs(node['column'] - column) < min_spacing
                                for column in desired_columns))
                ]
                if not conflicts:
                    return candidate, desired_columns
                candidate = round(candidate + direction * step, 3)
            return candidate, [
                round(candidate + offset, 3)
                for offset in offsets
            ]

        def expanded_sibling_ids(source_id):
            sibling_ids = []
            seen = set()
            source_node = by_id.get(source_id)
            if not source_node:
                return sibling_ids
            for left_id, right_id, category in extra_edges:
                if category != 'siblings' or left_id != source_id:
                    continue
                sibling_node = by_id.get(right_id)
                if not sibling_node:
                    continue
                if sibling_node['generation'] != source_node['generation']:
                    continue
                if right_id in seen:
                    continue
                sibling_ids.append(right_id)
                seen.add(right_id)
            return sibling_ids

        def enforce_sibling_adjacency():
            sibling_neighbors = {}
            source_ids = []
            seen_sources = set()
            explicit_sibling_sources = set()

            def add_sibling_edge(source_id, target_id):
                source_node = by_id.get(source_id)
                target_node = by_id.get(target_id)
                if not source_node or not target_node:
                    return
                if source_node['generation'] != target_node['generation']:
                    return
                sibling_neighbors.setdefault(source_id, set()).add(target_id)
                sibling_neighbors.setdefault(target_id, set()).add(source_id)

            def add_source_id(source_id):
                if source_id in seen_sources:
                    return
                source_ids.append(source_id)
                seen_sources.add(source_id)

            for index in range(1, len(layout)):
                previous_node = layout[index - 1]
                current_node = layout[index]
                if (previous_node.get('is_path_node')
                        and current_node.get('is_path_node')
                        and current_node.get('edge') == 'sibling'
                        and relationship_matches_or_unknown(
                            previous_node['id'], current_node['id'],
                            'siblings')):
                    add_sibling_edge(previous_node['id'], current_node['id'])
                    add_source_id(previous_node['id'])
                    add_source_id(current_node['id'])

            for source_id, target_id, category in extra_edges:
                if category != 'siblings':
                    continue
                add_sibling_edge(source_id, target_id)
                explicit_sibling_sources.add(source_id)
                add_source_id(source_id)
            for source_id in source_ids:
                for sibling_id in family_lookup(source_id).get('siblings', ()):
                    if sibling_id in by_id:
                        add_sibling_edge(source_id, sibling_id)
            processed_ids = set()
            for source_id in source_ids:
                source_node = by_id.get(source_id)
                if not source_node:
                    continue
                if source_id in processed_ids:
                    continue
                component_ids = []
                pending = [source_id]
                seen_component = {source_id}
                while pending:
                    current_id = pending.pop(0)
                    current_node = by_id.get(current_id)
                    if (current_node
                            and current_node['generation']
                            == source_node['generation']):
                        component_ids.append(current_id)
                    for sibling_id in sibling_neighbors.get(current_id, ()):
                        if sibling_id in seen_component:
                            continue
                        seen_component.add(sibling_id)
                        pending.append(sibling_id)
                processed_ids.update(component_ids)
                anchor_id = source_id
                if not same_row_spouse_ids(anchor_id):
                    for person_id in sorted(
                            component_ids,
                            key=lambda item: by_id[item]['column']):
                        if same_row_spouse_ids(person_id):
                            anchor_id = person_id
                            break
                source_node = by_id.get(anchor_id)
                if not source_node:
                    continue
                sibling_ids = [
                    person_id for person_id in component_ids
                    if person_id != anchor_id
                ]
                if not sibling_ids:
                    continue
                spouse_ids = same_row_spouse_ids(anchor_id)
                spouse_columns = [
                    by_id[spouse_id]['column'] for spouse_id in spouse_ids
                ]
                sibling_columns = [
                    by_id[sibling_id]['column'] for sibling_id in sibling_ids
                ]
                left_sibling_count = sum(
                    1 for column in sibling_columns
                    if column < source_node['column'])
                right_sibling_count = sum(
                    1 for column in sibling_columns
                    if column > source_node['column'])
                is_explicit_source = source_id in explicit_sibling_sources
                if not is_explicit_source and left_sibling_count and not right_sibling_count:
                    direction = -1
                elif not is_explicit_source and right_sibling_count and not left_sibling_count:
                    direction = 1
                elif any(column < source_node['column']
                         for column in spouse_columns):
                    direction = 1
                elif any(column > source_node['column']
                         for column in spouse_columns):
                    direction = -1
                else:
                    direction = (
                        1 if right_sibling_count >= left_sibling_count else -1
                    )
                sibling_ids = sorted(
                    sibling_ids,
                    key=lambda person_id: by_id[person_id]['column'],
                    reverse=direction < 0,
                )
                desired_by_id = {}
                protected_ids = set(sibling_ids) | {
                    source_id} | set(spouse_ids)
                block_columns = []
                first_gap = (
                    min_spacing * 1.25
                    if spouse_ids and len(sibling_ids) == 1
                    else min_spacing
                )
                same_side_spouse_columns = [
                    column for column in spouse_columns
                    if ((direction > 0 and column > source_node['column'])
                        or (direction < 0 and column < source_node['column']))
                ]
                if same_side_spouse_columns:
                    spouse_edge_column = (
                        max(same_side_spouse_columns)
                        if direction > 0 else min(same_side_spouse_columns)
                    )
                    column = round(
                        spouse_edge_column + direction * min_spacing, 3)
                else:
                    column = round(
                        source_node['column'] + direction * first_gap, 3)
                for sibling_id in sibling_ids:
                    desired_by_id[sibling_id] = column
                    block_columns.append(column)
                    sibling_spouse_ids = [
                        spouse_id for spouse_id in same_row_spouse_ids(
                            sibling_id)
                        if spouse_id != source_id
                    ]
                    protected_ids.update(sibling_spouse_ids)
                    column = round(column + direction * min_spacing, 3)
                    for spouse_id in sibling_spouse_ids:
                        desired_by_id[spouse_id] = column
                        block_columns.append(column)
                        column = round(column + direction * min_spacing, 3)
                reserve_same_row_block(
                    source_node['generation'], block_columns, protected_ids,
                    direction)
                for target_id, desired_column in desired_by_id.items():
                    by_id[target_id]['column'] = desired_column
                rebuild_occupied()

        def visible_child_ids(source_id):
            child_ids = []
            spouse_ids = visible_spouse_ids(source_id)

            def add_path_child(parent_id):
                for index in range(1, len(layout)):
                    if (not layout[index - 1].get('is_path_node')
                            or not layout[index].get('is_path_node')):
                        continue
                    edge = layout[index].get('edge')
                    if edge in ('father', 'mother'):
                        edge_parent_id = layout[index]['id']
                        edge_child_id = layout[index - 1]['id']
                    elif edge == 'child':
                        edge_parent_id = layout[index - 1]['id']
                        edge_child_id = layout[index]['id']
                    else:
                        continue
                    if edge_parent_id == parent_id:
                        child_ids.append(edge_child_id)

            def add_extra_child(parent_id):
                for left_id, right_id, category in extra_edges:
                    if category == 'children' and left_id == parent_id:
                        child_ids.append(right_id)
                    elif category == 'parents' and right_id == parent_id:
                        child_ids.append(left_id)

            add_path_child(source_id)
            add_extra_child(source_id)
            for spouse_id in spouse_ids:
                add_path_child(spouse_id)
                add_extra_child(spouse_id)
            visible_children = []
            seen = set()
            for child_id in child_ids:
                if child_id in by_id and child_id not in seen:
                    visible_children.append(child_id)
                    seen.add(child_id)
            return visible_children

        def expanded_parent_ids(child_id):
            child_node = by_id.get(child_id)
            if not child_node:
                return []
            parent_generation = child_node['generation'] - 1
            parent_ids = []
            seen = set()
            for left_id, right_id, category in extra_edges:
                if category != 'parents' or left_id != child_id:
                    continue
                parent_node = by_id.get(right_id)
                if not parent_node:
                    continue
                if parent_node['generation'] != parent_generation:
                    continue
                if right_id in seen:
                    continue
                parent_ids.append(right_id)
                seen.add(right_id)
            for parent_id in tuple(parent_ids):
                for spouse_id in same_row_spouse_ids(parent_id):
                    spouse_node = by_id.get(spouse_id)
                    if not spouse_node:
                        continue
                    if spouse_node['generation'] != parent_generation:
                        continue
                    if spouse_id in seen:
                        continue
                    parent_ids.append(spouse_id)
                    seen.add(spouse_id)
            return parent_ids

        def enforce_parent_alignment():
            processed_child_ids = set()
            for child_id, _parent_id, category in extra_edges:
                if category != 'parents' or child_id in processed_child_ids:
                    continue
                processed_child_ids.add(child_id)
                child_node = by_id.get(child_id)
                if not child_node:
                    continue
                parent_ids = expanded_parent_ids(child_id)
                if not parent_ids:
                    continue
                parent_ids = sorted(
                    parent_ids,
                    key=lambda parent_id: by_id[parent_id]['column'],
                )
                parent_generation = child_node['generation'] - 1
                offsets = cls._centered_graph_offsets(
                    len(parent_ids), min_spacing)
                desired_columns = [
                    round(child_node['column'] + offset, 3)
                    for offset in offsets
                ]
                protected_ids = set(parent_ids) | {child_id}
                block_conflicts = [
                    node for node in layout
                    if (node['id'] not in protected_ids
                        and node['generation'] == parent_generation
                        and any(abs(node['column'] - column) < min_spacing
                                for column in desired_columns))
                ]
                if block_conflicts:
                    conflict_center = (
                        sum(node['column'] for node in block_conflicts)
                        / len(block_conflicts)
                    )
                    direction = (
                        1 if conflict_center >= child_node['column'] else -1
                    )
                    reserve_same_row_block(
                        parent_generation, desired_columns, protected_ids,
                        direction)
                for parent_id, desired_column in zip(
                        parent_ids, desired_columns):
                    by_id[parent_id]['column'] = desired_column
                rebuild_occupied()

        def enforce_child_alignment():
            processed_parent_groups = set()
            for source_node in sorted(
                    layout,
                    key=lambda node: (node['generation'], node['column'])):
                source_id = source_node['id']
                child_generation = source_node['generation'] + 1
                spouse_ids = [
                    spouse_id for spouse_id in visible_spouse_ids(source_id)
                    if by_id[spouse_id]['generation']
                    == source_node['generation']
                ]
                parent_group = frozenset([source_id] + spouse_ids[:1])
                if parent_group in processed_parent_groups:
                    continue
                processed_parent_groups.add(parent_group)
                child_ids = [
                    child_id for child_id in visible_child_ids(source_id)
                    if by_id[child_id]['generation'] == child_generation
                ]
                if not child_ids:
                    continue
                spouse_columns = [
                    by_id[spouse_id]['column']
                    for spouse_id in spouse_ids
                ]
                base_column = (
                    (source_node['column'] + spouse_columns[0]) / 2
                    if spouse_columns else source_node['column']
                )
                protected_ids = set(child_ids) | {source_id} | set(spouse_ids)
                protected_spouse_ids = {
                    spouse_id
                    for child_id in child_ids
                    for spouse_id in visible_spouse_ids(child_id)
                    if spouse_id in by_id and spouse_id not in child_ids
                }
                protected_ids.update(protected_spouse_ids)
                offsets = cls._centered_graph_offsets(len(child_ids))
                desired_columns = [
                    round(base_column + offset, 3)
                    for offset in offsets
                ]
                block_conflicts = [
                    node for node in layout
                    if (node['id'] not in protected_ids
                        and node['generation'] == child_generation
                        and any(abs(node['column'] - column) < min_spacing
                                for column in desired_columns))
                ]
                if block_conflicts:
                    conflict_center = (
                        sum(node['column'] for node in block_conflicts)
                        / len(block_conflicts)
                    )
                    direction = 1 if conflict_center >= base_column else -1
                    reserve_same_row_block(
                        child_generation, desired_columns, protected_ids,
                        direction)

                for child_id, desired_column in zip(child_ids, desired_columns):
                    desired_column = _nearest_unblocked_column(
                        desired_column,
                        [
                            by_id[spouse_id]['column']
                            for spouse_id in protected_spouse_ids
                        ])
                    reserve_same_row_slot(
                        child_generation, desired_column, protected_ids)
                    by_id[child_id]['column'] = desired_column
                    rebuild_occupied()

        def enforce_expanded_child_alignment():
            processed_parent_groups = set()
            child_sources = []
            seen_sources = set()
            for source_id, _child_id, category in extra_edges:
                if category != 'children' or source_id in seen_sources:
                    continue
                child_sources.append(source_id)
                seen_sources.add(source_id)
            for source_id in child_sources:
                source_node = by_id.get(source_id)
                if not source_node:
                    continue
                child_generation = source_node['generation'] + 1
                spouse_ids = [
                    spouse_id for spouse_id in visible_spouse_ids(source_id)
                    if by_id[spouse_id]['generation']
                    == source_node['generation']
                ]
                parent_group = frozenset([source_id] + spouse_ids[:1])
                if parent_group in processed_parent_groups:
                    continue
                processed_parent_groups.add(parent_group)
                child_ids = [
                    child_id for child_id in visible_child_ids(source_id)
                    if by_id[child_id]['generation'] == child_generation
                ]
                if not child_ids:
                    continue
                spouse_columns = [
                    by_id[spouse_id]['column']
                    for spouse_id in spouse_ids
                ]
                base_column = (
                    (source_node['column'] + spouse_columns[0]) / 2
                    if spouse_columns else source_node['column']
                )
                offsets = cls._centered_graph_offsets(len(child_ids))
                desired_columns = [
                    round(base_column + offset, 3)
                    for offset in offsets
                ]
                protected_ids = set(child_ids) | {source_id} | set(spouse_ids)
                block_conflicts = [
                    node for node in layout
                    if (node['id'] not in protected_ids
                        and node['generation'] == child_generation
                        and any(abs(node['column'] - column) < min_spacing
                                for column in desired_columns))
                ]
                if block_conflicts and not source_node.get('is_path_node'):
                    conflict_group_size = max(
                        (
                            len([
                                child_id for child_id in visible_child_ids(
                                    node.get('expanded_from'))
                                if (child_id in by_id
                                    and by_id[child_id]['generation']
                                    == child_generation)
                            ])
                            if node.get('expanded_category') == 'children'
                            and node.get('expanded_from') else 1
                        )
                        for node in block_conflicts
                    )
                    if len(child_ids) < conflict_group_size:
                        conflict_center = (
                            sum(node['column'] for node in block_conflicts)
                            / len(block_conflicts)
                        )
                        direction = (
                            1 if conflict_center >= base_column else -1
                        )
                        parent_ids = {source_id} | set(spouse_ids)
                        parent_offsets = {
                            parent_id: round(
                                by_id[parent_id]['column'] - base_column, 3)
                            for parent_id in parent_ids
                        }

                        def child_columns_are_open(anchor):
                            return all(
                                not (
                                    node['id'] not in protected_ids
                                    and node['generation'] == child_generation
                                    and any(
                                        abs(node['column']
                                            - round(anchor + offset, 3))
                                        < min_spacing
                                        for offset in offsets
                                    )
                                )
                                for node in layout
                            )

                        shifted_base = None
                        for step in range(1, 41):
                            candidate = round(
                                base_column
                                + direction * step * min_spacing, 3)
                            if child_columns_are_open(candidate):
                                shifted_base = candidate
                                break
                        if shifted_base is not None:
                            desired_parent_columns = [
                                round(shifted_base + offset, 3)
                                for offset in parent_offsets.values()
                            ]
                            reserve_same_row_block(
                                source_node['generation'],
                                desired_parent_columns,
                                parent_ids | set(child_ids),
                                direction)
                            for parent_id, parent_offset in (
                                    parent_offsets.items()):
                                by_id[parent_id]['column'] = round(
                                    shifted_base + parent_offset, 3)
                            rebuild_occupied()
                            spouse_columns = [
                                by_id[spouse_id]['column']
                                for spouse_id in spouse_ids
                            ]
                            base_column = (
                                (source_node['column'] + spouse_columns[0]) / 2
                                if spouse_columns else source_node['column']
                            )
                            desired_columns = [
                                round(base_column + offset, 3)
                                for offset in offsets
                            ]
                            block_conflicts = [
                                node for node in layout
                                if (node['id'] not in protected_ids
                                    and node['generation'] == child_generation
                                    and any(
                                        abs(node['column'] - column)
                                        < min_spacing
                                        for column in desired_columns))
                            ]
                if block_conflicts:
                    conflict_center = (
                        sum(node['column'] for node in block_conflicts)
                        / len(block_conflicts)
                    )
                    direction = 1 if conflict_center >= base_column else -1
                    reserve_same_row_block(
                        child_generation, desired_columns, protected_ids,
                        direction)
                for child_id, desired_column in zip(
                        child_ids, desired_columns):
                    by_id[child_id]['column'] = desired_column
                rebuild_occupied()

        def enforce_vertical_path_components():
            neighbors = {}
            for index in range(1, len(layout)):
                previous_node = layout[index - 1]
                current_node = layout[index]
                if (not previous_node.get('is_path_node')
                        or not current_node.get('is_path_node')):
                    continue
                edge = current_node.get('edge')
                if edge in ('father', 'mother'):
                    parent_node = current_node
                    child_node = previous_node
                elif edge == 'child':
                    parent_node = previous_node
                    child_node = current_node
                else:
                    continue
                if len(visible_parent_ids(child_node['id'])) != 1:
                    continue
                if same_row_spouse_ids(child_node['id']):
                    continue
                neighbors.setdefault(parent_node['id'], set()).add(
                    child_node['id'])
                neighbors.setdefault(child_node['id'], set()).add(
                    parent_node['id'])

            visited = set()
            for start_id in list(neighbors):
                if start_id in visited:
                    continue
                component_ids = []
                pending = [start_id]
                visited.add(start_id)
                while pending:
                    current_id = pending.pop()
                    if current_id in by_id:
                        component_ids.append(current_id)
                    for next_id in neighbors.get(current_id, ()):
                        if next_id in visited:
                            continue
                        visited.add(next_id)
                        pending.append(next_id)
                if len(component_ids) < 2:
                    continue
                current_columns = [
                    by_id[node_id]['column'] for node_id in component_ids
                ]
                component_set = set(component_ids)

                def column_is_open(column):
                    return all(
                        not (
                            node['id'] not in component_set
                            and node['generation'] == by_id[node_id]['generation']
                            and abs(node['column'] - column) < min_spacing
                        )
                        for node_id in component_ids
                        for node in layout
                    )

                ordered_candidates = sorted(
                    set(round(column, 3) for column in current_columns),
                    key=lambda column: (
                        current_columns.count(column),
                        -abs(column - (
                            sum(current_columns) / len(current_columns))),
                    ),
                    reverse=True,
                )
                target_column = None
                for candidate in ordered_candidates:
                    if column_is_open(candidate):
                        target_column = candidate
                        break
                if target_column is None:
                    center = sum(current_columns) / len(current_columns)
                    for step in range(0, 41):
                        offsets = [0] if step == 0 else [step / 2, -step / 2]
                        for offset in offsets:
                            candidate = round(center + offset, 3)
                            if column_is_open(candidate):
                                target_column = candidate
                                break
                        if target_column is not None:
                            break
                if target_column is None:
                    continue
                for node_id in component_ids:
                    by_id[node_id]['column'] = target_column
                rebuild_occupied()

        def enforce_two_parent_path_child_alignment():
            def path_parent_ids(child_id):
                parents = []
                child_node = by_id.get(child_id)
                if not child_node:
                    return parents
                parent_generation = child_node['generation'] - 1
                for index in range(1, len(layout)):
                    previous_node = layout[index - 1]
                    current_node = layout[index]
                    if (not previous_node.get('is_path_node')
                            or not current_node.get('is_path_node')):
                        continue
                    edge = current_node.get('edge')
                    if edge in ('father', 'mother'):
                        edge_child_id = previous_node['id']
                        edge_parent_id = current_node['id']
                    elif edge == 'child':
                        edge_parent_id = previous_node['id']
                        edge_child_id = current_node['id']
                    else:
                        continue
                    if edge_child_id != child_id:
                        continue
                    parent_node = by_id.get(edge_parent_id)
                    if (parent_node
                            and parent_node['generation']
                            == parent_generation):
                        parents.append(edge_parent_id)
                return parents

            def two_parent_branch_ids(child_id, parent_ids):
                branch_ids = {child_id, *parent_ids}
                pending = list(parent_ids)
                while pending:
                    current_id = pending.pop()
                    for parent_id in path_parent_ids(current_id):
                        if parent_id in branch_ids:
                            continue
                        if len(visible_parent_ids(current_id)) != 1:
                            continue
                        branch_ids.add(parent_id)
                        pending.append(parent_id)
                return branch_ids

            for index in range(1, len(layout)):
                previous_node = layout[index - 1]
                current_node = layout[index]
                if (not previous_node.get('is_path_node')
                        or not current_node.get('is_path_node')):
                    continue
                edge = current_node.get('edge')
                if edge in ('father', 'mother'):
                    child_node = previous_node
                elif edge == 'child':
                    child_node = current_node
                else:
                    continue
                parent_ids = visible_parent_ids(child_node['id'])
                if len(parent_ids) < 2:
                    continue
                parent_anchor = round(
                    sum(by_id[parent_id]['column']
                        for parent_id in parent_ids) / len(parent_ids),
                    3)
                branch_ids = two_parent_branch_ids(
                    child_node['id'], parent_ids)
                branch_offsets = {
                    node_id: round(by_id[node_id]['column'] - parent_anchor, 3)
                    for node_id in branch_ids
                }
                branch_offsets[child_node['id']] = 0

                def branch_column_is_open(anchor_column):
                    for node_id, offset in branch_offsets.items():
                        target_column = round(anchor_column + offset, 3)
                        generation = by_id[node_id]['generation']
                        for node in layout:
                            if node['id'] in branch_ids:
                                continue
                            if node['generation'] != generation:
                                continue
                            if abs(node['column'] - target_column) < min_spacing:
                                return False
                    return True

                desired_column = parent_anchor
                if not branch_column_is_open(desired_column):
                    target_column = None
                    for step in range(1, 81):
                        for direction in (1, -1):
                            candidate = round(
                                desired_column
                                + direction * step * min_spacing, 3)
                            if branch_column_is_open(candidate):
                                target_column = candidate
                                break
                        if target_column is not None:
                            break
                    if target_column is None:
                        continue
                    delta = round(target_column - parent_anchor, 3)
                    for node_id in branch_ids:
                        by_id[node_id]['column'] = round(
                            by_id[node_id]['column'] + delta, 3)
                    rebuild_occupied()
                    continue

                if abs(child_node['column'] - desired_column) < 0.001:
                    continue
                reserve_same_row_slot(
                    child_node['generation'], desired_column,
                    {child_node['id']} | set(parent_ids))
                child_node['column'] = desired_column
                rebuild_occupied()

        def enforce_vertical_path_edges():
            for index in range(1, len(layout)):
                previous_node = layout[index - 1]
                current_node = layout[index]
                if (not previous_node.get('is_path_node')
                        or not current_node.get('is_path_node')):
                    continue
                edge = current_node.get('edge')
                if edge in ('father', 'mother'):
                    parent_node = current_node
                    child_node = previous_node
                elif edge == 'child':
                    parent_node = previous_node
                    child_node = current_node
                else:
                    continue
                parent_ids = visible_parent_ids(child_node['id'])
                child_spouse_ids = same_row_spouse_ids(child_node['id'])
                if len(parent_ids) == 1 and child_spouse_ids:
                    parent_anchor = visible_parent_anchor(child_node['id'])
                    spouse_columns = [
                        by_id[spouse_id]['column']
                        for spouse_id in child_spouse_ids
                    ]
                    spouse_center = sum(spouse_columns) / len(spouse_columns)
                    direction = (
                        1 if spouse_center < child_node['column'] else -1
                    )
                    local_start = (
                        max(spouse_columns) + min_spacing
                        if direction > 0 else
                        min(spouse_columns) - min_spacing
                    )
                    local_anchor, desired_parent_columns = (
                        nearest_local_parent_anchor(
                            child_node, parent_ids, direction, local_start)
                    )
                    if (parent_anchor is not None
                            and abs(parent_anchor - local_anchor)
                            > min_spacing):
                        parent_generation = child_node['generation'] - 1
                        protected_ids = (
                            set(parent_ids)
                            | {child_node['id']}
                            | anchored_parent_ids(child_node['id'])
                        )
                        reserve_same_row_block(
                            parent_generation, desired_parent_columns,
                            protected_ids, direction)
                        for parent_id, desired_parent_column in zip(
                                sorted(
                                    parent_ids,
                                    key=lambda item: by_id[item]['column']),
                                desired_parent_columns):
                            by_id[parent_id]['column'] = desired_parent_column
                        reserve_same_row_slot(
                            child_node['generation'], local_anchor,
                            {child_node['id']} | set(child_spouse_ids))
                        child_node['column'] = local_anchor
                        rebuild_occupied()
                        continue
                if parent_node['column'] == child_node['column']:
                    continue
                desired_column = visible_parent_anchor(child_node['id'])
                if desired_column is None:
                    desired_column = parent_node['column']
                conflicts = [
                    node for node in layout
                    if (node['id'] not in {child_node['id'], parent_node['id']}
                        and node['generation'] == child_node['generation']
                        and abs(node['column'] - desired_column) < min_spacing)
                ]
                if conflicts and not same_row_spouse_ids(parent_node['id']):
                    target_node = parent_node
                    desired_column = child_node['column']
                else:
                    target_node = child_node
                reserve_same_row_slot(
                    target_node['generation'], round(desired_column, 3),
                    {target_node['id'], parent_node['id']})
                target_node['column'] = desired_column
                rebuild_occupied()

        def enforce_two_parent_path_parent_alignment():
            def path_parent_ids(child_id):
                parents = []
                child_node = by_id.get(child_id)
                if not child_node:
                    return parents
                parent_generation = child_node['generation'] - 1
                for index in range(1, len(layout)):
                    previous_node = layout[index - 1]
                    current_node = layout[index]
                    if (not previous_node.get('is_path_node')
                            or not current_node.get('is_path_node')):
                        continue
                    edge = current_node.get('edge')
                    if edge in ('father', 'mother'):
                        edge_child_id = previous_node['id']
                        edge_parent_id = current_node['id']
                    elif edge == 'child':
                        edge_parent_id = previous_node['id']
                        edge_child_id = current_node['id']
                    else:
                        continue
                    if edge_child_id != child_id:
                        continue
                    parent_node = by_id.get(edge_parent_id)
                    if (parent_node
                            and parent_node['generation']
                            == parent_generation):
                        parents.append(edge_parent_id)
                return parents

            def branch_parent_ids(child_id, parent_ids):
                branch_ids = set(parent_ids)
                pending = list(parent_ids)
                while pending:
                    current_id = pending.pop()
                    for parent_id in path_parent_ids(current_id):
                        if parent_id in branch_ids:
                            continue
                        if len(visible_parent_ids(current_id)) != 1:
                            continue
                        branch_ids.add(parent_id)
                        pending.append(parent_id)
                return branch_ids

            for index in range(1, len(layout)):
                previous_node = layout[index - 1]
                current_node = layout[index]
                if (not previous_node.get('is_path_node')
                        or not current_node.get('is_path_node')):
                    continue
                edge = current_node.get('edge')
                if edge in ('father', 'mother'):
                    child_node = previous_node
                elif edge == 'child':
                    child_node = current_node
                else:
                    continue
                parent_ids = visible_parent_ids(child_node['id'])
                if len(parent_ids) < 2:
                    continue
                parent_anchor = round(
                    sum(by_id[parent_id]['column']
                        for parent_id in parent_ids) / len(parent_ids),
                    3)
                delta = round(child_node['column'] - parent_anchor, 3)
                if abs(delta) < 0.001:
                    continue
                branch_ids = branch_parent_ids(child_node['id'], parent_ids)
                protected_ids = branch_ids | {child_node['id']}
                direction = 1 if delta >= 0 else -1
                desired_by_generation = {}
                for node_id in branch_ids:
                    node = by_id[node_id]
                    desired_by_generation.setdefault(
                        node['generation'], []).append(
                            round(node['column'] + delta, 3))
                for generation, desired_columns in desired_by_generation.items():
                    reserve_same_row_block(
                        generation, desired_columns, protected_ids, direction)
                for node_id in branch_ids:
                    by_id[node_id]['column'] = round(
                        by_id[node_id]['column'] + delta, 3)
                rebuild_occupied()

        def compact_sibling_only_gaps():
            def graph_edges():
                for index in range(1, len(layout)):
                    previous_node = layout[index - 1]
                    current_node = layout[index]
                    if (not previous_node.get('is_path_node')
                            or not current_node.get('is_path_node')):
                        continue
                    yield (
                        previous_node['id'], current_node['id'],
                        current_node.get('edge'))
                yield from extra_edges

            def edge_crosses_gap(source_id, target_id, left_col, right_col):
                source_node = by_id.get(source_id)
                target_node = by_id.get(target_id)
                if not source_node or not target_node:
                    return False
                source_col = source_node['column']
                target_col = target_node['column']
                return (
                    (source_col <= left_col and target_col >= right_col)
                    or (target_col <= left_col and source_col >= right_col)
                )

            target_gap = min_spacing * 3
            for _ in range(20):
                columns = sorted({
                    round(float(node['column']), 3)
                    for node in layout
                })
                if len(columns) < 2:
                    return
                gaps = [
                    (round(columns[index + 1] - columns[index], 3),
                     columns[index], columns[index + 1])
                    for index in range(len(columns) - 1)
                ]
                gap, left_col, right_col = max(
                    gaps, key=lambda item: item[0])
                if gap <= target_gap:
                    return
                crossing_edges = [
                    category for source_id, target_id, category in graph_edges()
                    if edge_crosses_gap(source_id, target_id, left_col, right_col)
                ]
                if crossing_edges and any(
                        category != 'sibling' for category in crossing_edges):
                    return
                left_nodes = [
                    node for node in layout
                    if node['column'] <= left_col
                ]
                right_nodes = [
                    node for node in layout
                    if node['column'] >= right_col
                ]
                if not left_nodes or not right_nodes:
                    return
                safe_shift = gap - target_gap
                for right_node in right_nodes:
                    same_generation_left = [
                        node for node in left_nodes
                        if node['generation'] == right_node['generation']
                    ]
                    if not same_generation_left:
                        continue
                    nearest_left = max(
                        node['column'] for node in same_generation_left)
                    safe_shift = min(
                        safe_shift,
                        right_node['column'] - nearest_left - min_spacing)
                if safe_shift <= 0.001:
                    return
                shift = round(safe_shift, 3)
                for node in right_nodes:
                    node['column'] = round(node['column'] - shift, 3)
                rebuild_occupied()

        def enforce_unexpanded_path_child_alignment():
            """Center simple path children without rearranging other path nodes."""
            for index in range(1, len(layout)):
                previous_node = layout[index - 1]
                current_node = layout[index]
                if (not previous_node.get('is_path_node')
                        or not current_node.get('is_path_node')):
                    continue
                edge = current_node.get('edge')
                if edge in ('father', 'mother'):
                    child_node = previous_node
                elif edge == 'child':
                    child_node = current_node
                else:
                    continue

                parent_ids = visible_parent_ids(child_node['id'])
                if len(parent_ids) < 2:
                    continue
                desired_column = round(
                    sum(by_id[parent_id]['column']
                        for parent_id in parent_ids) / len(parent_ids),
                    3)
                if abs(child_node['column'] - desired_column) < 0.001:
                    continue

                child_spouse_ids = set(same_row_spouse_ids(child_node['id']))
                protected_ids = (
                    {child_node['id']}
                    | child_spouse_ids
                    | set(parent_ids)
                )
                path_conflicts = [
                    node for node in layout
                    if (node['id'] not in protected_ids
                        and node.get('is_path_node')
                        and node['generation'] == child_node['generation']
                        and abs(node['column'] - desired_column) < min_spacing)
                ]
                if path_conflicts:
                    continue

                reserve_same_row_slot(
                    child_node['generation'], desired_column, protected_ids)
                child_node['column'] = desired_column
                rebuild_occupied()

        for source_id, category in expanded:
            source = by_id.get(source_id)
            if not source:
                continue
            members = [
                member_id for member_id in family_lookup(source_id).get(
                    category, ())
                if member_id and member_id != source_id
            ]
            coparents = []
            if category == 'children' and coparent_lookup:
                coparents = [
                    parent_id for parent_id in coparent_lookup(
                        source_id, members)
                    if parent_id and parent_id != source_id
                ]
                hidden_coparents = [
                    parent_id for parent_id in coparents
                    if parent_id not in visible
                ]
                offsets = [
                    (index + 1) * min_spacing
                    for index in range(len(hidden_coparents))
                ]
                for parent_id, offset in zip(hidden_coparents, offsets):
                    desired_column = round(source['column'] + offset, 3)
                    reserve_same_row_slot(
                        source['generation'], desired_column, source_id)
                    column = place(source['generation'], desired_column)
                    node = {
                        'id': parent_id,
                        'edge': 'spouse',
                        'generation': source['generation'],
                        'column': column,
                        'index': len(layout),
                        'is_path_node': False,
                        'is_endpoint': False,
                        'expanded_from': source_id,
                        'expanded_category': 'spouses',
                    }
                    layout.append(node)
                    by_id[parent_id] = node
                    visible.add(parent_id)
                for parent_id in coparents:
                    if parent_id in visible:
                        edge = (source_id, parent_id, 'spouses')
                        if edge not in extra_edge_set:
                            extra_edges.append(edge)
                            extra_edge_set.add(edge)
            elif category == 'parents' and coparent_lookup:
                visible_parents = set(members)
                for parent_id in members:
                    for other_parent_id in coparent_lookup(
                            parent_id, (source_id,)):
                        if other_parent_id not in visible_parents:
                            continue
                        edge = (parent_id, other_parent_id, 'spouses')
                        reverse_edge = (
                            other_parent_id, parent_id, 'spouses')
                        if (edge not in extra_edge_set
                                and reverse_edge not in extra_edge_set):
                            extra_edges.append(edge)
                            extra_edge_set.add(edge)

            hidden = [member_id for member_id in members
                      if member_id not in visible]
            parent_columns = {}
            parent_protected = {}
            child_columns = {}
            sibling_columns = {}
            if category == 'parents':
                generation = source['generation'] - 1
                offsets = cls._centered_graph_offsets(len(hidden), min_spacing)
                if coparent_lookup:
                    for parent_id in hidden:
                        for other_parent_id in coparent_lookup(
                                parent_id, (source_id,)):
                            other_parent = by_id.get(other_parent_id)
                            if not other_parent:
                                continue
                            if other_parent['generation'] != generation:
                                continue
                            pair_offset = min_spacing / 2
                            if other_parent['column'] <= source['column']:
                                other_column = round(
                                    source['column'] - pair_offset, 3)
                                parent_column = round(
                                    source['column'] + pair_offset, 3)
                            else:
                                other_column = round(
                                    source['column'] + pair_offset, 3)
                                parent_column = round(
                                    source['column'] - pair_offset, 3)
                            reserve_same_row_slot(
                                generation, other_column,
                                {other_parent_id, source_id})
                            other_parent['column'] = other_column
                            rebuild_occupied()
                            parent_columns[parent_id] = parent_column
                            parent_protected[parent_id] = other_parent_id
                            break
                desired_parent_columns = [
                    parent_columns.get(
                        parent_id,
                        round(source['column'] + offset, 3),
                    )
                    for parent_id, offset in zip(hidden, offsets)
                ]
                parent_block_ids = (
                    {source_id}
                    | set(hidden)
                    | {
                        protected_id for protected_id in parent_protected.values()
                        if protected_id
                    }
                )
                if desired_parent_columns:
                    block_center = sum(desired_parent_columns) / len(
                        desired_parent_columns)
                    direction = 1 if block_center >= source['column'] else -1
                    reserve_same_row_block(
                        generation, desired_parent_columns,
                        parent_block_ids, direction)
            elif category == 'children':
                generation = source['generation'] + 1
                visible_coparents = [
                    by_id[parent_id] for parent_id in coparents
                    if parent_id in by_id
                ]
                base_column = (
                    (source['column'] + visible_coparents[0]['column']) / 2
                    if visible_coparents else source['column']
                )
                offsets = cls._centered_graph_offsets(len(members))
                for member_id, offset in zip(members, offsets):
                    desired_column = round(base_column + offset, 3)
                    if member_id in by_id:
                        member = by_id[member_id]
                        if member['generation'] == generation:
                            reserve_same_row_slot(
                                generation, desired_column,
                                {member_id, source_id})
                            member['column'] = desired_column
                            rebuild_occupied()
                    else:
                        child_columns[member_id] = desired_column
                offsets = [0] * len(hidden)
            elif category == 'spouses':
                generation = source['generation']
                offsets = [
                    (index + 1) * min_spacing
                    for index in range(len(hidden))
                ]
                base_column = source['column']
            elif category == 'siblings':
                generation = source['generation']
                spouse_ids_same_row = same_row_spouse_ids(source_id)
                same_row_spouse_columns = [
                    by_id[spouse_id]['column']
                    for spouse_id in spouse_ids_same_row
                ]
                sibling_direction = (
                    1 if any(column < source['column']
                             for column in same_row_spouse_columns)
                    else -1
                )
                if sibling_direction < 0:
                    first_gap = (
                        min_spacing * 1.25
                        if spouse_ids_same_row and len(hidden) == 1
                        else min_spacing
                    )
                    offsets = [
                        -(first_gap + index * min_spacing)
                        for index in range(len(hidden) - 1, -1, -1)
                    ]
                else:
                    first_gap = (
                        min_spacing * 1.25
                        if spouse_ids_same_row and len(hidden) == 1
                        else min_spacing
                    )
                    offsets = [
                        first_gap + index * min_spacing
                        for index in range(len(hidden))
                    ]
                base_column = source['column']
                desired_columns = [
                    round(base_column + offset, 3)
                    for offset in offsets
                ]
                sibling_columns = dict(zip(hidden, desired_columns))
                protected_ids = (
                    {source_id}
                    | set(spouse_ids_same_row)
                    | set(hidden)
                )
                reserve_same_row_block(
                    generation, desired_columns, protected_ids,
                    sibling_direction)
            else:
                generation = source['generation']
                offsets = [-(index + 1) * 1.4 for index in range(len(hidden))]
                base_column = source['column']
            if category == 'parents':
                base_column = source['column']

            for member_id, offset in zip(hidden, offsets):
                desired_column = parent_columns.get(
                    member_id, child_columns.get(member_id, sibling_columns.get(
                        member_id, round(base_column + offset, 3))))
                if category == 'children':
                    reserve_same_row_slot(
                        generation, desired_column, source_id)
                elif category == 'parents':
                    reserve_same_row_slot(
                        generation, desired_column,
                        {parent_protected.get(member_id), source_id})
                elif category == 'spouses':
                    reserve_same_row_slot(
                        generation, desired_column, source_id)
                if category == 'siblings':
                    column = desired_column
                    occupied.add((generation, column))
                else:
                    column = place(generation, desired_column)
                node = {
                    'id': member_id,
                    'edge': category[:-1] if category.endswith('s') else category,
                    'generation': generation,
                    'column': column,
                    'index': len(layout),
                    'is_path_node': False,
                    'is_endpoint': False,
                    'expanded_from': source_id,
                    'expanded_category': category,
                }
                layout.append(node)
                by_id[member_id] = node
                visible.add(member_id)
                edge = (source_id, member_id, category)
                if edge not in extra_edge_set:
                    extra_edges.append(edge)
                    extra_edge_set.add(edge)

        has_expanded_requests = bool(expanded)
        if not has_expanded_requests:
            path_generations = {
                node['generation'] for node in layout
                if node.get('is_path_node')
            }
            if len(path_generations) == 1:
                enforce_sibling_adjacency()
                enforce_spouse_adjacency()
            enforce_unexpanded_path_child_alignment()
            enforce_spouse_adjacency()
            return layout, extra_edges

        for _ in range(10):
            before = {
                node['id']: (node['generation'], node['column'])
                for node in layout
            }
            if has_expanded_requests:
                enforce_child_alignment()
            enforce_spouse_adjacency()
            enforce_sibling_adjacency()
            enforce_spouse_adjacency()
            after = {
                node['id']: (node['generation'], node['column'])
                for node in layout
            }
            if before == after:
                break
        enforce_vertical_path_edges()
        enforce_parent_alignment()
        enforce_vertical_path_edges()
        enforce_spouse_adjacency()
        if has_expanded_requests:
            enforce_child_alignment()
        enforce_vertical_path_edges()
        enforce_spouse_adjacency()
        enforce_sibling_adjacency()
        enforce_vertical_path_edges()
        enforce_spouse_adjacency()
        enforce_two_parent_path_child_alignment()
        enforce_expanded_child_alignment()
        enforce_two_parent_path_parent_alignment()
        enforce_vertical_path_components()
        enforce_spouse_adjacency()
        enforce_two_parent_path_parent_alignment()
        compact_sibling_only_gaps()
        enforce_vertical_path_edges()
        enforce_spouse_adjacency()
        enforce_two_parent_path_parent_alignment()
        return layout, extra_edges

    @staticmethod
    def _wrap_canvas_label(text, font, max_width):
        """Wrap a canvas label using measured pixel width."""
        lines = []
        for source_line in text.splitlines() or ['']:
            words = source_line.split()
            if not words:
                lines.append(source_line)
                continue
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
    def _graph_ui_font():
        """Return the active UI font family and point size for graph labels."""
        default_font = tkfont.nametofont('TkDefaultFont')
        actual = default_font.actual()
        family = actual.get('family') or default_font.cget('family')
        try:
            size = abs(int(actual.get('size') or default_font.cget('size')))
        except (TypeError, ValueError, tk.TclError):
            size = 11
        return family, size

    @staticmethod
    def _path_graph_window_geometry(content_w, content_h, screen_w, screen_h,
                                    screen_x=0, screen_y=0,
                                    previous_geometry=None):
        """Return geometry for a graph window sized to content or display."""
        chrome_w = 56
        chrome_h = 128
        min_w = min(640, screen_w)
        min_h = min(420, screen_h)
        desired_w = max(int(content_w) + chrome_w, min_w)
        desired_h = max(int(content_h) + chrome_h, min_h)
        if desired_w > screen_w or desired_h > screen_h:
            desired_w, desired_h = screen_w, screen_h

        x = screen_x + max((screen_w - desired_w) // 2, 0)
        y = screen_y + max((screen_h - desired_h) // 2, 0)

        if previous_geometry:
            match = re.match(r'^\d+x\d+([+-]\d+)([+-]\d+)$',
                             previous_geometry)
            if match:
                try:
                    prev_x = int(match.group(1))
                    prev_y = int(match.group(2))
                except ValueError:
                    pass
                else:
                    max_x = screen_x + max(screen_w - desired_w, 0)
                    max_y = screen_y + max(screen_h - desired_h, 0)
                    x = max(screen_x, min(prev_x, max_x))
                    y = max(screen_y, min(prev_y, max_y))

        return desired_w, desired_h, x, y

    @staticmethod
    def _centered_graph_scrollregion(content_w, content_h, view_w, view_h):
        """Return a scrollregion that centers smaller graph content."""
        content_w = max(int(content_w), 1)
        content_h = max(int(content_h), 1)
        view_w = max(int(view_w), 1)
        view_h = max(int(view_h), 1)
        x_pad = max((view_w - content_w) / 2, 0)
        y_pad = max((view_h - content_h) / 2, 0)
        return (
            -x_pad,
            -y_pad,
            content_w + x_pad,
            content_h + y_pad,
        )

    @classmethod
    def _center_graph_canvas(cls, canvas, content_w, content_h):
        """Center graph content when the viewport is larger than the graph."""
        try:
            canvas.update_idletasks()
            scrollregion = cls._centered_graph_scrollregion(
                content_w, content_h,
                canvas.winfo_width(), canvas.winfo_height())
            canvas.configure(scrollregion=scrollregion)
            if scrollregion[0] < 0:
                canvas.xview_moveto(0)
            if scrollregion[1] < 0:
                canvas.yview_moveto(0)
        except tk.TclError:
            pass

    @staticmethod
    def _window_display_bounds(win):
        """Return display bounds for the window's monitor."""
        if sys.platform == 'win32':
            try:
                import ctypes  # pylint: disable=import-outside-toplevel

                class RECT(ctypes.Structure):
                    _fields_ = [
                        ('left', ctypes.c_long),
                        ('top', ctypes.c_long),
                        ('right', ctypes.c_long),
                        ('bottom', ctypes.c_long),
                    ]

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ('cbSize', ctypes.c_ulong),
                        ('rcMonitor', RECT),
                        ('rcWork', RECT),
                        ('dwFlags', ctypes.c_ulong),
                    ]

                monitor_defaulttonearest = 2
                user32 = ctypes.windll.user32
                user32.MonitorFromWindow.argtypes = [
                    ctypes.c_void_p, ctypes.c_uint]
                user32.MonitorFromWindow.restype = ctypes.c_void_p
                user32.GetMonitorInfoW.argtypes = [
                    ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
                user32.GetMonitorInfoW.restype = ctypes.c_bool
                monitor = user32.MonitorFromWindow(
                    ctypes.c_void_p(win.winfo_id()), monitor_defaulttonearest)
                if monitor:
                    info = MONITORINFO()
                    info.cbSize = ctypes.sizeof(MONITORINFO)
                    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                        rect = info.rcWork
                        return (
                            rect.left,
                            rect.top,
                            rect.right - rect.left,
                            rect.bottom - rect.top,
                        )
            except Exception:  # pylint: disable=broad-except
                pass

        try:
            return (
                0,
                0,
                win.winfo_screenwidth(),
                win.winfo_screenheight(),
            )
        except tk.TclError:
            return 0, 0, 1024, 768

    @staticmethod
    def _windows_dib_from_png_bytes(png_bytes):
        """Return CF_DIB bytes for Windows clipboard image data."""
        try:
            from PIL import Image  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise tk.TclError(
                "Pillow is required for Windows graph clipboard copy."
            ) from exc

        with Image.open(io.BytesIO(png_bytes)) as image:
            if image.mode == 'RGBA':
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.getchannel('A'))
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            out = io.BytesIO()
            image.save(out, format='BMP')

        # CF_DIB expects the BMP bytes after the 14-byte BITMAPFILEHEADER.
        return out.getvalue()[14:]

    @classmethod
    def _copy_windows_canvas_bitmap(cls, canvas, width, height):
        """Copy a full Tk canvas render to the Windows clipboard as a bitmap."""
        import ctypes  # pylint: disable=import-outside-toplevel
        import time  # pylint: disable=import-outside-toplevel

        dib_bytes = cls._windows_dib_from_png_bytes(
            canvas_to_png_bytes(canvas, width, height))

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        handle = ctypes.c_void_p

        user32.OpenClipboard.argtypes = [handle]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, handle]
        user32.SetClipboardData.restype = handle
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool

        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = handle
        kernel32.GlobalLock.argtypes = [handle]
        kernel32.GlobalLock.restype = handle
        kernel32.GlobalUnlock.argtypes = [handle]
        kernel32.GlobalUnlock.restype = ctypes.c_bool
        kernel32.GlobalFree.argtypes = [handle]
        kernel32.GlobalFree.restype = handle

        cf_dib = 8
        gmem_moveable = 0x0002
        hwnd = handle(canvas.winfo_toplevel().winfo_id())

        memory = kernel32.GlobalAlloc(gmem_moveable, len(dib_bytes))
        if not memory:
            raise tk.TclError("Could not allocate Windows clipboard image.")

        clipboard_open = False
        try:
            locked = kernel32.GlobalLock(memory)
            if not locked:
                raise tk.TclError("Could not lock Windows clipboard image.")
            try:
                ctypes.memmove(locked, dib_bytes, len(dib_bytes))
            finally:
                kernel32.GlobalUnlock(memory)

            for _ in range(8):
                if user32.OpenClipboard(hwnd):
                    clipboard_open = True
                    break
                time.sleep(0.05)
            if not clipboard_open:
                raise tk.TclError("Could not open the Windows clipboard.")
            if not user32.EmptyClipboard():
                raise tk.TclError("Could not clear the Windows clipboard.")
            if not user32.SetClipboardData(cf_dib, memory):
                raise tk.TclError("Could not set Windows clipboard bitmap.")
            memory = None
        finally:
            if clipboard_open:
                user32.CloseClipboard()
            if memory:
                kernel32.GlobalFree(memory)

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

        png_bytes = canvas_to_png_bytes(canvas, width, height)
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

    @staticmethod
    def _sibling_button_x(node_id, x, x1, x2, button_size, spouse_edges,
                          positions):
        """Return the x coordinate for a sibling expansion button."""
        spouse_on_left = any(
            (
                source_id == node_id
                and target_id in positions
                and positions[target_id][0] < x
            ) or (
                target_id == node_id
                and source_id in positions
                and positions[source_id][0] < x
            )
            for source_id, target_id in spouse_edges
        )
        return (
            x2 + button_size / 2 if spouse_on_left
            else x1 - button_size / 2
        )

    @staticmethod
    def _spouse_button_x(node_id, x, x1, x2, button_size, spouse_edges,
                         positions):
        """Return the x coordinate for a spouse expansion button."""
        spouse_on_left = any(
            (
                source_id == node_id
                and target_id in positions
                and positions[target_id][0] < x
            ) or (
                target_id == node_id
                and source_id in positions
                and positions[source_id][0] < x
            )
            for source_id, target_id in spouse_edges
        )
        return (
            x1 - button_size / 2 if spouse_on_left
            else x2 + button_size / 2
        )

    @classmethod
    def _person_box_fill(cls, individuals, indi_id):
        """Return a theme-independent box fill color for a person's sex."""
        sex = individuals.get(indi_id, {}).get('sex', '').strip().upper()
        if sex == 'M':
            return cls.PERSON_BOX_FILL_MALE
        if sex == 'F':
            return cls.PERSON_BOX_FILL_FEMALE
        return cls.PERSON_BOX_FILL_NEUTRAL

    @staticmethod
    def _toggle_expansion_request(expanded, request):
        """Toggle one graph expansion request in-place."""
        if request in expanded:
            expanded.remove(request)
        else:
            expanded.append(request)

    @staticmethod
    def _expand_all_requests(expanded, node_id,
                             categories=EXPANDABLE_TREE_CATEGORIES):
        """Ensure all immediate-family expansion requests exist for a node."""
        existing = set(expanded)
        changed = False
        for category in categories:
            request = (node_id, category)
            if request not in existing:
                expanded.append(request)
                existing.add(request)
                changed = True
        return changed

    @staticmethod
    def _show_expansion_button(options, expanded, node_id, category):
        """Return whether an expansion toggle should be rendered."""
        return bool(options.get(category)) or (node_id, category) in expanded

    @staticmethod
    def _expansion_button_text(expanded, node_id, category, side='left'):
        """Return the arrow for the next expansion-toggle action."""
        is_expanded = (node_id, category) in expanded
        if category == 'parents':
            return TREE_BUTTON_PARENTS_HIDE if is_expanded else TREE_BUTTON_PARENTS
        if category == 'children':
            return TREE_BUTTON_CHILDREN_HIDE if is_expanded else TREE_BUTTON_CHILDREN
        if category == 'spouses':
            return TREE_BUTTON_SPOUSES_HIDE if is_expanded else TREE_BUTTON_SPOUSES
        if side == 'right':
            return (TREE_BUTTON_SIBLINGS_LEFT if is_expanded
                    else TREE_BUTTON_SIBLINGS_RIGHT)
        return (TREE_BUTTON_SIBLINGS_RIGHT if is_expanded
                else TREE_BUTTON_SIBLINGS_LEFT)

    @staticmethod
    def _expansion_button_tooltip(expanded, node_id, category):
        """Return state-aware tooltip text for a graph expansion button."""
        labels = {
            'parents': (TIP_SHOW_PARENTS, TIP_HIDE_PARENTS),
            'siblings': (TIP_SHOW_SIBLINGS, TIP_HIDE_SIBLINGS),
            'spouses': (TIP_SHOW_SPOUSES, TIP_HIDE_SPOUSES),
            'children': (TIP_SHOW_CHILDREN, TIP_HIDE_CHILDREN),
        }
        show_text, hide_text = labels.get(category, (None, None))
        if show_text is None:
            return None
        return hide_text if (node_id, category) in expanded else show_text

    @staticmethod
    def _clear_canvas_tag_tooltips(canvas):
        """Destroy Canvas tag tooltips from a prior graph render."""
        for tooltip in getattr(canvas, '_graph_tag_tooltips', []):
            tooltip.destroy()
        canvas._graph_tag_tooltips = []

    @staticmethod
    def _make_canvas_tag_tooltip(canvas, text):
        """Create and retain a Canvas tag tooltip for the current render."""
        tooltip = CanvasTagTooltip(canvas, text)
        canvas._graph_tag_tooltips.append(tooltip)
        return tooltip

    @staticmethod
    def _compact_graph_label(indi):
        """Return a compact multi-line label for graph person boxes."""
        name = (indi.get('name') or '').strip()
        given = (indi.get('given_name') or '').strip()
        surname = (indi.get('surname') or '').strip()

        if not given and not surname and name and name != '(unknown)':
            parts = name.split()
            if len(parts) > 1:
                given = ' '.join(parts[:-1])
                surname = parts[-1]
            else:
                given = name

        given_parts = given.split()
        first_line = ''
        if given_parts:
            first_line = given_parts[0]
            if len(given_parts) > 1 and given_parts[1]:
                first_line = f'{first_line} {given_parts[1][0].upper()}.'
        elif surname:
            first_line = surname
            surname = ''
        else:
            first_line = name or '(unknown)'

        lines = [first_line]
        if surname:
            lines.append(surname)
        span = lifespan(indi)
        if span:
            lines.append(span)
        return '\n'.join(lines)

    @staticmethod
    def _draw_spouse_line(canvas, start_x, start_y, end_x, end_y, color,
                          scale):
        """Draw a spouse relationship as paired solid rails."""
        for offset in (-scale(5), scale(5)):
            canvas.create_line(
                start_x, start_y + offset, end_x, end_y + offset,
                fill=color, width=scale(3))

    @staticmethod
    def _draw_sibling_line(canvas, start_x, start_y, end_x, end_y, color,
                           scale):
        """Draw a sibling relationship as a dotted horizontal line."""
        canvas.create_line(
            start_x, start_y, end_x, end_y,
            fill=color, width=scale(4), dash=(scale(2), scale(7)))

    _GRAPH_BUTTON_TAGS = ('family_tree_button', 'path_graph_button')

    def _hide_graph_buttons(self, canvas):
        for tag in self._GRAPH_BUTTON_TAGS:
            canvas.itemconfigure(tag, state='hidden')

    def _show_graph_buttons(self, canvas):
        for tag in self._GRAPH_BUTTON_TAGS:
            canvas.itemconfigure(tag, state='normal')

    def _save_graph_canvas(self, parent, canvas, graph_state, title):
        """Save a full graph canvas as PNG or SVG."""
        canvas.update_idletasks()
        path = filedialog.asksaveasfilename(
            parent=parent,
            title=title,
            defaultextension='.png',
            filetypes=[
                ("PNG images", "*.png"),
                ("SVG images", "*.svg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return 'break'
        self._hide_graph_buttons(canvas)
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.svg':
                svg = canvas_to_svg(
                    canvas, graph_state['canvas_w'],
                    graph_state['canvas_h'])
                with open(path, 'w', encoding='utf-8') as svg_file:
                    svg_file.write(svg)
            else:
                png = canvas_to_png_bytes(
                    canvas, graph_state['canvas_w'],
                    graph_state['canvas_h'])
                with open(path, 'wb') as png_file:
                    png_file.write(png)
        except (OSError, tk.TclError) as exc:
            messagebox.showerror(
                ERR_SAVE_GRAPH_TITLE,
                ERR_SAVE_GRAPH_MSG.format(error=exc),
                parent=parent,
            )
        finally:
            self._show_graph_buttons(canvas)
        return 'break'

    def _copy_graph_canvas(self, parent, canvas, graph_state):
        """Copy a full graph canvas to the system clipboard."""
        canvas.update_idletasks()
        self._hide_graph_buttons(canvas)
        try:
            if sys.platform == 'win32':
                self._copy_windows_canvas_bitmap(
                    canvas, graph_state['canvas_w'], graph_state['canvas_h'])
            elif sys.platform == 'darwin':
                self._copy_macos_canvas_png(
                    canvas, graph_state['canvas_w'], graph_state['canvas_h'])
            else:
                postscript = canvas.postscript(
                    colormode='color', x=0, y=0,
                    width=graph_state['canvas_w'],
                    height=graph_state['canvas_h'])
                parent.clipboard_clear()
                try:
                    parent.clipboard_append(postscript, type='PostScript')
                except tk.TclError:
                    parent.clipboard_append(postscript)
                parent.update()
        finally:
            self._show_graph_buttons(canvas)
        return 'break'

    @staticmethod
    def _graph_debug_node(node):
        """Return a JSON-safe graph node without display names."""
        return {
            'id': node.get('id'),
            'edge': node.get('edge'),
            'generation': node.get('generation'),
            'column': node.get('column'),
            'index': node.get('index'),
            'is_path_node': bool(node.get('is_path_node')),
            'is_endpoint': bool(node.get('is_endpoint')),
            'expanded_from': node.get('expanded_from'),
            'expanded_category': node.get('expanded_category'),
        }

    @staticmethod
    def _graph_debug_edge(edge):
        """Return a JSON-safe graph edge."""
        source_id, target_id, category = edge
        return {
            'source': source_id,
            'target': target_id,
            'category': category,
        }

    @classmethod
    def _graph_debug_payload(cls, graph_state, layout, extra_edges,
                             family_lookup):
        """Return deterministic relationship-graph layout debug data."""
        visible_ids = sorted({node['id'] for node in layout})
        family_members = {}
        for indi_id in visible_ids:
            members = family_lookup(indi_id)
            family_members[indi_id] = {
                category: list(members.get(category, ()))
                for category in ('parents', 'siblings', 'spouses', 'children')
            }
        return {
            'version': 1,
            'graph_type': 'relationship_path',
            'relationship': graph_state.get('relationship'),
            'start_id': graph_state.get('start_id'),
            'zoom': graph_state.get('zoom'),
            'canvas': {
                'width': graph_state.get('canvas_w'),
                'height': graph_state.get('canvas_h'),
            },
            'expanded': [
                {'source': source_id, 'category': category}
                for source_id, category in graph_state.get('expanded', ())
            ],
            'base_layout': [
                cls._graph_debug_node(node)
                for node in graph_state.get('base_layout', ())
            ],
            'layout': [
                cls._graph_debug_node(node)
                for node in sorted(
                    layout,
                    key=lambda item: (
                        item.get('generation', 0),
                        item.get('column', 0),
                        item.get('index', 0),
                        item.get('id', ''),
                    ))
            ],
            'path_edges': [
                {
                    'source': graph_state['base_layout'][index - 1]['id'],
                    'target': graph_state['base_layout'][index]['id'],
                    'category': graph_state['base_layout'][index].get('edge'),
                }
                for index in range(1, len(graph_state.get('base_layout', ())))
            ],
            'extra_edges': [
                cls._graph_debug_edge(edge)
                for edge in sorted(extra_edges)
            ],
            'family_members': family_members,
        }

    @staticmethod
    def _family_tree_debug_node(node):
        """Return a JSON-safe family-tree node without display names."""
        return {
            'id': node.get('id'),
            'generation': node.get('generation'),
            'column': node.get('column'),
            'is_center': bool(node.get('is_center')),
        }

    @classmethod
    def _family_tree_debug_payload(cls, center_id, expanded, zoom,
                                   canvas_w, canvas_h, visible_ids,
                                   edges, layout, family_lookup):
        """Return deterministic Tree View layout debug data."""
        visible_ids = sorted(visible_ids)
        family_members = {}
        for indi_id in visible_ids:
            members = family_lookup(indi_id)
            family_members[indi_id] = {
                category: list(members.get(category, ()))
                for category in ('parents', 'siblings', 'spouses', 'children')
            }
        return {
            'version': 1,
            'graph_type': 'family_tree',
            'center_id': center_id,
            'zoom': zoom,
            'canvas': {
                'width': canvas_w,
                'height': canvas_h,
            },
            'expanded': [
                {'source': source_id, 'category': category}
                for source_id, category in expanded
            ],
            'visible_ids': visible_ids,
            'edges': [
                cls._graph_debug_edge(edge)
                for edge in sorted(edges)
            ],
            'layout': [
                cls._family_tree_debug_node(node)
                for node in sorted(
                    layout,
                    key=lambda item: (
                        item.get('generation', 0),
                        item.get('column', 0),
                        item.get('id', ''),
                    ))
            ],
            'family_members': family_members,
        }

    def _save_graph_debug_payload(self, parent, graph_state):
        """Save deterministic relationship-graph layout data as JSON."""
        payload = graph_state.get('debug_payload')
        if not payload:
            return 'break'
        path = filedialog.asksaveasfilename(
            parent=parent,
            title=DLG_SAVE_GRAPH_DEBUG,
            defaultextension='.json',
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return 'break'
        try:
            with open(path, 'w', encoding='utf-8') as debug_file:
                json.dump(payload, debug_file, indent=2, sort_keys=True)
                debug_file.write('\n')
        except OSError as exc:
            messagebox.showerror(
                ERR_SAVE_GRAPH_TITLE,
                ERR_SAVE_GRAPH_DEBUG_MSG.format(error=exc),
                parent=parent,
            )
        return 'break'

    @staticmethod
    def _bind_graph_mouse_navigation(canvas):
        """Bind wheel scrolling and drag panning to a graph canvas."""
        drag_state = {'x': 0, 'y': 0}
        canvas._graph_dragged = False

        def _scroll_units(event):
            delta = getattr(event, 'delta', 0)
            if not delta:
                return 0
            if abs(delta) >= 120:
                return int(-delta / 120)
            return -1 if delta > 0 else 1

        def _on_mouse_wheel(event):
            if getattr(event, 'state', 0):
                return None
            units = _scroll_units(event)
            if units:
                canvas.yview_scroll(units, 'units')
            return 'break'

        def _on_linux_wheel_up(event):
            if getattr(event, 'state', 0):
                return None
            canvas.yview_scroll(-1, 'units')
            return 'break'

        def _on_linux_wheel_down(event):
            if getattr(event, 'state', 0):
                return None
            canvas.yview_scroll(1, 'units')
            return 'break'

        def _on_drag_start(event):
            canvas.focus_set()
            drag_state['x'] = event.x
            drag_state['y'] = event.y
            canvas._graph_dragged = False
            canvas.scan_mark(event.x, event.y)

        def _on_drag_motion(event):
            if (abs(event.x - drag_state['x']) > 3 or
                    abs(event.y - drag_state['y']) > 3):
                canvas._graph_dragged = True
            canvas.scan_dragto(event.x, event.y, gain=1)
            return 'break'

        def _on_drag_release(_event):
            canvas.after_idle(
                lambda: setattr(canvas, '_graph_dragged', False))

        canvas.bind('<MouseWheel>', _on_mouse_wheel, add='+')
        canvas.bind('<Button-4>', _on_linux_wheel_up, add='+')
        canvas.bind('<Button-5>', _on_linux_wheel_down, add='+')
        canvas.bind('<ButtonPress-1>', _on_drag_start, add='+')
        canvas.bind('<B1-Motion>', _on_drag_motion, add='+')
        canvas.bind('<ButtonRelease-1>', _on_drag_release, add='+')

    def _render_path_graph_canvas(self, canvas, layout, labels, colors, win,
                                  zoom, extra_edges=None, on_expand=None,
                                  expanded=None, on_show_tree=None,
                                  on_profile=None, on_find_matches=None,
                                  on_find_path=None):
        """Draw a relationship graph at the requested zoom level."""
        zoom = max(0.5, min(2.5, float(zoom)))
        extra_edges = extra_edges or []
        expanded_set = set(expanded or [])
        self._clear_canvas_tag_tooltips(canvas)

        def scale(value, minimum=1):
            return max(minimum, int(round(value * zoom)))

        ui_family, ui_size = self._graph_ui_font()
        label_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size), 7))
        badge_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size - 2), 6),
            weight='bold')
        button_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size - 2), 6),
            weight='bold')
        longest = max((label_font.measure(label)
                      for label in labels), default=0)
        node_w = min(max(longest + scale(24), scale(112)), scale(190))
        wrapped_labels = [
            self._wrap_canvas_label(label, label_font, node_w - scale(22))
            for label in labels
        ]
        line_space = label_font.metrics('linespace')
        max_lines = max((label.count('\n') + 1 for label in wrapped_labels),
                        default=1)
        base_node_h = max(scale(82), max_lines * line_space + scale(26))
        badge_h = badge_font.metrics('linespace') + scale(4)
        endpoint_header_h = badge_h + scale(14)
        node_heights = [
            base_node_h + endpoint_header_h
            if node.get('is_endpoint') else base_node_h
            for node in layout
        ]
        max_node_h = max(node_heights, default=base_node_h)
        h_gap = node_w + scale(52)
        v_gap = max(max_node_h + scale(86), scale(150))
        margin = scale(44)
        button_size = scale(22)

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
        position_by_id = {
            node['id']: position for node, position in zip(layout, positions)
        }
        visible_ids = set(position_by_id)
        node_index_by_id = {
            node['id']: index for index, node in enumerate(layout)
        }
        spouse_edges = [
            (layout[index - 1]['id'], layout[index]['id'])
            for index in range(1, len(layout))
            if (layout[index - 1].get('is_path_node')
                and layout[index].get('is_path_node')
                and layout[index].get('edge') == 'spouse')
        ]
        spouse_edges.extend(
            (source_id, target_id)
            for source_id, target_id, category in extra_edges
            if category == 'spouses'
        )

        canvas_w = margin * 2 + node_w + (max_column - min_column) * h_gap
        canvas_h = margin * 2 + max_node_h + (
            max_generation - min_generation) * v_gap

        for generation in range(min_generation, max_generation + 1):
            y = margin + max_node_h / 2 + (
                generation - min_generation) * v_gap
            canvas.create_line(
                margin / 2, y, canvas_w - margin / 2, y,
                fill=colors['guide'], dash=(scale(3), scale(8)))

        for index in range(1, len(layout)):
            if (not layout[index - 1].get('is_path_node')
                    or not layout[index].get('is_path_node')):
                continue
            edge = layout[index]['edge']
            x1, y1 = positions[index - 1]
            x2, y2 = positions[index]

            if edge == 'spouse':
                start_x = x1 + node_w / 2
                end_x = x2 - node_w / 2
                self._draw_spouse_line(
                    canvas, start_x, y1, end_x, y2, colors['spouse'], scale)
            elif edge == 'sibling':
                start_x = x1 + node_w / 2
                end_x = x2 - node_w / 2
                self._draw_sibling_line(
                    canvas, start_x, y1, end_x, y2, colors['sibling'], scale)
            else:
                from_h = node_heights[index - 1]
                to_h = node_heights[index]
                from_x, from_y = x1, y1
                if edge == 'child':
                    parent_midpoint = self._child_parent_midpoint(
                        layout[index - 1]['id'], layout[index]['id'],
                        position_by_id, self._co_parents_for_children,
                        spouse_edges)
                    if parent_midpoint:
                        from_x, from_y = parent_midpoint
                        from_h = 0
                elif edge in ('father', 'mother'):
                    parent_midpoint = self._child_parent_midpoint(
                        layout[index]['id'], layout[index - 1]['id'],
                        position_by_id, self._co_parents_for_children,
                        spouse_edges)
                    if parent_midpoint:
                        x2, y2 = parent_midpoint
                        to_h = 0
                start_y = from_y + (
                    from_h / 2 if y2 > from_y else -from_h / 2)
                end_y = y2 - (to_h / 2 if y2 > from_y else -to_h / 2)
                mid_y = (start_y + end_y) / 2
                canvas.create_line(
                    from_x, start_y, from_x, mid_y, x2, mid_y, x2, end_y,
                    fill=colors['parent'], width=scale(3), arrow='last',
                    arrowshape=(scale(12), scale(14), scale(5)))

        drawn_parent_midpoint_edges = set()
        for source_id, target_id, category in extra_edges:
            if source_id not in position_by_id or target_id not in position_by_id:
                continue
            source_index = node_index_by_id[source_id]
            target_index = node_index_by_id[target_id]
            sx, sy = position_by_id[source_id]
            tx, ty = position_by_id[target_id]
            if category == 'parents':
                parent_midpoint = self._child_parent_midpoint(
                    target_id, source_id, position_by_id,
                    self._co_parents_for_children, spouse_edges)
                coparent_id = self._visible_coparent_id(
                    target_id, source_id, position_by_id,
                    self._co_parents_for_children, spouse_edges)
                if parent_midpoint and coparent_id:
                    edge_key = (
                        source_id,
                        tuple(sorted((target_id, coparent_id))),
                    )
                    if edge_key in drawn_parent_midpoint_edges:
                        continue
                    drawn_parent_midpoint_edges.add(edge_key)
                    parent_x, parent_y = parent_midpoint
                    parent_h = 0
                else:
                    parent_x, parent_y = tx, ty
                    parent_h = node_heights[target_index]
                child_x, child_y = sx, sy
                child_h = node_heights[source_index]
            elif category == 'children':
                parent_midpoint = self._child_parent_midpoint(
                    source_id, target_id, position_by_id,
                    self._co_parents_for_children, spouse_edges)
                if parent_midpoint:
                    parent_x, parent_y = parent_midpoint
                    parent_h = 0
                else:
                    parent_x, parent_y = sx, sy
                    parent_h = node_heights[source_index]
                child_x, child_y = tx, ty
                child_h = node_heights[target_index]
            elif category == 'spouses':
                start_x = sx + (-node_w / 2 if tx < sx else node_w / 2)
                end_x = tx + (node_w / 2 if tx < sx else -node_w / 2)
                self._draw_spouse_line(
                    canvas, start_x, sy, end_x, ty,
                    colors['spouse'], scale)
                continue
            else:
                start_x = sx + (-node_w / 2 if tx < sx else node_w / 2)
                end_x = tx + (node_w / 2 if tx < sx else -node_w / 2)
                self._draw_sibling_line(
                    canvas, start_x, sy, end_x, ty,
                    colors['sibling'], scale)
                continue

            start_y = parent_y + parent_h / 2
            end_y = child_y - child_h / 2
            mid_y = (start_y + end_y) / 2
            canvas.create_line(
                parent_x, start_y, parent_x, mid_y, child_x, mid_y,
                child_x, end_y,
                fill=colors['parent'], width=scale(3), arrow='last',
                arrowshape=(scale(12), scale(14), scale(5)))

        for index, ((x, y), label) in enumerate(zip(positions, wrapped_labels)):
            node_id = layout[index]['id']
            node_tag = f'path_node_{index}'
            node_h = node_heights[index]
            x1 = x - node_w / 2
            y1 = y - node_h / 2
            x2 = x + node_w / 2
            y2 = y + node_h / 2
            is_endpoint = layout[index].get('is_endpoint')
            fill = self._person_box_fill(self.individuals, node_id)
            outline_width = scale(3) if is_endpoint else scale(2)
            canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline=colors['node_outline'],
                width=outline_width, tags=('path_node', node_tag))
            if is_endpoint:
                badge = PATH_GRAPH_START if index == 0 else PATH_GRAPH_END
                badge_w = badge_font.measure(badge) + scale(12)
                badge_x1 = x1 + scale(8)
                badge_y1 = y1 + scale(6)
                badge_x2 = badge_x1 + badge_w
                badge_y2 = badge_y1 + badge_h
                canvas.create_rectangle(
                    badge_x1, badge_y1, badge_x2, badge_y2,
                    fill=colors['badge_fill'], outline=colors['badge_fill'],
                    tags=('path_node', node_tag))
                canvas.create_text(
                    (badge_x1 + badge_x2) / 2, (badge_y1 + badge_y2) / 2,
                    text=badge, fill=colors['badge_text'], font=badge_font,
                    anchor='center', tags=('path_node', node_tag))
                text_y = y1 + endpoint_header_h + (
                    node_h - endpoint_header_h) / 2
            else:
                text_y = y
            canvas.create_text(
                x, text_y, text=label, fill=self.PERSON_BOX_TEXT,
                font=label_font,
                width=node_w - scale(22), justify='center',
                tags=('path_node', node_tag))

            if node_id in self.individuals:
                canvas.tag_bind(
                    node_tag, '<Enter>',
                    lambda *_: canvas.configure(cursor='hand2'))
                canvas.tag_bind(
                    node_tag, '<Leave>',
                    lambda *_: canvas.configure(cursor=''))

                def _show_node_menu(event, indi_id=node_id):
                    if (getattr(canvas, '_graph_dragged', False)
                            or getattr(canvas, '_family_tree_dragged', False)):
                        return 'break'
                    menu = tk.Menu(canvas, tearoff=0)
                    menu.add_command(
                        label=PATH_GRAPH_MENU_SHOW_TREE,
                        command=(
                            lambda: on_show_tree(indi_id)
                            if on_show_tree else None))
                    menu.add_command(
                        label=BTN_SHOW_PERSON,
                        command=(
                            lambda: on_profile(indi_id)
                            if on_profile else None))
                    menu.add_command(
                        label=BTN_FIND_MATCHES,
                        command=(
                            lambda: on_find_matches(indi_id)
                            if on_find_matches else None))
                    menu.add_command(
                        label=PATH_GRAPH_MENU_FIND_PATH,
                        command=(
                            lambda: on_find_path(indi_id)
                            if on_find_path else None))
                    try:
                        menu.tk_popup(event.x_root, event.y_root)
                    finally:
                        try:
                            menu.grab_release()
                        except tk.TclError:
                            pass
                    return 'break'

                canvas.tag_bind(node_tag, '<ButtonRelease-1>', _show_node_menu)
                canvas.tag_bind(node_tag, '<Button-3>', _show_node_menu)
                canvas.tag_bind(
                    node_tag, '<Control-Button-1>', _show_node_menu)

                if on_expand:
                    options = family_tree_expansion_options(
                        node_id, visible_ids, self._family_tree_members_for)
                    button_specs = {
                        'parents': (
                            x, y1 - button_size / 2),
                        'siblings': (
                            self._sibling_button_x(
                                node_id, x, x1, x2, button_size,
                                spouse_edges, position_by_id),
                            y),
                        'spouses': (
                            self._spouse_button_x(
                                node_id, x, x1, x2, button_size,
                                spouse_edges, position_by_id),
                            y),
                        'children': (
                            x, y2 + button_size / 2),
                    }
                    for category in EXPANDABLE_TREE_CATEGORIES:
                        if not self._show_expansion_button(
                                options, expanded_set, node_id, category):
                            continue
                        bx, by = button_specs[category]
                        button_side = 'right' if bx > x else 'left'
                        text = self._expansion_button_text(
                            expanded_set, node_id, category, button_side)
                        tooltip_text = self._expansion_button_tooltip(
                            expanded_set, node_id, category)
                        tooltip = (
                            self._make_canvas_tag_tooltip(canvas, tooltip_text)
                            if tooltip_text else None
                        )
                        is_active = (node_id, category) in expanded_set
                        button_fill = (
                            colors['spouse']
                            if category == 'spouses' and is_active
                            else colors['badge_fill']
                        )
                        button_text = self._readable_text_color(button_fill)
                        button_tag = f'path_expand_{index}_{category}'
                        canvas.create_rectangle(
                            bx - button_size / 2, by - button_size / 2,
                            bx + button_size / 2, by + button_size / 2,
                            fill=button_fill,
                            outline=button_fill,
                            tags=('path_graph_button', button_tag))
                        canvas.create_text(
                            bx, by, text=text, fill=button_text,
                            font=button_font, anchor='center',
                            tags=('path_graph_button', button_tag))

                        def _on_expand(_, indi_id=node_id, rel=category):
                            on_expand(indi_id, rel)
                            return 'break'

                        def _on_button_enter(event, tip=tooltip):
                            canvas.configure(cursor='hand2')
                            if tip:
                                tip.on_enter(event)

                        def _on_button_leave(event, tip=tooltip):
                            canvas.configure(cursor='')
                            if tip:
                                tip.on_leave(event)

                        canvas.tag_bind(button_tag, '<Enter>',
                                        _on_button_enter)
                        if tooltip:
                            canvas.tag_bind(
                                button_tag, '<Motion>', tooltip.on_enter)
                        canvas.tag_bind(button_tag, '<Leave>',
                                        _on_button_leave)
                        canvas.tag_bind(button_tag, '<Button-1>', _on_expand)

        self._center_graph_canvas(canvas, canvas_w, canvas_h)
        return canvas_w, canvas_h

    def _family_tree_members_for(self, indi_id):
        """Return family tree relationship lists for one individual."""
        if indi_id not in self.individuals:
            return {
                'parents': [],
                'siblings': [],
                'spouses': [],
                'children': [],
            }
        parents, siblings, spouses, children = self._get_family_members(
            indi_id)
        return {
            'parents': parents,
            'siblings': siblings,
            'spouses': spouses,
            'children': children,
        }

    def _co_parents_for_children(self, indi_id, child_ids):
        """Return the other parents for this person's displayed children."""
        if indi_id not in self.individuals:
            return []
        wanted_children = set(child_ids)
        parents = []
        seen = set()
        for fam_id in self.individuals[indi_id].get('fams', ()):
            fam = self.families.get(fam_id)
            if not fam:
                continue
            if not any(child_id in wanted_children
                       for child_id in fam.get('chil', ())):
                continue
            parent_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            if (parent_id and parent_id in self.individuals
                    and parent_id not in seen):
                parents.append(parent_id)
                seen.add(parent_id)
        return parents

    @staticmethod
    def _visible_coparent_id(parent_id, child_id, positions,
                             coparent_lookup, spouse_edges=()):
        """Return a displayed co-parent for the parent and child."""
        if parent_id not in positions:
            return None
        for coparent_id in coparent_lookup(parent_id, (child_id,)):
            if coparent_id in positions:
                return coparent_id
        for left_id, right_id in spouse_edges:
            if left_id == parent_id and right_id in positions:
                return right_id
            if right_id == parent_id and left_id in positions:
                return left_id
        return None

    @staticmethod
    def _child_parent_midpoint(parent_id, child_id, positions,
                               coparent_lookup, spouse_edges=()):
        """Return the midpoint between displayed parents for a child edge."""
        coparent_id = ResultsMixin._visible_coparent_id(
            parent_id, child_id, positions, coparent_lookup, spouse_edges)
        if not coparent_id:
            return None
        parent_x, parent_y = positions[parent_id]
        coparent_x, coparent_y = positions[coparent_id]
        return (
            (parent_x + coparent_x) / 2,
            (parent_y + coparent_y) / 2,
        )

    @staticmethod
    def _family_tree_child_edge_groups(edges, positions, coparent_lookup,
                                       spouse_edges=()):
        """Group visible parent-child edges by displayed parent or couple."""
        groups = {}
        for source_id, target_id, category in edges:
            if category == 'parents':
                child_id = source_id
                parent_id = target_id
            elif category == 'children':
                parent_id = source_id
                child_id = target_id
            else:
                continue
            if parent_id not in positions or child_id not in positions:
                continue

            coparent_id = ResultsMixin._visible_coparent_id(
                parent_id, child_id, positions, coparent_lookup, spouse_edges)
            if coparent_id and coparent_id in positions:
                parent_ids = tuple(sorted((parent_id, coparent_id)))
                parent_x = (
                    positions[parent_id][0] + positions[coparent_id][0]) / 2
                parent_y = (
                    positions[parent_id][1] + positions[coparent_id][1]) / 2
                parent_h = 0
            else:
                parent_ids = (parent_id,)
                parent_x, parent_y = positions[parent_id]
                parent_h = None

            child_generation_y = positions[child_id][1]
            group_key = (parent_ids, child_generation_y)
            group = groups.setdefault(group_key, {
                'parent_ids': parent_ids,
                'parent_x': parent_x,
                'parent_y': parent_y,
                'parent_h': parent_h,
                'children': [],
                'child_ids': set(),
            })
            if child_id not in group['child_ids']:
                group['children'].append(child_id)
                group['child_ids'].add(child_id)

        result = []
        for group in groups.values():
            group['children'].sort(key=lambda child_id: positions[child_id][0])
            del group['child_ids']
            result.append(group)
        result.sort(key=lambda group: (
            group['parent_y'],
            min(positions[child_id][0] for child_id in group['children']),
        ))
        return result

    @staticmethod
    def _family_tree_child_bus_span(parent_x, child_xs):
        """Return the horizontal connector span for a parent-child group."""
        xs = [parent_x] + list(child_xs)
        return min(xs), max(xs)

    def _render_family_tree_canvas(self, canvas, center_id, expanded, colors,
                                   win, zoom, on_expand, on_recenter,
                                   on_profile=None, on_find_matches=None,
                                   on_expand_all=None):
        """Draw an expandable immediate-family tree graph."""
        zoom = max(0.5, min(2.5, float(zoom)))
        visible_ids, edges = build_family_tree_graph(
            center_id, expanded, self._family_tree_members_for,
            self._co_parents_for_children)
        layout = layout_family_tree(center_id, visible_ids, edges)
        visible_set = set(visible_ids)
        expanded_set = set(expanded)
        self._clear_canvas_tag_tooltips(canvas)

        def scale(value, minimum=1):
            return max(minimum, int(round(value * zoom)))

        ui_family, ui_size = self._graph_ui_font()
        label_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size), 7))
        button_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size - 2), 6),
            weight='bold')

        labels = [
            self._compact_graph_label(self.individuals[node['id']])
            if node['id'] in self.individuals else node['id']
            for node in layout
        ]
        longest = max((label_font.measure(label)
                      for label in labels), default=0)
        node_w = min(max(longest + scale(24), scale(112)), scale(190))
        wrapped_labels = [
            self._wrap_canvas_label(label, label_font, node_w - scale(24))
            for label in labels
        ]
        line_space = label_font.metrics('linespace')
        max_lines = max((label.count('\n') + 1 for label in wrapped_labels),
                        default=1)
        node_h = max(scale(84), max_lines * line_space + scale(26))
        h_gap = node_w + scale(48)
        v_gap = max(node_h + scale(88), scale(150))
        margin = scale(56)
        button_size = scale(22)

        min_generation = min(node['generation'] for node in layout)
        max_generation = max(node['generation'] for node in layout)
        min_column = min(node['column'] for node in layout)
        max_column = max(node['column'] for node in layout)
        positions = {}
        for node in layout:
            x = margin + node_w / 2 + (node['column'] - min_column) * h_gap
            y = margin + node_h / 2 + (
                node['generation'] - min_generation) * v_gap
            positions[node['id']] = (x, y)
        canvas._family_tree_center = positions.get(center_id, (0, 0))
        spouse_edges = [
            (source_id, target_id)
            for source_id, target_id, category in edges
            if category == 'spouses'
        ]

        canvas_w = margin * 2 + node_w + (max_column - min_column) * h_gap
        canvas_h = margin * 2 + node_h + (
            max_generation - min_generation) * v_gap
        canvas._family_tree_debug_payload = self._family_tree_debug_payload(
            center_id, expanded, zoom, canvas_w, canvas_h, visible_ids,
            edges, layout, self._family_tree_members_for)

        for generation in range(min_generation, max_generation + 1):
            y = margin + node_h / 2 + (
                generation - min_generation) * v_gap
            canvas.create_line(
                margin / 2, y, canvas_w - margin / 2, y,
                fill=colors['guide'], dash=(scale(3), scale(8)))

        for source_id, target_id, category in edges:
            if source_id not in positions or target_id not in positions:
                continue
            sx, sy = positions[source_id]
            tx, ty = positions[target_id]
            if category == 'spouses':
                start_x = sx + (node_w / 2 if tx >= sx else -node_w / 2)
                end_x = tx - node_w / 2 if tx >= sx else tx + node_w / 2
                self._draw_spouse_line(
                    canvas, start_x, sy, end_x, ty, colors['spouse'], scale)
                continue
            if category == 'siblings':
                start_x = sx + (-node_w / 2 if tx < sx else node_w / 2)
                end_x = tx + (node_w / 2 if tx < sx else -node_w / 2)
                self._draw_sibling_line(
                    canvas, start_x, sy, end_x, ty,
                    colors['sibling'], scale)
        for group in self._family_tree_child_edge_groups(
                edges, positions, self._co_parents_for_children,
                spouse_edges):
            parent_x = group['parent_x']
            parent_y = group['parent_y']
            parent_h = node_h if group['parent_h'] is None else group['parent_h']
            start_y = parent_y + parent_h / 2
            child_tops = [
                positions[child_id][1] - node_h / 2
                for child_id in group['children']
            ]
            end_y = min(child_tops)
            mid_y = (start_y + end_y) / 2
            child_xs = [positions[child_id][0]
                        for child_id in group['children']]
            bus_start_x, bus_end_x = self._family_tree_child_bus_span(
                parent_x, child_xs)
            canvas.create_line(
                parent_x, start_y, parent_x, mid_y,
                fill=colors['parent'], width=scale(3))
            canvas.create_line(
                bus_start_x, mid_y, bus_end_x, mid_y,
                fill=colors['parent'], width=scale(3))
            for child_id in group['children']:
                child_x, child_y = positions[child_id]
                canvas.create_line(
                    child_x, mid_y, child_x, child_y - node_h / 2,
                    fill=colors['parent'], width=scale(3), arrow='last',
                    arrowshape=(scale(12), scale(14), scale(5)))

        for index, (node, label) in enumerate(zip(layout, wrapped_labels)):
            node_id = node['id']
            x, y = positions[node_id]
            x1 = x - node_w / 2
            y1 = y - node_h / 2
            x2 = x + node_w / 2
            y2 = y + node_h / 2
            node_tag = f'family_tree_node_{index}'
            fill = self._person_box_fill(self.individuals, node_id)
            outline_width = scale(3) if node['is_center'] else scale(2)
            canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline=colors['node_outline'],
                width=outline_width, tags=('family_tree_node', node_tag))
            canvas.create_text(
                x, y, text=label, fill=self.PERSON_BOX_TEXT,
                font=label_font,
                width=node_w - scale(24), justify='center',
                tags=('family_tree_node', node_tag))
            options = family_tree_expansion_options(
                node_id, visible_set, self._family_tree_members_for)
            hidden_categories = tuple(
                category for category in EXPANDABLE_TREE_CATEGORIES
                if options.get(category))

            if node_id in self.individuals:
                canvas.tag_bind(
                    node_tag, '<Enter>',
                    lambda *_: canvas.configure(cursor='hand2'))
                canvas.tag_bind(
                    node_tag, '<Leave>',
                    lambda *_: canvas.configure(cursor=''))

                def _show_node_menu(event, indi_id=node_id,
                                    categories=hidden_categories):
                    if getattr(canvas, '_family_tree_dragged', False):
                        return 'break'
                    menu = tk.Menu(canvas, tearoff=0)
                    menu.add_command(
                        label=TREE_MENU_RECENTER,
                        command=lambda: on_recenter(indi_id))
                    menu.add_command(
                        label=BTN_SHOW_PERSON,
                        command=(
                            lambda: on_profile(indi_id)
                            if on_profile else None))
                    menu.add_command(
                        label=BTN_FIND_MATCHES,
                        command=(
                            lambda: on_find_matches(indi_id)
                            if on_find_matches else None))
                    menu.add_command(
                        label=TREE_MENU_EXPAND_ALL,
                        command=(
                            lambda: on_expand_all(indi_id, categories)
                            if on_expand_all else None))
                    try:
                        menu.tk_popup(event.x_root, event.y_root)
                    finally:
                        try:
                            menu.grab_release()
                        except tk.TclError:
                            pass
                    return 'break'

                canvas.tag_bind(node_tag, '<ButtonRelease-1>', _show_node_menu)
                canvas.tag_bind(node_tag, '<Button-3>', _show_node_menu)
                canvas.tag_bind(
                    node_tag, '<Control-Button-1>', _show_node_menu)

            button_specs = {
                'parents': (x, y1 - button_size / 2),
                'siblings': (
                    self._sibling_button_x(
                        node_id, x, x1, x2, button_size, spouse_edges,
                        positions),
                    y,
                ),
                'spouses': (
                    self._spouse_button_x(
                        node_id, x, x1, x2, button_size, spouse_edges,
                        positions),
                    y,
                ),
                'children': (x, y2 + button_size / 2),
            }
            for category in EXPANDABLE_TREE_CATEGORIES:
                if not self._show_expansion_button(
                        options, expanded_set, node_id, category):
                    continue
                bx, by = button_specs[category]
                button_side = 'right' if bx > x else 'left'
                text = self._expansion_button_text(
                    expanded_set, node_id, category, button_side)
                tooltip_text = self._expansion_button_tooltip(
                    expanded_set, node_id, category)
                tooltip = (
                    self._make_canvas_tag_tooltip(canvas, tooltip_text)
                    if tooltip_text else None
                )
                is_active = (node_id, category) in expanded_set
                button_fill = (
                    colors['spouse']
                    if category == 'spouses' and is_active
                    else colors['badge_fill']
                )
                button_text = self._readable_text_color(button_fill)
                button_tag = f'family_tree_expand_{index}_{category}'
                canvas.create_rectangle(
                    bx - button_size / 2, by - button_size / 2,
                    bx + button_size / 2, by + button_size / 2,
                    fill=button_fill, outline=button_fill,
                    tags=('family_tree_button', button_tag))
                canvas.create_text(
                    bx, by, text=text, fill=button_text,
                    font=button_font, anchor='center',
                    tags=('family_tree_button', button_tag))

                def _on_expand(_, indi_id=node_id, rel=category):
                    on_expand(indi_id, rel)
                    return 'break'

                def _on_button_enter(event, tip=tooltip):
                    canvas.configure(cursor='hand2')
                    if tip:
                        tip.on_enter(event)

                def _on_button_leave(event, tip=tooltip):
                    canvas.configure(cursor='')
                    if tip:
                        tip.on_leave(event)

                canvas.tag_bind(button_tag, '<Enter>', _on_button_enter)
                if tooltip:
                    canvas.tag_bind(button_tag, '<Motion>', tooltip.on_enter)
                canvas.tag_bind(button_tag, '<Leave>', _on_button_leave)
                canvas.tag_bind(button_tag, '<Button-1>', _on_expand)

        self._center_graph_canvas(canvas, canvas_w, canvas_h)
        return canvas_w, canvas_h

    def _show_path_graph(self, path, relationship):
        """Open a scrollable graphical view of a relationship path."""
        if not path:
            return

        graph_path = self._simplify_path_for_graph(path)

        existing_win = getattr(self, '_secondary_win', None)
        if existing_win is not None:
            try:
                if not existing_win.winfo_exists():
                    existing_win = None
            except tk.TclError:
                existing_win = None
            if existing_win is None:
                self._secondary_win = None
                self._path_graph_win = None
                self._path_graph_replace_fn = None

        if existing_win is not None and existing_win is getattr(self, '_path_graph_win', None):
            replace_fn = getattr(self, '_path_graph_replace_fn', None)
            if replace_fn is not None:
                replace_fn(list(path), relationship)
            self._raise_window(existing_win)
            return

        repurpose_window = existing_win is not None
        if repurpose_window:
            win = existing_win
            for sequence in self._reused_person_window_bindings():
                try:
                    win.unbind(sequence)
                except tk.TclError:
                    pass
            try:
                win.unbind('<Configure>')
            except tk.TclError:
                pass
            for child in win.winfo_children():
                child.destroy()
        else:
            win = ctk.CTkToplevel(self.root)
            self._secondary_win = win
            win.withdraw()

        self._path_graph_win = win
        win.title(WIN_PATH_GRAPH)
        win.resizable(True, True)
        if sys.platform != 'win32':
            win.transient(self.root)

        is_dark = ctk.get_appearance_mode() == 'Dark'
        colors = self._path_graph_colors(
            is_dark, getattr(self, '_theme_pref', None))

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=12, pady=12)

        relationship_label = ctk.CTkLabel(
            outer,
            text=RESULT_RELATIONSHIP.format(rel=relationship),
            anchor='w',
            justify='left',
            wraplength=1000,
            font=ctk.CTkFont(weight='bold'),
        )
        relationship_label.pack(fill='x', pady=(0, 8))

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

        graph_state = {
            'zoom': 1.0,
            'canvas_w': 0,
            'canvas_h': 0,
            'expanded': [],
            'base_layout': self._path_graph_layout(graph_path),
            'relationship': relationship,
            'start_id': graph_path[0][0],
            'debug_payload': None,
        }

        def _redraw_graph():
            layout, extra_edges = self._expanded_path_graph_layout(
                graph_state['base_layout'], graph_state['expanded'],
                self._family_tree_members_for,
                self._co_parents_for_children)
            labels = [
                self._compact_graph_label(self.individuals[node['id']])
                if node['id'] in self.individuals else node['id']
                for node in layout
            ]
            canvas.delete('all')
            graph_state['canvas_w'], graph_state['canvas_h'] = (
                self._render_path_graph_canvas(
                    canvas, layout, labels, colors, win, graph_state['zoom'],
                    extra_edges=extra_edges, on_expand=_expand_graph_node,
                    expanded=graph_state['expanded'],
                    on_show_tree=_show_tree_from_graph,
                    on_profile=_show_profile_from_graph,
                    on_find_matches=_find_matches_from_graph,
                    on_find_path=_find_path_from_graph))
            graph_state['debug_payload'] = self._graph_debug_payload(
                graph_state, layout, extra_edges, self._family_tree_members_for)

        def _replace_graph_path(new_path, new_relationship):
            simplified_path = self._simplify_path_for_graph(new_path)
            graph_state['base_layout'] = self._path_graph_layout(
                simplified_path)
            graph_state['relationship'] = new_relationship
            graph_state['expanded'] = []
            relationship_label.configure(
                text=RESULT_RELATIONSHIP.format(rel=new_relationship))
            _redraw_graph()

        self._path_graph_replace_fn = _replace_graph_path

        _graph_geo_after = [None]

        def _remember_graph_geometry():
            try:
                self._path_graph_geometry = win.geometry()
                self._path_graph_opened_this_session = True
            except tk.TclError:
                pass

        def _stop_graph_geometry_tracking():
            if _graph_geo_after[0]:
                try:
                    win.after_cancel(_graph_geo_after[0])
                except tk.TclError:
                    pass
                _graph_geo_after[0] = None

        def _destroy_graph_window(*_):
            _stop_graph_geometry_tracking()
            _remember_graph_geometry()
            if getattr(self, '_secondary_win', None) is win:
                self._secondary_win = None
            if getattr(self, '_path_graph_win', None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            win.destroy()

        def _on_graph_configure(event):
            if event.widget is not win:
                return
            if _graph_geo_after[0]:
                win.after_cancel(_graph_geo_after[0])
            _graph_geo_after[0] = win.after(400, _remember_graph_geometry)

        def _close_graph_for(action):
            _stop_graph_geometry_tracking()
            _remember_graph_geometry()
            _destroy_graph_window()
            self.root.after_idle(action)

        def _show_tree_from_graph(indi_id):
            self._select_person_in_main_tree(indi_id)
            self._show_person_for(indi_id, initial_view='tree')

        def _show_profile_from_graph(indi_id):
            self._select_person_in_main_tree(indi_id)
            self._show_person_for(indi_id, initial_view='profile')

        def _find_matches_from_graph(indi_id):
            def _find_matches():
                self._select_person_in_main_tree(indi_id)
                self._find_matches()

            _close_graph_for(_find_matches)

        def _focus_graph_window():
            try:
                if win.winfo_exists():
                    self._raise_window(win)
                    canvas.focus_set()
            except tk.TclError:
                pass

        def _graph_window_exists():
            try:
                return bool(win.winfo_exists())
            except tk.TclError:
                return False

        def _find_path_from_graph(target_id):
            if self._busy:
                return
            start_id = graph_state['start_id']
            if target_id == start_id:
                _replace_graph_path([(start_id, None)], PATH_SAME_PERSON)
                return
            try:
                max_depth = int(self.max_depth.get())
            except (tk.TclError, ValueError):
                messagebox.showerror(ERR_BAD_VAL_TITLE, ERR_BAD_VAL_DEPTH)
                _focus_graph_window()
                return

            self._show_progress()
            self._set_busy(True)
            _focus_graph_window()

            def _do_search(cancel_event):
                return self._model.find_all_paths(
                    start_id, target_id, top_n=1, max_depth=max_depth,
                    cancel_event=cancel_event)

            def _on_cancel():
                self._hide_progress()
                self._set_busy(False)
                _focus_graph_window()

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if not _graph_window_exists():
                    return
                _focus_graph_window()
                if error:
                    messagebox.showerror(ERR_PARSE_TITLE, str(error))
                    _focus_graph_window()
                    return
                paths, _truncated = result
                if not paths:
                    messagebox.showinfo(
                        WIN_PATH_GRAPH,
                        PATH_NOT_FOUND.format(depth=max_depth),
                        parent=win,
                    )
                    _focus_graph_window()
                    return
                new_path = paths[0]
                ancestors = get_ancestor_depths(
                    start_id, self.individuals, self.families)
                descendants = get_descendant_depths(
                    start_id, self.individuals, self.families)
                new_relationship = describe_relationship(
                    new_path, self.individuals,
                    ancestors=ancestors, descendants=descendants,
                    families=self.families)
                _replace_graph_path(new_path, new_relationship)

            self._run_background_task(
                _do_search,
                _on_done,
                cancelable=True,
                on_cancel=_on_cancel,
            )

        def _expand_graph_node(indi_id, category):
            request = (indi_id, category)
            self._toggle_expansion_request(graph_state['expanded'], request)
            _redraw_graph()

        def _set_graph_zoom(zoom):
            zoom = max(0.5, min(2.5, zoom))
            if abs(zoom - graph_state['zoom']) < 0.001:
                return
            x0, x1 = canvas.xview()
            y0, y1 = canvas.yview()
            center_x = (x0 + x1) / 2
            center_y = (y0 + y1) / 2
            span_x = x1 - x0
            span_y = y1 - y0
            graph_state['zoom'] = zoom
            _redraw_graph()
            canvas.update_idletasks()
            canvas.xview_moveto(max(0, min(1, center_x - span_x / 2)))
            canvas.yview_moveto(max(0, min(1, center_y - span_y / 2)))

        def _zoom_graph_in():
            _set_graph_zoom(graph_state['zoom'] * 1.1)

        def _zoom_graph_out():
            _set_graph_zoom(graph_state['zoom'] / 1.1)

        def _zoom_graph_reset():
            _set_graph_zoom(1.0)

        _redraw_graph()
        self._bind_graph_mouse_navigation(canvas)
        canvas.bind(
            '<Configure>',
            lambda *_: self._center_graph_canvas(
                canvas, graph_state['canvas_w'], graph_state['canvas_h']),
            add='+')
        bind_zoom_shortcuts(
            win, _zoom_graph_in, _zoom_graph_out, _zoom_graph_reset)
        bind_zoom_shortcuts(
            canvas, _zoom_graph_in, _zoom_graph_out, _zoom_graph_reset)

        def _save_graph(*_):
            win.update_idletasks()
            try:
                return self._save_graph_canvas(
                    win, canvas, graph_state, DLG_SAVE_GRAPH)
            finally:
                btn_frame.pack(fill='x', pady=(8, 0))

        def _copy_graph(*_):
            win.update_idletasks()
            try:
                return self._copy_graph_canvas(win, canvas, graph_state)
            finally:
                btn_frame.pack(fill='x', pady=(8, 0))

        def _save_graph_debug(*_):
            win.update_idletasks()
            try:
                return self._save_graph_debug_payload(win, graph_state)
            finally:
                btn_frame.pack(fill='x', pady=(8, 0))

        btn_frame = ctk.CTkFrame(outer, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(8, 0))
        close_btn = ctk.CTkButton(
            btn_frame, text=BTN_CLOSE, width=80,
            command=_destroy_graph_window)
        close_btn.pack(side='right')
        copy_btn = ctk.CTkButton(
            btn_frame, text=BTN_COPY_GRAPH, width=80, command=_copy_graph)
        copy_btn.pack(side='right', padx=(0, 8))
        Tooltip(copy_btn, TIP_COPY_GRAPH)
        save_btn = ctk.CTkButton(
            btn_frame, text=BTN_SAVE_GRAPH, width=80, command=_save_graph)
        save_btn.pack(side='right', padx=(0, 8))
        Tooltip(save_btn, TIP_SAVE_GRAPH)
        graph_debug_enabled = (
            os.environ.get('GEDCOM_NAVIGATOR_GRAPH_DEBUG') == '1')
        if graph_debug_enabled:
            debug_btn = ctk.CTkButton(
                btn_frame, text=BTN_DEBUG_GRAPH, width=100,
                command=_save_graph_debug)
            debug_btn.pack(side='right', padx=(0, 8))
            Tooltip(debug_btn, TIP_DEBUG_GRAPH)

        copy_shortcut = '<Command-c>' if sys.platform == 'darwin' else '<Control-c>'
        save_shortcut = '<Command-s>' if sys.platform == 'darwin' else '<Control-s>'
        win.bind('<Escape>', _destroy_graph_window)
        win.bind(copy_shortcut, _copy_graph)
        win.bind(save_shortcut, _save_graph)
        if graph_debug_enabled:
            win.bind('<Control-Shift-D>', _save_graph_debug)
            canvas.bind('<Control-Shift-D>', _save_graph_debug)
        win.protocol('WM_DELETE_WINDOW', _destroy_graph_window)
        self._path_graph_opened_this_session = True
        win.bind('<Configure>', _on_graph_configure)
        if repurpose_window:
            self._raise_window(win)
        else:
            win.update_idletasks()
            screen_x, screen_y, screen_w, screen_h = (
                self._window_display_bounds(self.root))
            previous_geometry = None
            if getattr(self, '_path_graph_opened_this_session', False):
                previous_geometry = getattr(self, '_path_graph_geometry', None)
            width, height, x, y = self._path_graph_window_geometry(
                graph_state['canvas_w'], graph_state['canvas_h'],
                screen_w, screen_h, screen_x, screen_y,
                previous_geometry=previous_geometry)
            win.geometry(f'{width}x{height}+{x}+{y}')
            self._raise_window(win)

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
        if (relationship_tooltip is None or
                not relationship_tooltip.is_for(tw)):
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
        if self.show_ids.get():
            name += f" [{start_id.strip('@')}]"
        self._results_header_var.set(name + lifespan)
        self._results_header_id = start_id
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

    def _show_results_header_menu(self, event):
        """Show a right-click context menu on the results pane title bar."""
        indi_id = getattr(self, '_results_header_id', None)
        if not indi_id:
            return 'break'
        menu = tk.Menu(self._results_header_label, tearoff=0)

        def _copy_name():
            self.root.clipboard_clear()
            self.root.clipboard_append(
                self._display_name(self.individuals[indi_id]))

        menu.add_command(
            label=RESULTS_HEADER_MENU_COPY_NAME,
            command=_copy_name)
        menu.add_command(
            label=RESULTS_HEADER_MENU_SHOW_PROFILE,
            command=lambda: self._show_person_for(indi_id, initial_view='profile'))
        menu.add_command(
            label=RESULTS_HEADER_MENU_SHOW_TREE,
            command=lambda: self._show_person_for(indi_id, initial_view='tree'))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return 'break'

    def _copy_results(self):
        """Copy the current results text to the clipboard."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        header = self._results_header_var.get().strip()
        if header:
            text = header + '\n\n' + text
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _save_results(self):
        """Save the current results text to a user-selected text file."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        header = self._results_header_var.get().strip()
        if header:
            text = header + '\n\n' + text
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
        self._results_header_id = None
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

    def _select_person_in_main_tree(self, indi_id):
        """Select a person in the main people list, clearing filters if needed."""
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
            return True

        # Person exceeds max_display even with no filters; clear stale
        # selections so action buttons fall back to _active_id.
        selection = self.tree.selection()
        if selection:
            self.tree.selection_remove(*selection)
        return False

    def _nav_snapshot(self):
        """Return a snapshot of the current navigable state."""
        return {
            'last_result': dict(self._last_result) if self._last_result else None,
            'active_id': self._active_id,
            'results_reversed': self._results_reversed,
        }

    def _nav_restore(self, snapshot):
        """Apply a navigation snapshot and re-render results."""
        self._last_result = snapshot['last_result']
        self._active_id = snapshot['active_id']
        self._results_reversed = snapshot['results_reversed']
        self._reverse_btn.configure(
            text=BTN_REVERSE_RESTORE if self._results_reversed else BTN_REVERSE)
        if self._active_id:
            self._select_person_in_main_tree(self._active_id)
        kind = self._last_result.get('type') if self._last_result else None
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

    def _navigate_back(self):
        """Restore the previous navigation state, saving current state for forward."""
        if self._busy or not self._nav_history:
            return
        self._nav_forward.append(self._nav_snapshot())
        self._nav_restore(self._nav_history.pop())

    def _navigate_forward(self):
        """Restore the next navigation state, saving current state for back."""
        if self._busy or not self._nav_forward:
            return
        self._nav_history.append(self._nav_snapshot())
        self._nav_restore(self._nav_forward.pop())

    def _navigate_to(self, indi_id):
        """Select a person in the tree and refresh the results pane for them.

        If the right pane currently shows DNA matches, shows DNA matches for the
        new person.  If it shows a relationship path, finds the path from the new
        person to the same destination.
        """
        if self._busy:
            return

        if self._last_result:
            self._nav_history.append(self._nav_snapshot())
            self._nav_forward.clear()

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
            self._show_progress()
            self._set_busy(True)

            def _do_path(cancel_event):
                return self._model.find_all_paths(
                    start_id, indi_id, top_n, max_depth,
                    cancel_event=cancel_event)

            def _on_cancel():
                self._hide_progress()
                self._set_busy(False)

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if error:
                    messagebox.showerror(ERR_PARSE_TITLE, str(error))
                    return
                paths, truncated = result
                self._last_result = {
                    'type': 'path',
                    'start_id': start_id,
                    'end_id': indi_id,
                }
                self._render_path_results(start_id, indi_id, paths, truncated)

            self._run_background_task(
                _do_path,
                _on_done,
                popup_message=PROGRESS_FINDING_PATH,
                cancelable=True,
                on_cancel=_on_cancel,
            )
        # for a "DNA" search, find the closest DNA markers to the newly selected person
        else:
            self._select_person_in_main_tree(indi_id)
            self._show_progress()
            self._set_busy(True)

            def _do_dna(cancel_event):
                return self._find_dna_result_data(
                    indi_id, top_n, max_depth, cancel_event=cancel_event)

            def _on_cancel():
                self._hide_progress()
                self._set_busy(False)

            def _on_done(result, error):
                self._hide_search_popup()
                self._hide_progress()
                self._set_busy(False)
                if error:
                    messagebox.showerror(ERR_PARSE_TITLE, str(error))
                    return
                results, home_paths = result
                self._last_result = {
                    'type': 'dna_matches', 'start_id': indi_id}
                self._render_results(indi_id, results, home_paths=home_paths)

            self._run_background_task(
                _do_dna,
                _on_done,
                popup_message=(
                    PROGRESS_SEARCHING
                    if self._is_slow_search(max_depth, len(self.individuals))
                    else None
                ),
                cancelable=True,
                on_cancel=_on_cancel,
            )

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
