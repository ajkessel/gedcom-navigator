#!/usr/bin/env python3
"""
gedcom_family_tree.py

Pure helpers for building and laying out immediate-family tree graphs.
"""

from collections import defaultdict, deque


INITIAL_TREE_CATEGORIES = ('parents', 'siblings', 'spouses', 'children')
EXPANDABLE_TREE_CATEGORIES = ('parents', 'siblings', 'spouses', 'children')
LAYOUT_TREE_CATEGORIES = ('parents', 'spouses', 'siblings', 'children')
MIN_COLUMN_SPACING = 1.0


def build_family_tree_graph(center_id, expanded, family_lookup,
                            coparent_lookup=None):
    """Return visible IDs and relationship edges for a family tree view."""
    visible = [center_id]
    visible_set = {center_id}
    edges = []
    edge_set = set()
    requests = list(expanded)

    for source_id, category in requests:
        if source_id not in visible_set:
            continue
        members = family_lookup(source_id).get(category, ())
        for target_id in members:
            if not target_id or target_id == source_id:
                continue
            if target_id not in visible_set:
                visible.append(target_id)
                visible_set.add(target_id)
            edge = (source_id, target_id, category)
            if edge not in edge_set:
                edges.append(edge)
                edge_set.add(edge)
        if category == 'children' and coparent_lookup:
            for parent_id in coparent_lookup(source_id, members):
                if not parent_id or parent_id == source_id:
                    continue
                if parent_id not in visible_set:
                    visible.append(parent_id)
                    visible_set.add(parent_id)
                edge = (source_id, parent_id, 'spouses')
                if edge not in edge_set:
                    edges.append(edge)
                    edge_set.add(edge)
        elif category == 'parents' and coparent_lookup:
            visible_parents = set(members)
            for parent_id in members:
                for other_parent_id in coparent_lookup(parent_id, (source_id,)):
                    if other_parent_id not in visible_parents:
                        continue
                    edge = (parent_id, other_parent_id, 'spouses')
                    reverse_edge = (other_parent_id, parent_id, 'spouses')
                    if edge not in edge_set and reverse_edge not in edge_set:
                        edges.append(edge)
                        edge_set.add(edge)

    return visible, edges


def family_tree_expansion_options(indi_id, visible_ids, family_lookup):
    """Return expandable categories that have hidden relatives."""
    visible = set(visible_ids)
    members = family_lookup(indi_id)
    return {
        category: [
            target_id for target_id in members.get(category, ())
            if target_id and target_id not in visible and target_id != indi_id
        ]
        for category in EXPANDABLE_TREE_CATEGORIES
    }


def _centered_offsets(count, step=1.4):
    if count <= 0:
        return []
    start = -((count - 1) * step) / 2
    return [start + index * step for index in range(count)]


def _side_offsets(count, direction, step=1.4):
    return [direction * (index + 1) * step for index in range(count)]


def _next_open_column(column, used_columns):
    """Return a column with enough horizontal room from existing boxes."""
    while any(abs(column - used) < MIN_COLUMN_SPACING for used in used_columns):
        column += MIN_COLUMN_SPACING
    return column


def _nearest_unblocked_column(column, blocked_columns):
    """Return the nearest column not inside any blocked spacing band."""
    blocked_columns = list(blocked_columns)
    if not any(
            abs(column - blocked) < MIN_COLUMN_SPACING
            for blocked in blocked_columns):
        return column

    candidates = []
    for blocked in blocked_columns:
        candidates.extend((
            blocked - MIN_COLUMN_SPACING,
            blocked + MIN_COLUMN_SPACING,
        ))
    return min(
        (
            candidate for candidate in candidates
            if not any(
                abs(candidate - blocked) < MIN_COLUMN_SPACING
                for blocked in blocked_columns)
        ),
        key=lambda candidate: (abs(candidate - column), candidate),
    )


def _rebuild_occupied(occupied, positions):
    occupied.clear()
    for generation, column in positions.values():
        occupied[generation].append(column)


