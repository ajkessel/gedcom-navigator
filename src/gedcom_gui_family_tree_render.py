#!/usr/bin/env python3
"""
gedcom_gui_family_tree_render.py

Family-tree canvas rendering helpers for person detail windows.
"""

import math
import sys
import tkinter as tk
import tkinter.font as tkfont

from gedcom_display import lifespan
from gedcom_family_tree import (
    EXPANDABLE_TREE_CATEGORIES,
    build_family_tree_graph,
    family_tree_expansion_options,
    layout_family_tree,
)
from gedcom_strings import *  # pylint: disable=unused-wildcard-import


class FamilyTreeRenderMixin:
    """Family tree graph rendering helpers."""

    @staticmethod
    def _horizontal_tree_font_shrink(zoom):
        """Return extra pedigree font shrink applied only at low zoom."""
        if zoom >= 1.0:
            return 0
        return min(3, max(0, int(round((1.0 - zoom) * 6))))

    @staticmethod
    def _horizontal_parent_connector_segments(source_right_x, source_y,
                                              parent_points, node_h):
        """Return right-angle horizontal-pedigree parent connector segments."""
        if not parent_points:
            return []
        if len(parent_points) == 1:
            end_x, target_y = parent_points[0]
            if abs(target_y - source_y) < 0.001:
                return [(source_right_x, source_y, end_x, target_y)]
            bus_x = FamilyTreeRenderMixin._horizontal_parent_bus_x(
                source_right_x, end_x, node_h)
            return [(
                source_right_x, source_y,
                bus_x, source_y,
                bus_x, target_y,
                end_x, target_y,
            )]

        parent_left_x = min(end_x for end_x, _target_y in parent_points)
        bus_x = FamilyTreeRenderMixin._horizontal_parent_bus_x(
            source_right_x, parent_left_x, node_h)
        parent_ys = [target_y for _end_x, target_y in parent_points]
        min_y = min(parent_ys + [source_y])
        max_y = max(parent_ys + [source_y])
        segments = [
            (source_right_x, source_y, bus_x, source_y),
            (bus_x, min_y, bus_x, max_y),
        ]
        segments.extend(
            (bus_x, target_y, end_x, target_y)
            for end_x, target_y in parent_points
        )
        return segments

    @staticmethod
    def _horizontal_parent_bus_x(source_right_x, parent_left_x, node_h):
        """Return the vertical connector bus x-position between generations."""
        gap = parent_left_x - source_right_x
        if gap <= 0:
            return (source_right_x + parent_left_x) / 2
        offset = min(max(node_h * 0.45, gap * 0.18), gap * 0.5)
        return source_right_x + offset

    @staticmethod
    def _arc_points(cx, cy, radius, start_degrees, end_degrees, steps=8):
        """Return points approximating a canvas arc."""
        if steps <= 0:
            steps = 1
        return [
            (
                cx + radius * math.cos(math.radians(
                    start_degrees + (end_degrees - start_degrees) * index
                    / steps)),
                cy + radius * math.sin(math.radians(
                    start_degrees + (end_degrees - start_degrees) * index
                    / steps)),
            )
            for index in range(steps + 1)
        ]

    @classmethod
    def _expansion_button_tab_points(cls, bx, by, button_size, category, side):
        """Return a tab polygon with only the exposed corners rounded."""
        half = button_size / 2
        radius = half
        x1, y1 = bx - half, by - half
        x2, y2 = bx + half, by + half

        if category == 'parents':
            points = [(x1, y2), (x1, by)]
            points.extend(cls._arc_points(bx, by, radius, 180, 360))
            points.append((x2, y2))
        elif category == 'children':
            points = [(x1, y1), (x1, by)]
            points.extend(cls._arc_points(bx, by, radius, 180, 0))
            points.append((x2, y1))
        elif side == 'left':
            points = [(x2, y1), (bx, y1)]
            points.extend(cls._arc_points(bx, by, radius, 270, 90))
            points.append((x2, y2))
        else:
            points = [(x1, y1), (bx, y1)]
            points.extend(cls._arc_points(bx, by, radius, 270, 450))
            points.append((x1, y2))

        return tuple(coordinate for point in points for coordinate in point)

    @classmethod
    def _draw_expansion_button_tab(cls, canvas, bx, by, button_size, category,
                                   side, fill, outline, tags):
        """Draw an expand/collapse button as an attached rounded-edge tab."""
        canvas.create_polygon(
            *cls._expansion_button_tab_points(
                bx, by, button_size, category, side),
            fill=fill,
            outline=outline,
            width=1,
            tags=tags,
        )

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

    @classmethod
    def _child_parent_midpoint(cls, parent_id, child_id, positions,
                               coparent_lookup, spouse_edges=()):
        """Return the midpoint between displayed parents for a child edge."""
        coparent_id = cls._visible_coparent_id(
            parent_id, child_id, positions, coparent_lookup, spouse_edges)
        if not coparent_id:
            return None
        parent_x, parent_y = positions[parent_id]
        coparent_x, coparent_y = positions[coparent_id]
        return (
            (parent_x + coparent_x) / 2,
            (parent_y + coparent_y) / 2,
        )

    @classmethod
    def _family_tree_child_edge_groups(cls, edges, positions, coparent_lookup,
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

            coparent_id = cls._visible_coparent_id(
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
                                   on_find_paths=None, on_expand_all=None,
                                   graph_builder=None,
                                   layout_builder=layout_family_tree,
                                   expandable_categories=None,
                                   expansion_options_lookup=None,
                                   expanded_for_buttons=None,
                                   orientation='vertical',
                                   graph_type='family_tree',
                                   expand_all_categories_lookup=None,
                                   progress_callback=None):
        """Draw a family-tree-style graph canvas."""
        zoom = max(0.5, min(2.5, float(zoom)))
        progress_units = {'count': 0}

        def pulse_progress(step=1):
            if progress_callback is None:
                return
            progress_units['count'] += step
            if progress_units['count'] >= 60:
                progress_units['count'] = 0
                progress_callback()

        expandable_categories = (
            tuple(EXPANDABLE_TREE_CATEGORIES)
            if expandable_categories is None else tuple(expandable_categories)
        )
        if graph_builder is None:
            visible_ids, edges = build_family_tree_graph(
                center_id, expanded, self._family_tree_members_for,
                self._co_parents_for_children)
        else:
            visible_ids, edges = graph_builder()
        layout = layout_builder(center_id, visible_ids, edges)
        visible_set = set(visible_ids)
        expanded_set = set(
            expanded if expanded_for_buttons is None else expanded_for_buttons)
        self._clear_canvas_tag_tooltips(canvas)

        def scale(value, minimum=1):
            return max(minimum, int(round(value * zoom)))

        ui_family, ui_size = self._graph_ui_font()
        label_size = scale(ui_size)
        center_label_size = scale(ui_size)
        button_label_size = scale(ui_size - 2)
        if orientation == 'horizontal':
            font_shrink = self._horizontal_tree_font_shrink(zoom)
            label_size = scale(ui_size - font_shrink, minimum=6)
            center_label_size = scale(ui_size - font_shrink, minimum=6)
        label_font = tkfont.Font(
            family=ui_family,
            size=max(label_size, 7 if orientation != 'horizontal' else 6))
        center_label_font = tkfont.Font(
            family=ui_family,
            size=max(center_label_size, 7 if orientation != 'horizontal' else 6),
            weight='bold')
        button_font = tkfont.Font(
            family=ui_family,
            size=max(button_label_size, 6),
            weight='bold')

        labels = [
            self._compact_graph_label(self.individuals[node['id']])
            if node['id'] in self.individuals else node['id']
            for node in layout
        ]
        longest = 0
        for node, label in zip(layout, labels):
            name_label, detail_label = (
                self._split_graph_label_name_detail(label)
                if node['is_center'] else (label, '')
            )
            longest = max(
                longest,
                *(center_label_font.measure(line)
                  for line in name_label.splitlines()),
                *(label_font.measure(line)
                  for line in detail_label.splitlines()),
            )
        if orientation == 'horizontal':
            node_w = min(max(longest + scale(18), scale(78)), scale(150))
        else:
            node_w = min(max(longest + scale(24), scale(112)), scale(190))
        label_width = node_w - scale(24)
        wrapped_label_blocks = []
        for node, label in zip(layout, labels):
            if node['is_center']:
                name_label, detail_label = (
                    self._split_graph_label_name_detail(label))
                wrapped_label_blocks.append((
                    self._wrap_canvas_label(
                        name_label, center_label_font, label_width),
                    self._wrap_canvas_label(
                        detail_label, label_font, label_width)
                    if detail_label else '',
                ))
            else:
                wrapped_label_blocks.append((
                    self._wrap_canvas_label(label, label_font, label_width),
                    '',
                ))
        line_space = label_font.metrics('linespace')
        center_line_space = center_label_font.metrics('linespace')
        block_heights = [
            ((name_label.count('\n') + 1) * (
                center_line_space if node['is_center'] else line_space)
             if name_label else 0)
            + ((detail_label.count('\n') + 1) * line_space
               if detail_label else 0)
            for node, (name_label, detail_label)
            in zip(layout, wrapped_label_blocks)
        ]
        max_label_h = max(block_heights, default=line_space)
        if orientation == 'horizontal':
            node_h = max(scale(34), max_label_h + scale(12))
            h_gap = node_w + scale(34)
            v_gap = max(node_h + scale(4), scale(30))
            margin = scale(36)
        else:
            node_h = max(scale(84), max_label_h + scale(26))
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
            if orientation == 'horizontal':
                x = margin + node_w / 2 + (
                    node['column'] - min_column) * h_gap
                y = margin + node_h / 2 + (
                    node['generation'] - min_generation) * v_gap
            else:
                x = margin + node_w / 2 + (
                    node['column'] - min_column) * h_gap
                y = margin + node_h / 2 + (
                    node['generation'] - min_generation) * v_gap
            positions[node['id']] = (x, y)
        canvas._family_tree_center = positions.get(center_id, (0, 0))
        canvas._family_tree_positions = dict(positions)
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
            edges, layout, self._family_tree_members_for,
            graph_type=graph_type)

        if orientation == 'horizontal':
            for column in range(int(min_column), int(max_column) + 1):
                x = margin + node_w / 2 + (column - min_column) * h_gap
                canvas.create_line(
                    x, margin / 2, x, canvas_h - margin / 2,
                    fill=colors['guide'], dash=(scale(3), scale(8)))
            parent_edges_by_source = {}
            for source_id, target_id, category in edges:
                if category != 'parents':
                    continue
                parent_edges_by_source.setdefault(source_id, []).append(
                    target_id)
            for source_id, target_ids in parent_edges_by_source.items():
                pulse_progress()
                if source_id not in positions:
                    continue
                sx, sy = positions[source_id]
                parent_points = []
                for target_id in target_ids:
                    if target_id not in positions:
                        continue
                    tx, ty = positions[target_id]
                    parent_points.append((tx - node_w / 2, ty))
                for points in self._horizontal_parent_connector_segments(
                        sx + node_w / 2, sy, parent_points, node_h):
                    pulse_progress()
                    canvas.create_line(
                        *points, fill=colors['parent'], width=scale(3),
                        smooth=False)
        else:
            for generation in range(
                    int(min_generation), int(max_generation) + 1):
                y = margin + node_h / 2 + (
                    generation - min_generation) * v_gap
                canvas.create_line(
                    margin / 2, y, canvas_w - margin / 2, y,
                    fill=colors['guide'], dash=(scale(3), scale(8)))

            for source_id, target_id, category in edges:
                pulse_progress()
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
                pulse_progress()
                parent_x = group['parent_x']
                parent_y = group['parent_y']
                parent_h = (
                    node_h if group['parent_h'] is None else group['parent_h'])
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
                    pulse_progress()
                    child_x, child_y = positions[child_id]
                    canvas.create_line(
                        child_x, mid_y, child_x, child_y - node_h / 2,
                        fill=colors['parent'], width=scale(3), arrow='last',
                        arrowshape=(scale(12), scale(14), scale(5)))

        highlighted_nodes = getattr(canvas, '_highlighted_nodes', set())

        def _toggle_highlight(indi_id):
            nodes = getattr(canvas, '_highlighted_nodes', set())
            if indi_id in nodes:
                nodes.discard(indi_id)
            else:
                nodes.add(indi_id)
            canvas._highlighted_nodes = nodes
            redraw = getattr(canvas, '_redraw_fn', None)
            if redraw:
                redraw()

        for index, (node, label_block) in enumerate(
                zip(layout, wrapped_label_blocks)):
            pulse_progress()
            node_id = node['id']
            x, y = positions[node_id]
            x1 = x - node_w / 2
            y1 = y - node_h / 2
            x2 = x + node_w / 2
            y2 = y + node_h / 2
            node_tag = f'family_tree_node_{index}'
            fill = self._person_box_fill(self.individuals, node_id)
            if node['is_center']:
                fill = self._endpoint_person_box_fill(fill, colors)
            outline_width = scale(3) if node['is_center'] else scale(2)
            if node_id in highlighted_nodes:
                fill = self.PERSON_BOX_FILL_HIGHLIGHT
                node_outline = self.PERSON_BOX_OUTLINE_HIGHLIGHT
                outline_width = scale(4)
            else:
                node_outline = colors['node_outline']
            canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline=node_outline,
                width=outline_width, tags=('family_tree_node', node_tag))
            name_label, detail_label = label_block
            if node['is_center']:
                name_lines = name_label.count('\n') + 1 if name_label else 0
                detail_lines = (
                    detail_label.count('\n') + 1 if detail_label else 0)
                name_h = name_lines * center_line_space
                detail_h = detail_lines * line_space
                text_top = y - (name_h + detail_h) / 2
                if name_label:
                    canvas.create_text(
                        x, text_top + name_h / 2,
                        text=name_label, fill=self.PERSON_BOX_TEXT,
                        font=center_label_font, width=label_width,
                        justify='center',
                        tags=('family_tree_node', node_tag))
                if detail_label:
                    canvas.create_text(
                        x, text_top + name_h + detail_h / 2,
                        text=detail_label, fill=self.PERSON_BOX_TEXT,
                        font=label_font, width=label_width, justify='center',
                        tags=('family_tree_node', node_tag))
            else:
                canvas.create_text(
                    x, y, text=name_label, fill=self.PERSON_BOX_TEXT,
                    font=label_font,
                    width=label_width, justify='center',
                    tags=('family_tree_node', node_tag))
            members = self._family_tree_members_for(node_id)
            if expansion_options_lookup is None:
                options = family_tree_expansion_options(
                    node_id, visible_set, self._family_tree_members_for)
            else:
                options = expansion_options_lookup(node_id, visible_set)
            hidden_categories = tuple(
                category for category in expandable_categories
                if options.get(category))
            if expand_all_categories_lookup is None:
                expand_all_categories = hidden_categories
            else:
                expand_all_categories = tuple(
                    expand_all_categories_lookup(node_id, visible_set))

            if node_id in self.individuals:
                canvas.tag_bind(
                    node_tag, '<Enter>',
                    lambda *_: canvas.configure(cursor='hand2'))
                canvas.tag_bind(
                    node_tag, '<Leave>',
                    lambda *_: canvas.configure(cursor=''))

                def _show_node_menu(event, indi_id=node_id,
                                    categories=expand_all_categories):
                    if getattr(canvas, '_family_tree_dragged', False):
                        return 'break'
                    _menu_kw = {'font': tkfont.nametofont('TkMenuFont')} if sys.platform == 'win32' else {}
                    menu = tk.Menu(canvas, tearoff=0, **_menu_kw)
                    menu.add_command(
                        label=TREE_MENU_RECENTER,
                        command=lambda: on_recenter(indi_id))
                    menu.add_command(
                        label=GRAPH_MENU_HIGHLIGHT,
                        command=lambda iid=indi_id: _toggle_highlight(iid))
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
                        label=TREE_MENU_PATHS,
                        command=(
                            lambda: on_find_paths(indi_id)
                            if on_find_paths else None))
                    if categories and on_expand_all:
                        menu.add_command(
                            label=TREE_MENU_EXPAND_ALL,
                            command=lambda: on_expand_all(indi_id, categories))
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
            for category in expandable_categories:
                pulse_progress()
                if not self._show_expansion_button(
                        options, expanded_set, node_id, category, members):
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
                button_tags = ('family_tree_button', button_tag)
                self._draw_expansion_button_tab(
                    canvas, bx, by, button_size, category, button_side,
                    button_fill, colors['guide'], button_tags)
                canvas.create_text(
                    bx, by, text=text, fill=button_text,
                    font=button_font, anchor='center',
                    tags=button_tags)

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

        pulse_progress(60)
        self._center_graph_canvas(canvas, canvas_w, canvas_h)
        return canvas_w, canvas_h
