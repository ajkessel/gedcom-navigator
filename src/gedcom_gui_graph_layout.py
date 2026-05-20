#!/usr/bin/env python3
"""
gedcom_gui_graph_layout.py

Pure layout helpers for relationship graph path and expansion rendering.
"""

from gedcom_family_tree import _nearest_unblocked_column


class GraphLayoutMixin:
    """Path graph layout helpers shared by result graph renderers."""

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

        def enforce_same_row_spacing():
            """Ensure final same-row node columns never overlap."""
            generations = sorted({node['generation'] for node in layout})
            for generation in generations:
                row = sorted(
                    [
                        node for node in layout
                        if node['generation'] == generation
                    ],
                    key=lambda node: node['column'],
                )
                for index in range(1, len(row)):
                    minimum_column = round(
                        row[index - 1]['column'] + min_spacing, 3)
                    if row[index]['column'] >= minimum_column:
                        continue
                    shift = round(minimum_column - row[index]['column'], 3)
                    for node in row[index:]:
                        node['column'] = round(node['column'] + shift, 3)
            rebuild_occupied()

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
            enforce_same_row_spacing()
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
        enforce_same_row_spacing()
        return layout, extra_edges