def _compact_row_gaps(positions, protected_ids=()):
    """Close excessive same-row gaps left by conflict resolution."""
    protected_ids = set(protected_ids)
    max_allowed_gap = MIN_COLUMN_SPACING * 2
    by_generation = defaultdict(list)
    for person_id, (generation, column) in positions.items():
        by_generation[generation].append((column, person_id))
    for generation, row in by_generation.items():
        row = sorted(row)
        if len(row) < 2:
            continue
        previous_column = row[0][0]
        for column, person_id in row[1:]:
            if person_id not in protected_ids and (
                    column - previous_column > max_allowed_gap):
                column = previous_column + MIN_COLUMN_SPACING
                positions[person_id] = (generation, column)
            previous_column = column


def _resolve_same_row_conflicts(positions, protected_ids=()):
    """Move same-row boxes apart after final adjacency adjustments."""
    protected_ids = set(protected_ids)
    by_generation = defaultdict(list)
    for person_id, (generation, column) in positions.items():
        by_generation[generation].append((column, person_id))

    for generation, row in by_generation.items():
        row = sorted(row)
        for index in range(1, len(row)):
            previous_column, previous_id = row[index - 1]
            column, person_id = row[index]
            if column - previous_column >= MIN_COLUMN_SPACING:
                continue
            if person_id in protected_ids and previous_id not in protected_ids:
                previous_column = column - MIN_COLUMN_SPACING
                positions[previous_id] = (generation, previous_column)
                row[index - 1] = (previous_column, previous_id)
            elif person_id not in protected_ids:
                column = previous_column + MIN_COLUMN_SPACING
                positions[person_id] = (generation, column)
                row[index] = (column, person_id)


def _reserve_same_row_slot(positions, occupied, generation, column,
                           protected_id):
    """Move same-row boxes aside so a spouse can sit next to their partner."""
    protected_ids = (
        set(protected_id)
        if isinstance(protected_id, (set, tuple, list))
        else {protected_id}
    )
    while True:
        conflicts = [
            target_id for target_id, pos in positions.items()
            if (target_id not in protected_ids
                and pos[0] == generation
                and abs(pos[1] - column) < MIN_COLUMN_SPACING)
        ]
        if not conflicts:
            break
        boundary = min(positions[target_id][1] for target_id in conflicts)
        for target_id, (target_generation, target_column) in list(
                positions.items()):
            if (target_id not in protected_ids
                    and target_generation == generation
                    and target_column >= boundary):
                positions[target_id] = (
                    target_generation,
                    target_column + MIN_COLUMN_SPACING,
                )
        _rebuild_occupied(occupied, positions)


def _visible_spouse_ids(source_id, relations, positions):
    spouse_ids = list(relations[source_id].get('spouses', ()))
    for other_id, rels in relations.items():
        if source_id in rels.get('spouses', ()):
            spouse_ids.append(other_id)
    return [spouse_id for spouse_id in spouse_ids if spouse_id in positions]


def _visible_spouse_columns(source_id, relations, positions):
    return [
        positions[spouse_id][1]
        for spouse_id in _visible_spouse_ids(source_id, relations, positions)
    ]


def _visible_spouse_pairs(relations, positions):
    pairs = []
    seen = set()
    for source_id in positions:
        for spouse_id in _visible_spouse_ids(source_id, relations, positions):
            edge_key = tuple(sorted((source_id, spouse_id)))
            if edge_key in seen:
                continue
            seen.add(edge_key)
            pairs.append((source_id, spouse_id))
    return pairs


def _visible_child_ids(source_id, relations, positions):
    child_ids = list(relations[source_id].get('children', ()))
    for spouse_id in _visible_spouse_ids(source_id, relations, positions):
        child_ids.extend(relations[spouse_id].get('children', ()))
    for other_id, rels in relations.items():
        if source_id in rels.get('parents', ()):
            child_ids.append(other_id)
        for spouse_id in _visible_spouse_ids(source_id, relations, positions):
            if spouse_id in rels.get('parents', ()):
                child_ids.append(other_id)
    visible = []
    seen = set()
    for child_id in child_ids:
        if child_id in positions and child_id not in seen:
            visible.append(child_id)
            seen.add(child_id)
    return visible


