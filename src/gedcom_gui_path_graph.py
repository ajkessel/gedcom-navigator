#!/usr/bin/env python3
"""
gedcom_gui_path_graph.py

Relationship path graph canvas rendering and graph-window orchestration.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

import customtkinter as ctk

from gedcom_debug import debug_enabled
from gedcom_family_tree import (
    EXPANDABLE_TREE_CATEGORIES,
    family_tree_expansion_options,
)
from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_tooltip import Tooltip
from gedcom_zoom import bind_zoom_shortcuts


class PathGraphMixin:
    """Relationship path graph rendering methods."""

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
        endpoint_label_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size), 7),
            weight='bold')
        badge_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size - 2), 6),
            weight='bold')
        button_font = tkfont.Font(
            family=ui_family,
            size=max(scale(ui_size - 2), 6),
            weight='bold')
        longest = 0
        for index, label in enumerate(labels):
            name_label, detail_label = (
                self._split_graph_label_name_detail(label)
                if layout[index].get('is_endpoint') else (label, '')
            )
            longest = max(
                longest,
                *(endpoint_label_font.measure(line)
                  for line in name_label.splitlines()),
                *(label_font.measure(line)
                  for line in detail_label.splitlines()),
            )
        show_images = bool(
            getattr(getattr(self, 'show_profile_image', None), 'get', lambda: False)())
        node_w = min(max(longest + scale(24), scale(112)), scale(190))
        if show_images:
            node_w = max(node_w, scale(126))
        label_width = node_w - (scale(12) if show_images else scale(22))
        wrapped_label_blocks = []
        for index, label in enumerate(labels):
            if layout[index].get('is_endpoint'):
                name_label, detail_label = (
                    self._split_graph_label_name_detail(label))
                wrapped_label_blocks.append((
                    self._wrap_canvas_label(
                        name_label, endpoint_label_font, label_width),
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
        endpoint_line_space = endpoint_label_font.metrics('linespace')
        block_heights = [
            ((name_label.count('\n') + 1) * (
                endpoint_line_space if layout[index].get('is_endpoint')
                else line_space)
             if name_label else 0)
            + ((detail_label.count('\n') + 1) * line_space
               if detail_label else 0)
            for index, (name_label, detail_label)
            in enumerate(wrapped_label_blocks)
        ]
        max_label_h = max(block_heights, default=line_space)
        thumb_w, thumb_h = (
            self._graph_thumbnail_size(scale) if show_images else (0, 0))
        if show_images:
            thumb_w = max(scale(48), node_w - scale(4))
            thumb_h = min(thumb_h, thumb_w)
        image_gap = scale(5) if show_images else 0
        image_inset = scale(2) if show_images else 0
        text_bottom_margin = scale(5) if show_images else 0
        if show_images:
            base_node_h = max(
                scale(82),
                image_inset + thumb_h + image_gap
                + max_label_h + text_bottom_margin)
        else:
            base_node_h = max(scale(82), max_label_h + scale(26))
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
        relationship_kinds = set()
        for index in range(1, len(layout)):
            if (not layout[index - 1].get('is_path_node')
                    or not layout[index].get('is_path_node')):
                continue
            edge = layout[index].get('edge')
            if edge in ('father', 'mother', 'child', 'sibling'):
                relationship_kinds.add(self._edge_relationship_kind(
                    layout[index - 1]['id'], layout[index]['id'],
                    'children' if edge == 'child'
                    else ('siblings' if edge == 'sibling' else 'parents')))
        relationship_kinds.update(
            self._edge_relationship_kind(source_id, target_id, category)
            for source_id, target_id, category in extra_edges
            if category in ('parents', 'children', 'siblings')
        )
        _legend_w, legend_h = self._graph_relationship_legend_size(
            label_font, scale, relationship_kinds)
        top_margin = margin + (legend_h + scale(12) if legend_h else 0)
        positions = []
        for node in layout:
            x = margin + node_w / 2 + (node['column'] - min_column) * h_gap
            y = top_margin + max_node_h / 2 + (
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
        canvas_h = top_margin + margin + max_node_h + (
            max_generation - min_generation) * v_gap

        for generation in range(min_generation, max_generation + 1):
            y = top_margin + max_node_h / 2 + (
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
                self._draw_graph_sibling_line(
                    canvas, start_x, y1, end_x, y2,
                    self._edge_relationship_kind(
                        layout[index - 1]['id'], layout[index]['id'], edge),
                    colors, scale)
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
                line_options = self._graph_parent_line_options(
                    self._edge_relationship_kind(
                        layout[index - 1]['id'], layout[index]['id'],
                        'children' if edge == 'child' else 'parents'),
                    colors, scale)
                canvas.create_line(
                    from_x, start_y, from_x, mid_y, x2, mid_y, x2, end_y,
                    arrow='last', **line_options,
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
                parent_ids = (
                    (target_id, coparent_id)
                    if parent_midpoint and coparent_id else (target_id,))
            elif category == 'children':
                parent_midpoint = self._child_parent_midpoint(
                    source_id, target_id, position_by_id,
                    self._co_parents_for_children, spouse_edges)
                coparent_id = self._visible_coparent_id(
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
                parent_ids = (
                    (source_id, coparent_id)
                    if parent_midpoint and coparent_id else (source_id,))
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
                self._draw_graph_sibling_line(
                    canvas, start_x, sy, end_x, ty,
                    self._edge_relationship_kind(
                        source_id, target_id, category),
                    colors, scale)
                continue

            start_y = parent_y + parent_h / 2
            end_y = child_y - child_h / 2
            mid_y = (start_y + end_y) / 2
            grouped_child_id = source_id if category == 'parents' else target_id
            line_options = self._graph_parent_line_options(
                self._combined_parent_child_kind(parent_ids, grouped_child_id),
                colors, scale)
            canvas.create_line(
                parent_x, start_y, parent_x, mid_y, child_x, mid_y,
                child_x, end_y, arrow='last', **line_options,
                arrowshape=(scale(12), scale(14), scale(5)))

        self._draw_graph_relationship_legend(
            canvas, colors, scale, label_font, relationship_kinds)

        highlighted_nodes = getattr(canvas, '_highlighted_nodes', set())
        canvas._profile_image_refs = []

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

        for index, ((x, y), label_block) in enumerate(
                zip(positions, wrapped_label_blocks)):
            node_id = layout[index]['id']
            node_tag = f'path_node_{index}'
            node_h = node_heights[index]
            x1 = x - node_w / 2
            y1 = y - node_h / 2
            x2 = x + node_w / 2
            y2 = y + node_h / 2
            is_endpoint = layout[index].get('is_endpoint')
            fill = self._person_box_fill(self.individuals, node_id)
            if is_endpoint:
                fill = self._endpoint_person_box_fill(fill, colors)
            outline_width = scale(3) if is_endpoint else scale(2)
            if node_id in highlighted_nodes:
                fill = self.PERSON_BOX_FILL_HIGHLIGHT
                node_outline = self.PERSON_BOX_OUTLINE_HIGHLIGHT
                outline_width = scale(4)
            else:
                node_outline = colors['node_outline']
            canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline=node_outline,
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
                name_label, detail_label = label_block
                name_lines = name_label.count('\n') + 1 if name_label else 0
                detail_lines = (
                    detail_label.count('\n') + 1 if detail_label else 0)
                name_h = name_lines * endpoint_line_space
                detail_h = detail_lines * line_space
                text_top = text_y - (name_h + detail_h) / 2
                if show_images:
                    payload = self._profile_media_payload(node_id, (thumb_w, thumb_h))
                    if payload and payload.get('image') is not None:
                        image_tag = f'{node_tag}_photo'
                        image_top = y1 + endpoint_header_h + image_inset
                        image_tags = (
                            ('path_node_photo', image_tag)
                            if payload.get('kind') == 'real'
                            else ('path_node', node_tag, image_tag)
                        )
                        canvas.create_image(
                            x, image_top + thumb_h / 2,
                            image=payload['image'], anchor='center',
                            tags=image_tags)
                        canvas._profile_image_refs.append(payload['image'])
                        if payload.get('kind') == 'real':
                            canvas.tag_bind(
                                image_tag, '<Enter>',
                                lambda *_: canvas.configure(cursor='hand2'))
                            canvas.tag_bind(
                                image_tag, '<Leave>',
                                lambda *_: canvas.configure(cursor=''))
                            canvas.tag_bind(
                                image_tag, '<Button-1>',
                                lambda event, path=payload.get('path'): (
                                    self._show_full_profile_image(
                                        path, parent=canvas.winfo_toplevel()),
                                    'break',
                                )[-1])
                    text_top = (
                        y1 + endpoint_header_h + image_inset + thumb_h + image_gap)
                if name_label:
                    canvas.create_text(
                        x, text_top + name_h / 2,
                        text=name_label, fill=self.PERSON_BOX_TEXT,
                        font=endpoint_label_font, width=label_width,
                        justify='center', tags=('path_node', node_tag))
                if detail_label:
                    canvas.create_text(
                        x, text_top + name_h + detail_h / 2,
                        text=detail_label, fill=self.PERSON_BOX_TEXT,
                        font=label_font, width=label_width,
                        justify='center', tags=('path_node', node_tag))
            else:
                label, _ = label_block
                text_y = y
                text_top = None
                if show_images:
                    payload = self._profile_media_payload(node_id, (thumb_w, thumb_h))
                    if payload and payload.get('image') is not None:
                        image_tag = f'{node_tag}_photo'
                        image_tags = (
                            ('path_node_photo', image_tag)
                            if payload.get('kind') == 'real'
                            else ('path_node', node_tag, image_tag)
                        )
                        canvas.create_image(
                            x, y1 + image_inset + thumb_h / 2, image=payload['image'],
                            anchor='center',
                            tags=image_tags)
                        canvas._profile_image_refs.append(payload['image'])
                        if payload.get('kind') == 'real':
                            canvas.tag_bind(
                                image_tag, '<Enter>',
                                lambda *_: canvas.configure(cursor='hand2'))
                            canvas.tag_bind(
                                image_tag, '<Leave>',
                                lambda *_: canvas.configure(cursor=''))
                            canvas.tag_bind(
                                image_tag, '<Button-1>',
                                lambda event, path=payload.get('path'): (
                                    self._show_full_profile_image(
                                        path, parent=canvas.winfo_toplevel()),
                                    'break',
                                )[-1])
                        text_top = y1 + image_inset + thumb_h + image_gap
                        text_y = text_top + block_heights[index] / 2
                canvas.create_text(
                    x, text_y, text=label, fill=self.PERSON_BOX_TEXT,
                    font=label_font,
                    width=label_width, justify='center',
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
                    _menu_kw = {'font': tkfont.nametofont('TkMenuFont')} if sys.platform == 'win32' else {}
                    menu = tk.Menu(canvas, tearoff=0, **_menu_kw)
                    menu.add_command(
                        label=PATH_GRAPH_MENU_SHOW_TREE,
                        command=(
                            lambda: on_show_tree(indi_id)
                            if on_show_tree else None))
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
                    members = self._family_tree_members_for(node_id)
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
                                options, expanded_set, node_id, category,
                                members):
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
        canvas._highlighted_nodes = set()
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
            if debug_enabled():
                graph_state['debug_payload'] = self._graph_debug_payload(
                    graph_state, layout, extra_edges,
                    self._family_tree_members_for,
                    relationship_lookup=self._edge_relationship_kind)

        canvas._redraw_fn = _redraw_graph

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

        def _maybe_grow_graph_win():
            """Grow window to fit expanded content; skip if already maximized."""
            try:
                is_max = (win.state() == 'zoomed' if sys.platform == 'win32'
                          else bool(win.attributes('-zoomed')))
            except tk.TclError:
                is_max = False
            if is_max:
                return
            try:
                win.update_idletasks()
                _, _, screen_w, screen_h = self._window_display_bounds(self.root)
                tnw = int(graph_state['canvas_w']) + 56
                tnh = int(graph_state['canvas_h']) + 128
                if tnw >= screen_w or tnh >= screen_h:
                    win.state('zoomed')
                else:
                    cur_w = win.winfo_width()
                    cur_h = win.winfo_height()
                    new_w = max(cur_w, tnw)
                    new_h = max(cur_h, tnh)
                    if new_w > cur_w or new_h > cur_h:
                        tsw = self.root.winfo_screenwidth()
                        tsh = self.root.winfo_screenheight()
                        cx, cy = win.winfo_x(), win.winfo_y()
                        win.geometry(
                            f"{int(new_w)}x{int(new_h)}"
                            f"+{max(0, min(cx, tsw - new_w))}"
                            f"+{max(0, min(cy, tsh - new_h))}"
                        )
            except tk.TclError:
                pass

        def _expand_graph_node(indi_id, category):
            request = (indi_id, category)
            self._toggle_expansion_request(graph_state['expanded'], request)
            _redraw_graph()
            _maybe_grow_graph_win()

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
        Tooltip(copy_btn, get_tip_copy_graph())
        save_btn = ctk.CTkButton(
            btn_frame, text=BTN_SAVE_GRAPH, width=80, command=_save_graph)
        save_btn.pack(side='right', padx=(0, 8))
        Tooltip(save_btn, get_tip_save_graph())
        graph_debug_enabled = debug_enabled()
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
