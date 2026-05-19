#!/usr/bin/env python3
"""
gedcom_gui_graph_common.py

Shared graph colors, export, clipboard, debug, and navigation helpers.
"""

import io
import json
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

from gedcom_display import lifespan
from gedcom_family_tree import EXPANDABLE_TREE_CATEGORIES
from gedcom_graph_export import canvas_to_png_bytes, canvas_to_svg
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_theme import get_link_color, ttk_colors
from gedcom_tooltip import CanvasTagTooltip


class GraphCommonMixin:
    """Shared graph helper methods."""

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
    def _split_graph_label_name_detail(label):
        """Return graph label name lines and trailing lifespan/detail line."""
        lines = label.splitlines()
        if len(lines) <= 1:
            return label, ''

        detail = lines[-1].strip()
        if re.match(r'^(?:\d+\s*-\s*\d+|b\. \d+|d\. \d+)$', detail):
            return '\n'.join(lines[:-1]), lines[-1]
        return label, ''

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

    @classmethod
    def _endpoint_person_box_fill(cls, base_fill, colors):
        """Return a subtly darker endpoint fill that keeps the sex color cue."""
        tinted_fill = cls._mix_hex_color(
            base_fill, colors['endpoint_fill'], 0.25)
        return cls._mix_hex_color(tinted_fill, cls.PERSON_BOX_TEXT, 0.08)

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