def layout_family_tree(center_id, visible_ids, edges):
    """Return family-tree nodes with generation and column coordinates."""
    relations = defaultdict(lambda: defaultdict(list))
    for source_id, target_id, category in edges:
        relations[source_id][category].append(target_id)

    positions = {center_id: (0, 0.0)}
    occupied = defaultdict(list)
    occupied[0].append(0.0)
    queue = deque([center_id])

    def assign(target_id, generation, column):
        column = _next_open_column(column, occupied[generation])
        positions[target_id] = (generation, column)
        occupied[generation].append(column)
        queue.append(target_id)

    def enforce_spouse_adjacency():
        seen = set()
        for source_id in list(positions):
            for spouse_id in _visible_spouse_ids(source_id, relations, positions):
                edge_key = tuple(sorted((source_id, spouse_id)))
                if edge_key in seen:
                    continue
                seen.add(edge_key)
                source_generation, source_column = positions[source_id]
                spouse_generation, spouse_column = positions[spouse_id]
                if source_generation != spouse_generation:
                    continue
                desired_column = (
                    source_column + MIN_COLUMN_SPACING
                    if spouse_column >= source_column
                    else source_column - MIN_COLUMN_SPACING
                )
                if abs(spouse_column - desired_column) < 0.001:
                    continue
                _reserve_same_row_slot(
                    positions, occupied, source_generation, desired_column,
                    {source_id, spouse_id})
                positions[spouse_id] = (spouse_generation, desired_column)
                _rebuild_occupied(occupied, positions)

    def enforce_child_alignment():
        assigned_child_columns_by_generation = defaultdict(list)
        aligned_child_groups = set()
        for source_id in sorted(
                list(positions),
                key=lambda item: (positions[item][0], positions[item][1])):
            source_generation, source_column = positions[source_id]
            child_generation = source_generation + 1
            child_ids = [
                child_id for child_id in _visible_child_ids(
                    source_id, relations, positions)
                if positions[child_id][0] == child_generation
            ]
            if not child_ids:
                continue
            child_group_key = (child_generation, frozenset(child_ids))
            if child_group_key in aligned_child_groups:
                continue
            aligned_child_groups.add(child_group_key)
            spouse_columns = _visible_spouse_columns(
                source_id, relations, positions)
            base_column = (
                (source_column + spouse_columns[0]) / 2
                if spouse_columns else source_column
            )
            protected_ids = set(child_ids) | {source_id}
            protected_spouse_ids = {
                spouse_id
                for child_id in child_ids
                for spouse_id in _visible_spouse_ids(
                    child_id, relations, positions)
                if spouse_id in positions and spouse_id not in child_ids
            }
            protected_ids.update(protected_spouse_ids)
            offsets = _centered_offsets(len(child_ids))
            columns = [base_column + offset for offset in offsets]
            protected_columns = [
                positions[person_id][1]
                for pair in _visible_spouse_pairs(relations, positions)
                if all(person_id not in child_ids for person_id in pair)
                for person_id in pair
                if positions[person_id][0] == child_generation
            ]
            protected_columns.extend(
                assigned_child_columns_by_generation[child_generation])
            for _ in range(20):
                conflicts = [
                    protected_column
                    for column in columns
                    for protected_column in protected_columns
                    if abs(column - protected_column) < MIN_COLUMN_SPACING
                ]
                if not conflicts:
                    break
                conflict_column = conflicts[0]
                group_center = (
                    (min(columns) + max(columns)) / 2
                    if columns else base_column
                )
                direction = 1 if group_center >= conflict_column else -1
                columns = [
                    column + direction * MIN_COLUMN_SPACING
                    for column in columns
                ]

            assigned_child_columns = []
            for child_id, column in zip(child_ids, columns):
                column = _nearest_unblocked_column(
                    column,
                    protected_columns + assigned_child_columns,
                )
                _reserve_same_row_slot(
                    positions, occupied, child_generation, column,
                    protected_ids)
                positions[child_id] = (child_generation, column)
                assigned_child_columns.append(column)
                _rebuild_occupied(occupied, positions)
            assigned_child_columns_by_generation[child_generation].extend(
                assigned_child_columns)

    while queue:
        source_id = queue.popleft()
        source_generation, source_column = positions[source_id]
        for category in LAYOUT_TREE_CATEGORIES:
            targets = relations[source_id].get(category, ())
            if category == 'parents':
                generation = source_generation - 1
                offsets = _centered_offsets(len(targets), MIN_COLUMN_SPACING)
                base_column = source_column
            elif category == 'children':
                generation = source_generation + 1
                offsets = _centered_offsets(len(targets))
                spouse_columns = _visible_spouse_columns(
                    source_id, relations, positions)
                base_column = (
                    (source_column + spouse_columns[0]) / 2
                    if spouse_columns else source_column
                )
            elif category == 'siblings':
                generation = source_generation
                spouse_columns = _visible_spouse_columns(
                    source_id, relations, positions)
                direction = (
                    1 if any(column < source_column
                             for column in spouse_columns)
                    else -1
                )
                offsets = _side_offsets(len(targets), direction)
                base_column = source_column
            else:
                generation = source_generation
                offsets = _side_offsets(len(targets), 1, MIN_COLUMN_SPACING)
                base_column = source_column

            target_columns = {
                target_id: base_column + offset
                for target_id, offset in zip(targets, offsets)
            }
            if category == 'children':
                for target_id, column in target_columns.items():
                    if target_id not in positions:
                        continue
                    if positions[target_id][0] != generation:
                        continue
                    _reserve_same_row_slot(
                        positions, occupied, generation, column,
                        {target_id, source_id})
                    positions[target_id] = (generation, column)
                    _rebuild_occupied(occupied, positions)

            for target_id, offset in zip(targets, offsets):
                if target_id in positions:
                    continue
                column = target_columns.get(target_id, base_column + offset)
                if category == 'parents':
                    visible_spouse_ids = [
                        spouse_id for spouse_id in _visible_spouse_ids(
                            target_id, relations, positions)
                        if positions[spouse_id][0] == generation
                    ]
                    if visible_spouse_ids:
                        spouse_id = visible_spouse_ids[0]
                        spouse_generation, spouse_column = positions[spouse_id]
                        pair_offset = MIN_COLUMN_SPACING / 2
                        if spouse_column <= source_column:
                            spouse_column = source_column - pair_offset
                            column = source_column + pair_offset
                        else:
                            spouse_column = source_column + pair_offset
                            column = source_column - pair_offset
                        _reserve_same_row_slot(
                            positions, occupied, generation, spouse_column,
                            {spouse_id, source_id})
                        positions[spouse_id] = (
                            spouse_generation, spouse_column)
                        _rebuild_occupied(occupied, positions)
                    _reserve_same_row_slot(
                        positions, occupied, generation, column,
                        set(visible_spouse_ids) | {source_id})
                elif category in ('children', 'spouses'):
                    _reserve_same_row_slot(
                        positions, occupied, generation, column, source_id)
                assign(target_id, generation, column)

    for target_id in visible_ids:
        if target_id in positions:
            continue
        generation = 0
        column = _next_open_column(0.0, occupied[generation])
        positions[target_id] = (generation, column)
        occupied[generation].append(column)

    for _ in range(10):
        before = dict(positions)
        enforce_spouse_adjacency()
        enforce_child_alignment()
        if before == positions:
            break
    enforce_spouse_adjacency()
    _compact_row_gaps(positions, {center_id})
    _rebuild_occupied(occupied, positions)
    enforce_spouse_adjacency()
    _resolve_same_row_conflicts(positions, {center_id})
    _rebuild_occupied(occupied, positions)
    _compact_row_gaps(positions, {center_id})
    _resolve_same_row_conflicts(positions, {center_id})
    _rebuild_occupied(occupied, positions)
    return [
        {
            'id': target_id,
            'generation': positions[target_id][0],
            'column': positions[target_id][1],
            'is_center': target_id == center_id,
        }
        for target_id in visible_ids
    ]
