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
    if not any(source_id == center_id for source_id, _category in requests):
        requests = [
            (center_id, category) for category in INITIAL_TREE_CATEGORIES
        ] + requests

    def add_visible(target_id):
        if target_id not in visible_set:
            visible.append(target_id)
            visible_set.add(target_id)

    def add_edge(source_id, target_id, category):
        edge = (source_id, target_id, category)
        if edge not in edge_set:
            edges.append(edge)
            edge_set.add(edge)

    def reveal_source(source_id):
        if source_id in visible_set:
            return True
        for visible_id in list(visible):
            members = family_lookup(visible_id)
            for category in EXPANDABLE_TREE_CATEGORIES:
                if source_id not in members.get(category, ()):
                    continue
                add_visible(source_id)
                add_edge(visible_id, source_id, category)
                if category == 'parents' and coparent_lookup:
                    for other_parent_id in coparent_lookup(
                            source_id, (visible_id,)):
                        if not other_parent_id or other_parent_id == source_id:
                            continue
                        add_visible(other_parent_id)
                        if ((source_id, other_parent_id, 'spouses')
                                not in edge_set
                                and (other_parent_id, source_id, 'spouses')
                                not in edge_set):
                            add_edge(source_id, other_parent_id, 'spouses')
                elif category == 'children' and coparent_lookup:
                    for other_parent_id in coparent_lookup(
                            visible_id, (source_id,)):
                        if not other_parent_id or other_parent_id == visible_id:
                            continue
                        add_visible(other_parent_id)
                        if ((visible_id, other_parent_id, 'spouses')
                                not in edge_set
                                and (other_parent_id, visible_id, 'spouses')
                                not in edge_set):
                            add_edge(visible_id, other_parent_id, 'spouses')
                return True
        return False

    for source_id, category in requests:
        if not reveal_source(source_id):
            continue
        members = family_lookup(source_id).get(category, ())
        for target_id in members:
            if not target_id or target_id == source_id:
                continue
            add_visible(target_id)
            add_edge(source_id, target_id, category)
        if category == 'children' and coparent_lookup:
            for parent_id in coparent_lookup(source_id, members):
                if not parent_id or parent_id == source_id:
                    continue
                add_visible(parent_id)
                add_edge(source_id, parent_id, 'spouses')
        elif category == 'parents' and coparent_lookup:
            visible_parents = set(members)
            for parent_id in members:
                for other_parent_id in coparent_lookup(parent_id, (source_id,)):
                    if other_parent_id not in visible_parents:
                        continue
                    if ((parent_id, other_parent_id, 'spouses') not in edge_set
                            and (other_parent_id, parent_id, 'spouses')
                            not in edge_set):
                        add_edge(parent_id, other_parent_id, 'spouses')

    return visible, edges


def build_pedigree_tree_graph(center_id, individuals, families):
    """Return all recorded ancestor links for a left-to-right pedigree view."""
    visible = [center_id]
    visible_set = {center_id}
    edges = []
    edge_set = set()
    queue = deque([center_id])
    processed = set()

    def add_visible(target_id):
        if target_id not in visible_set:
            visible.append(target_id)
            visible_set.add(target_id)

    def add_edge(source_id, target_id):
        edge = (source_id, target_id, 'parents')
        if edge not in edge_set:
            edges.append(edge)
            edge_set.add(edge)

    while queue:
        source_id = queue.popleft()
        if source_id in processed:
            continue
        processed.add(source_id)
        indi = individuals.get(source_id)
        if not indi:
            continue
        for fam_id in indi.get('famc', ()):
            fam = families.get(fam_id)
            if not fam:
                continue
            for parent_id in (fam.get('husb'), fam.get('wife')):
                if (not parent_id or parent_id == source_id
                        or parent_id not in individuals):
                    continue
                add_visible(parent_id)
                add_edge(source_id, parent_id)
                if parent_id not in processed:
                    queue.append(parent_id)

    return visible, edges


def build_descendant_tree_graph(center_id, expanded, individuals, families):
    """Return expanded descendant branches plus needed co-parent context."""
    expanded = set(expanded or ())
    visible = [center_id]
    visible_set = {center_id}
    edges = []
    edge_set = set()
    queue = deque([center_id])
    queued = {center_id}

    def add_visible(target_id):
        if target_id not in visible_set:
            visible.append(target_id)
            visible_set.add(target_id)

    def add_edge(source_id, target_id, category):
        edge = (source_id, target_id, category)
        if edge not in edge_set:
            edges.append(edge)
            edge_set.add(edge)

    while queue:
        parent_id = queue.popleft()
        indi = individuals.get(parent_id)
        if not indi or parent_id not in expanded:
            continue
        for fam_id in indi.get('fams', ()):
            fam = families.get(fam_id)
            if not fam:
                continue
            children = [
                child_id for child_id in fam.get('chil', ())
                if child_id and child_id != parent_id and child_id in individuals
            ]
            if not children:
                continue
            spouse_id = (
                fam.get('wife') if fam.get('husb') == parent_id
                else fam.get('husb')
            )
            if spouse_id and spouse_id in individuals:
                add_visible(spouse_id)
                add_edge(parent_id, spouse_id, 'spouses')
            for child_id in children:
                add_visible(child_id)
                add_edge(parent_id, child_id, 'children')
                if child_id in expanded and child_id not in queued:
                    queue.append(child_id)
                    queued.add(child_id)

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


def descendant_tree_expanded_requests(visible_ids, expanded, family_lookup):
    """Return visible descendant branches that should render collapse buttons."""
    expanded = set(expanded or ())
    requests = []
    for indi_id in visible_ids:
        if indi_id not in expanded:
            continue
        if family_lookup(indi_id).get('children'):
            requests.append((indi_id, 'children'))
    return requests


def descendant_tree_expansion_options(indi_id, visible_ids, family_lookup):
    """Return hidden child branches for the descendant-only graph mode."""
    visible = set(visible_ids)
    return {
        'children': [
            target_id
            for target_id in family_lookup(indi_id).get('children', ())
            if target_id and target_id not in visible and target_id != indi_id
        ]
    }


def layout_pedigree_tree(center_id, visible_ids, edges):
    """Return pedigree nodes with ancestor depth as column coordinates."""
    parents_by_child = defaultdict(list)
    for source_id, target_id, category in edges:
        if category == 'parents':
            parents_by_child[source_id].append(target_id)

    depths = {center_id: 0}
    queue = deque([center_id])
    while queue:
        source_id = queue.popleft()
        next_depth = depths[source_id] + 1
        for parent_id in parents_by_child.get(source_id, ()):
            if parent_id in depths and depths[parent_id] <= next_depth:
                continue
            depths[parent_id] = next_depth
            queue.append(parent_id)

    visible_order = {indi_id: index for index, indi_id in enumerate(visible_ids)}
    nodes_by_depth = defaultdict(list)
    for indi_id, depth in depths.items():
        nodes_by_depth[depth].append(indi_id)

    def merge_hints(target, source, shift):
        for indi_id, source_rows in source.items():
            target[indi_id].extend(row + shift for row in source_rows)

    def layout_subtree(indi_id, depth, path=()):
        parents = [
            parent_id
            for parent_id in parents_by_child.get(indi_id, ())
            if depths.get(parent_id) == depth + 1
        ]
        if not parents or indi_id in path:
            return {indi_id: [0.0]}, 0.0, 0.0, 0.0

        hints = defaultdict(list)
        placed_rows = []
        previous_max = None
        parent_roots = []
        for parent_id in parents:
            parent_hints, parent_root, parent_min, parent_max = (
                layout_subtree(parent_id, depth + 1, path + (indi_id,)))
            subtree_min = parent_min - parent_root
            subtree_max = parent_max - parent_root
            if previous_max is None:
                parent_shift = 0.0
            else:
                parent_shift = previous_max + MIN_COLUMN_SPACING - subtree_min
            shifted_by = parent_shift - parent_root
            merge_hints(hints, parent_hints, shifted_by)
            placed_rows.extend(
                row + shifted_by
                for source_rows in parent_hints.values()
                for row in source_rows
            )
            parent_roots.append(parent_shift)
            previous_max = subtree_max + parent_shift

        root_row = sum(parent_roots) / len(parent_roots)
        hints[indi_id].append(root_row)
        placed_rows.append(root_row)
        return hints, root_row, min(placed_rows), max(placed_rows)

    row_hints, root_row, _min_row, _max_row = layout_subtree(center_id, 0)
    rows = {
        indi_id: (sum(hints) / len(hints)) - root_row
        for indi_id, hints in row_hints.items()
    }

    next_row = max(rows.values(), default=0.0) + MIN_COLUMN_SPACING
    for depth in sorted(nodes_by_depth):
        for indi_id in sorted(
                nodes_by_depth[depth],
                key=lambda row_id: visible_order.get(row_id, 0)):
            if indi_id not in rows:
                rows[indi_id] = next_row
                next_row += MIN_COLUMN_SPACING

    return [
        {
            'id': indi_id,
            'generation': rows.get(indi_id, 0.0),
            'column': depths.get(indi_id, 0),
            'is_center': indi_id == center_id,
            'expanded_from': None,
            'expanded_category': None,
        }
        for indi_id in visible_ids
        if indi_id in depths
    ]


def layout_descendant_tree(center_id, visible_ids, edges):
    """Return a fast top-down layout for descendant-only graphs."""
    visible = set(visible_ids)
    children_by_parent = defaultdict(list)
    spouse_edges = []
    for source_id, target_id, category in edges:
        if source_id not in visible or target_id not in visible:
            continue
        if category == 'children':
            children_by_parent[source_id].append(target_id)
        elif category == 'spouses':
            spouse_edges.append((source_id, target_id))

    descendant_ids = set()
    generation = {}
    queue = deque([(center_id, 0)])
    while queue:
        indi_id, depth = queue.popleft()
        if indi_id in descendant_ids:
            continue
        descendant_ids.add(indi_id)
        generation[indi_id] = depth
        for child_id in children_by_parent.get(indi_id, ()):
            if child_id in visible and child_id not in descendant_ids:
                queue.append((child_id, depth + 1))

    columns = {}
    next_column = [0.0]
    visiting = set()

    def assign_column(indi_id):
        if indi_id in columns:
            return columns[indi_id]
        if indi_id in visiting:
            columns[indi_id] = next_column[0]
            next_column[0] += 1.0
            return columns[indi_id]
        visiting.add(indi_id)
        child_columns = [
            assign_column(child_id)
            for child_id in children_by_parent.get(indi_id, ())
            if child_id in descendant_ids
        ]
        visiting.discard(indi_id)
        if child_columns:
            columns[indi_id] = (
                min(child_columns) + max(child_columns)) / 2
        else:
            columns[indi_id] = next_column[0]
            next_column[0] += 1.0
        return columns[indi_id]

    assign_column(center_id)
    for indi_id in visible_ids:
        if indi_id in descendant_ids:
            assign_column(indi_id)

    occupied = defaultdict(set)
    for indi_id in descendant_ids:
        occupied[generation[indi_id]].add(columns[indi_id])

    def reserve_context_column(row, preferred):
        candidates = [preferred]
        for distance in range(1, max(20, len(visible_ids) + 1)):
            candidates.extend((preferred + distance, preferred - distance))
        for candidate in candidates:
            if not any(
                    abs(candidate - used) < MIN_COLUMN_SPACING
                    for used in occupied[row]):
                occupied[row].add(candidate)
                return candidate
        occupied[row].add(preferred)
        return preferred

    context_positions = {}
    context_partner_by_spouse = {}
    for left_id, right_id in spouse_edges:
        if left_id in descendant_ids and right_id not in descendant_ids:
            partner_id, spouse_id = left_id, right_id
        elif right_id in descendant_ids and left_id not in descendant_ids:
            partner_id, spouse_id = right_id, left_id
        else:
            continue
        row = generation[partner_id]
        preferred = columns[partner_id] + 1.0
        context_positions[spouse_id] = (
            row, reserve_context_column(row, preferred))
        context_partner_by_spouse[spouse_id] = partner_id

    layout = []
    for indi_id in visible_ids:
        if indi_id in descendant_ids:
            row = generation[indi_id]
            column = columns[indi_id]
        elif indi_id in context_positions:
            row, column = context_positions[indi_id]
        else:
            continue
        layout.append({
            'id': indi_id,
            'generation': row,
            'column': column,
            'is_center': indi_id == center_id,
            'expanded_from': None,
            'expanded_category': None,
        })

    layout_by_id = {node['id']: node for node in layout}
    layout_index = {node['id']: index for index, node in enumerate(layout)}
    by_generation = defaultdict(list)
    for index, node in enumerate(layout):
        by_generation[node['generation']].append((node['column'], index))

    spouses_by_partner = defaultdict(list)
    for spouse_id, partner_id in context_partner_by_spouse.items():
        if spouse_id in layout_by_id and partner_id in layout_by_id:
            spouses_by_partner[partner_id].append(spouse_id)

    def descendant_subtree_ids(root_id):
        subtree_ids = set()
        stack = [root_id]
        while stack:
            node_id = stack.pop()
            if node_id in subtree_ids:
                continue
            if node_id in layout_by_id:
                subtree_ids.add(node_id)
            for spouse_id in spouses_by_partner.get(node_id, ()):
                if spouse_id in layout_by_id:
                    subtree_ids.add(spouse_id)
            for child_id in children_by_parent.get(node_id, ()):
                if child_id in descendant_ids:
                    stack.append(child_id)
        return subtree_ids

    def shift_subtree(root_id, delta):
        if abs(delta) < 0.001:
            return
        for node_id in descendant_subtree_ids(root_id):
            layout_by_id[node_id]['column'] += delta

    def enforce_row_spacing():
        for generation_id in sorted({node['generation'] for node in layout}):
            previous_column = None
            for node in sorted(
                    (node for node in layout
                     if node['generation'] == generation_id),
                    key=lambda item: item['column']):
                column = node['column']
                if previous_column is not None and (
                        column - previous_column < MIN_COLUMN_SPACING):
                    delta = previous_column + MIN_COLUMN_SPACING - column
                    if node['id'] in descendant_ids:
                        shift_subtree(node['id'], delta)
                    else:
                        node['column'] += delta
                    column += delta
                previous_column = column

    def ordered_row_with_spouses(row):
        ordered = [index for _column, index in sorted(row)]
        same_row_spouses_by_partner = defaultdict(list)
        for partner_id, spouse_ids in spouses_by_partner.items():
            partner_node = layout_by_id.get(partner_id)
            if not partner_node:
                continue
            for spouse_id in spouse_ids:
                spouse_node = layout_by_id.get(spouse_id)
                if not spouse_node:
                    continue
                if spouse_node['generation'] != partner_node['generation']:
                    continue
                same_row_spouses_by_partner[partner_id].append(spouse_id)
        if not same_row_spouses_by_partner:
            return ordered, set()

        moved_spouse_ids = set()
        for spouse_ids in same_row_spouses_by_partner.values():
            spouse_ids.sort(key=lambda spouse_id: layout_index[spouse_id])
            moved_spouse_ids.update(spouse_ids)

        reordered = []
        for index in ordered:
            node_id = layout[index]['id']
            if node_id in moved_spouse_ids:
                continue
            reordered.append(index)
            for spouse_id in same_row_spouses_by_partner.get(node_id, ()):
                reordered.append(layout_index[spouse_id])
        return reordered, moved_spouse_ids

    for row in by_generation.values():
        ordered, moved_spouse_ids = ordered_row_with_spouses(row)
        previous_column = None
        for index in ordered:
            node = layout[index]
            column = node['column']
            if node['id'] in moved_spouse_ids and previous_column is not None:
                column = previous_column + MIN_COLUMN_SPACING
            elif previous_column is not None and (
                    column - previous_column < MIN_COLUMN_SPACING):
                column = previous_column + MIN_COLUMN_SPACING
            layout[index]['column'] = column
            previous_column = column

    for parent_id in sorted(
            descendant_ids,
            key=lambda node_id: (
                layout_by_id.get(node_id, {}).get('generation', 0),
                layout_by_id.get(node_id, {}).get('column', 0),
            )):
        parent_node = layout_by_id.get(parent_id)
        if not parent_node:
            continue
        same_row_spouse_columns = [
            layout_by_id[spouse_id]['column']
            for spouse_id in spouses_by_partner.get(parent_id, ())
            if (spouse_id in layout_by_id
                and layout_by_id[spouse_id]['generation']
                == parent_node['generation'])
        ]
        if not same_row_spouse_columns:
            continue
        child_ids = [
            child_id for child_id in children_by_parent.get(parent_id, ())
            if child_id in descendant_ids and child_id in layout_by_id
        ]
        if not child_ids:
            continue
        parent_midpoint = (
            parent_node['column'] + sum(same_row_spouse_columns)
            / len(same_row_spouse_columns)
        ) / 2
        child_columns = [layout_by_id[child_id]['column']
                         for child_id in child_ids]
        child_midpoint = (min(child_columns) + max(child_columns)) / 2
        delta = parent_midpoint - child_midpoint
        for child_id in child_ids:
            shift_subtree(child_id, delta)

    enforce_row_spacing()
    return layout


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

    def shift_left_block(row, protected_index):
        next_column = row[protected_index][0]
        for index in range(protected_index - 1, -1, -1):
            column, person_id = row[index]
            if next_column - column >= MIN_COLUMN_SPACING:
                break
            if person_id in protected_ids:
                break
            column = next_column - MIN_COLUMN_SPACING
            positions[person_id] = (positions[person_id][0], column)
            row[index] = (column, person_id)
            next_column = column

    by_generation = defaultdict(list)
    for person_id, (generation, column) in positions.items():
        by_generation[generation].append((column, person_id))

    for generation, row in by_generation.items():
        row = sorted(row)
        for _ in range(max(1, len(row))):
            changed = False
            for index in range(1, len(row)):
                previous_column, previous_id = row[index - 1]
                column, person_id = row[index]
                if column - previous_column >= MIN_COLUMN_SPACING:
                    continue
                if person_id in protected_ids and previous_id not in protected_ids:
                    before = list(row)
                    shift_left_block(row, index)
                    changed = row != before
                    if changed:
                        break
                elif person_id not in protected_ids:
                    column = previous_column + MIN_COLUMN_SPACING
                    positions[person_id] = (generation, column)
                    row[index] = (column, person_id)
                    changed = True
            if not changed:
                break
            row = sorted(row)


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


class _FamilyTreeLayoutContext:
    """Mutable state for family-tree layout passes."""

    def __init__(self, center_id, relations):
        self.center_id = center_id
        self.relations = relations
        self.positions = {center_id: (0, 0.0)}
        self.occupied = defaultdict(list)
        self.occupied[0].append(0.0)
        self.queue = deque([center_id])

    def assign(self, target_id, generation, column):
        column = _next_open_column(column, self.occupied[generation])
        self.positions[target_id] = (generation, column)
        self.occupied[generation].append(column)
        self.queue.append(target_id)

    def rebuild(self):
        _rebuild_occupied(self.occupied, self.positions)

    def reserve(self, generation, column, protected_id):
        _reserve_same_row_slot(
            self.positions, self.occupied, generation, column, protected_id)

    def compact_row_gaps(self, protected_ids=()):
        _compact_row_gaps(self.positions, protected_ids)
        self.rebuild()

    def resolve_same_row_conflicts(self, protected_ids=()):
        _resolve_same_row_conflicts(self.positions, protected_ids)
        self.rebuild()

    def run_until_stable(self, passes, max_iterations):
        for _ in range(max_iterations):
            before = dict(self.positions)
            for layout_pass in passes:
                layout_pass()
            if before == self.positions:
                break


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


def _visible_sibling_ids(source_id, relations, positions):
    sibling_ids = list(relations[source_id].get('siblings', ()))
    for other_id, rels in relations.items():
        if source_id in rels.get('siblings', ()):
            sibling_ids.append(other_id)
    visible = []
    seen = set()
    source_generation = positions[source_id][0]
    for sibling_id in sibling_ids:
        if sibling_id in seen or sibling_id not in positions:
            continue
        if positions[sibling_id][0] != source_generation:
            continue
        visible.append(sibling_id)
        seen.add(sibling_id)
    return visible


def _visible_family_sibling_ids(source_id, relations, positions):
    """Return visible same-generation siblings from sibling and parent edges."""
    sibling_ids = list(_visible_sibling_ids(source_id, relations, positions))
    for parent_id, rels in relations.items():
        if source_id not in rels.get('children', ()):
            continue
        sibling_ids.extend(
            child_id for child_id in rels.get('children', ())
            if child_id != source_id)

    visible = []
    seen = set()
    source_generation = positions[source_id][0]
    for sibling_id in sibling_ids:
        if sibling_id in seen or sibling_id not in positions:
            continue
        if positions[sibling_id][0] != source_generation:
            continue
        visible.append(sibling_id)
        seen.add(sibling_id)
    return visible


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

    spouses_by_person = defaultdict(list)
    siblings_by_person = defaultdict(list)
    children_by_parent = defaultdict(list)
    parents_by_child = defaultdict(list)

    def add_indexed_relation(index, source_id, target_id):
        if target_id not in index[source_id]:
            index[source_id].append(target_id)

    for source_id, target_id, category in edges:
        if category == 'spouses':
            add_indexed_relation(spouses_by_person, source_id, target_id)
            add_indexed_relation(spouses_by_person, target_id, source_id)
        elif category == 'siblings':
            add_indexed_relation(siblings_by_person, source_id, target_id)
            add_indexed_relation(siblings_by_person, target_id, source_id)
        elif category == 'children':
            add_indexed_relation(children_by_parent, source_id, target_id)
            add_indexed_relation(parents_by_child, target_id, source_id)
        elif category == 'parents':
            add_indexed_relation(parents_by_child, source_id, target_id)
            add_indexed_relation(children_by_parent, target_id, source_id)

    ctx = _FamilyTreeLayoutContext(center_id, relations)
    positions = ctx.positions
    queue = ctx.queue

    def _visible_spouse_ids(source_id, _relations, positions):
        return [
            spouse_id for spouse_id in spouses_by_person.get(source_id, ())
            if spouse_id in positions
        ]

    def _visible_spouse_columns(source_id, relations, positions):
        return [
            positions[spouse_id][1]
            for spouse_id in _visible_spouse_ids(source_id, relations, positions)
        ]

    def _visible_sibling_ids(source_id, _relations, positions):
        visible = []
        seen = set()
        source_generation = positions[source_id][0]
        for sibling_id in siblings_by_person.get(source_id, ()):
            if sibling_id in seen or sibling_id not in positions:
                continue
            if positions[sibling_id][0] != source_generation:
                continue
            visible.append(sibling_id)
            seen.add(sibling_id)
        return visible

    def _visible_family_sibling_ids(source_id, relations, positions):
        sibling_ids = list(_visible_sibling_ids(
            source_id, relations, positions))
        for parent_id in parents_by_child.get(source_id, ()):
            sibling_ids.extend(
                child_id for child_id in children_by_parent.get(parent_id, ())
                if child_id != source_id)

        visible = []
        seen = set()
        source_generation = positions[source_id][0]
        for sibling_id in sibling_ids:
            if sibling_id in seen or sibling_id not in positions:
                continue
            if positions[sibling_id][0] != source_generation:
                continue
            visible.append(sibling_id)
            seen.add(sibling_id)
        return visible

    def _visible_spouse_pairs(_relations, positions):
        pairs = []
        seen = set()
        for source_id in positions:
            for spouse_id in _visible_spouse_ids(
                    source_id, relations, positions):
                edge_key = tuple(sorted((source_id, spouse_id)))
                if edge_key in seen:
                    continue
                seen.add(edge_key)
                pairs.append((source_id, spouse_id))
        return pairs

    def _visible_child_ids(source_id, relations, positions):
        child_ids = list(children_by_parent.get(source_id, ()))
        for spouse_id in _visible_spouse_ids(source_id, relations, positions):
            child_ids.extend(children_by_parent.get(spouse_id, ()))

        visible = []
        seen = set()
        for child_id in child_ids:
            if child_id in positions and child_id not in seen:
                visible.append(child_id)
                seen.add(child_id)
        return visible

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
                ctx.reserve(
                    source_generation, desired_column, {source_id, spouse_id})
                positions[spouse_id] = (spouse_generation, desired_column)
                ctx.rebuild()

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
                ctx.reserve(child_generation, column, protected_ids)
                positions[child_id] = (child_generation, column)
                assigned_child_columns.append(column)
                ctx.rebuild()
            assigned_child_columns_by_generation[child_generation].extend(
                assigned_child_columns)

    def enforce_sibling_adjacency():
        seen_groups = set()
        for source_id in sorted(
                list(positions),
                key=lambda item: (positions[item][0], positions[item][1])):
            sibling_ids = _visible_sibling_ids(source_id, relations, positions)
            if not sibling_ids:
                continue
            if source_id != center_id and center_id in sibling_ids:
                continue
            source_generation, source_column = positions[source_id]
            spouse_columns = _visible_spouse_columns(
                source_id, relations, positions)
            if not spouse_columns:
                continue
            group_key = frozenset([source_id, *sibling_ids])
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            direction = (
                -1 if any(column > source_column
                          for column in spouse_columns)
                else 1
            )
            ordered_siblings = sorted(
                sibling_ids,
                key=lambda sibling_id: (
                    abs(positions[sibling_id][1] - source_column),
                    positions[sibling_id][1],
                    sibling_id,
                ))
            desired = {
                sibling_id: source_column + offset
                for sibling_id, offset in zip(
                    ordered_siblings,
                    _side_offsets(len(ordered_siblings), direction),
                )
            }
            if all(abs(positions[sibling_id][1] - column) < 0.001
                   for sibling_id, column in desired.items()):
                continue
            protected_ids = set(group_key)
            for sibling_id in sibling_ids:
                protected_ids.update(
                    _visible_spouse_ids(sibling_id, relations, positions))
            protected_ids.update(
                _visible_spouse_ids(source_id, relations, positions))
            desired_columns = list(desired.values())
            if desired_columns:
                if direction < 0:
                    band_min = min(desired_columns)
                    band_max = source_column
                    conflicts = sorted(
                        (
                            person_id for person_id, (generation, column)
                            in positions.items()
                            if person_id not in protected_ids
                            and generation == source_generation
                            and band_min <= column < band_max
                        ),
                        key=lambda person_id: positions[person_id][1],
                    )
                    next_column = band_min - MIN_COLUMN_SPACING
                    for person_id in conflicts:
                        positions[person_id] = (
                            source_generation, next_column)
                        next_column -= MIN_COLUMN_SPACING
                else:
                    band_min = source_column
                    band_max = max(desired_columns)
                    conflicts = sorted(
                        (
                            person_id for person_id, (generation, column)
                            in positions.items()
                            if person_id not in protected_ids
                            and generation == source_generation
                            and band_min < column <= band_max
                        ),
                        key=lambda person_id: positions[person_id][1],
                    )
                    next_column = band_max + MIN_COLUMN_SPACING
                    for person_id in conflicts:
                        positions[person_id] = (
                            source_generation, next_column)
                        next_column += MIN_COLUMN_SPACING
                ctx.rebuild()
            move_plan = sorted(
                desired.items(),
                key=lambda item: item[1],
                reverse=direction < 0,
            )
            for sibling_id, column in move_plan:
                ctx.reserve(source_generation, column, protected_ids)
                positions[sibling_id] = (source_generation, column)
                ctx.rebuild()

    def enforce_parent_child_alignment():
        aligned_pairs = set()
        for source_id in sorted(
                list(positions),
                key=lambda item: (positions[item][0], positions[item][1])):
            if source_id == center_id:
                continue
            if center_id in _visible_sibling_ids(source_id, relations, positions):
                continue
            if any(
                    center_id in _visible_sibling_ids(
                        spouse_id, relations, positions)
                    or spouse_id == center_id
                    for spouse_id in _visible_spouse_ids(
                        source_id, relations, positions)):
                continue
            source_generation, source_column = positions[source_id]
            child_generation = source_generation + 1
            child_ids = [
                child_id for child_id in _visible_child_ids(
                    source_id, relations, positions)
                if positions[child_id][0] == child_generation
            ]
            if not child_ids:
                continue
            spouse_ids = [
                spouse_id for spouse_id in _visible_spouse_ids(
                    source_id, relations, positions)
                if positions[spouse_id][0] == source_generation
            ]
            if not spouse_ids:
                continue
            spouse_id = spouse_ids[0]
            pair_key = tuple(sorted((source_id, spouse_id)))
            if pair_key in aligned_pairs:
                continue
            aligned_pairs.add(pair_key)
            spouse_column = positions[spouse_id][1]
            current_center = (source_column + spouse_column) / 2
            child_center = (
                min(positions[child_id][1] for child_id in child_ids)
                + max(positions[child_id][1] for child_id in child_ids)
            ) / 2
            if child_center - current_center <= MIN_COLUMN_SPACING:
                continue
            pair_offset = MIN_COLUMN_SPACING / 2
            if source_column <= spouse_column:
                source_target = child_center - pair_offset
                spouse_target = child_center + pair_offset
            else:
                source_target = child_center + pair_offset
                spouse_target = child_center - pair_offset
            protected_ids = {source_id, spouse_id}
            ctx.reserve(source_generation, source_target, protected_ids)
            ctx.reserve(source_generation, spouse_target, protected_ids)
            positions[source_id] = (source_generation, source_target)
            positions[spouse_id] = (source_generation, spouse_target)
            ctx.resolve_same_row_conflicts(protected_ids)

    def compact_child_row_clusters():
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
            if len(child_ids) < 2:
                continue
            spouse_columns = _visible_spouse_columns(
                source_id, relations, positions)
            base_column = (
                (source_column + spouse_columns[0]) / 2
                if spouse_columns else source_column
            )
            group_ids = set(child_ids)
            for child_id in child_ids:
                group_ids.update(
                    spouse_id for spouse_id in _visible_spouse_ids(
                        child_id, relations, positions)
                    if positions[spouse_id][0] == child_generation)
            ordered_group = sorted(
                group_ids,
                key=lambda person_id: (positions[person_id][1], person_id))
            current_center = (
                min(positions[person_id][1] for person_id in ordered_group)
                + max(positions[person_id][1] for person_id in ordered_group)
            ) / 2
            if current_center - base_column <= MIN_COLUMN_SPACING:
                continue
            start_column = base_column - (
                (len(ordered_group) - 1) * MIN_COLUMN_SPACING) / 2
            desired = {
                person_id: start_column + index * MIN_COLUMN_SPACING
                for index, person_id in enumerate(ordered_group)
            }
            non_group_columns = [
                column for person_id, (generation, column)
                in positions.items()
                if generation == child_generation and person_id not in group_ids
            ]
            if any(
                    abs(column - blocked) < MIN_COLUMN_SPACING
                    for column in desired.values()
                    for blocked in non_group_columns):
                continue
            for person_id, column in desired.items():
                positions[person_id] = (child_generation, column)
            ctx.rebuild()

    def compact_sibling_side_gaps():
        seen_groups = set()
        max_gap = 1.5
        for source_id in sorted(
                list(positions),
                key=lambda item: (positions[item][0], positions[item][1])):
            sibling_ids = _visible_sibling_ids(source_id, relations, positions)
            if not sibling_ids:
                continue
            source_generation, source_column = positions[source_id]
            spouse_columns = _visible_spouse_columns(
                source_id, relations, positions)
            if not spouse_columns:
                continue
            group_key = frozenset([source_id, *sibling_ids])
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            direction = (
                -1 if any(column > source_column
                          for column in spouse_columns)
                else 1
            )
            side_ids = set()
            fixed_ids = {source_id, *_visible_spouse_ids(
                source_id, relations, positions)}
            for sibling_id in sibling_ids:
                sibling_column = positions[sibling_id][1]
                if (direction < 0 and sibling_column >= source_column
                        or direction > 0 and sibling_column <= source_column):
                    continue
                side_ids.add(sibling_id)
                visible_children = [
                    child_id for child_id in _visible_child_ids(
                        sibling_id, relations, positions)
                    if positions[child_id][0] == source_generation + 1
                ]
                if visible_children:
                    fixed_ids.add(sibling_id)
                for spouse_id in _visible_spouse_ids(
                        sibling_id, relations, positions):
                    if positions[spouse_id][0] != source_generation:
                        continue
                    side_ids.add(spouse_id)
                    if visible_children:
                        fixed_ids.add(spouse_id)
            if len(side_ids) < 2:
                continue
            for _ in range(len(side_ids)):
                row = sorted(
                    (positions[person_id][1], person_id)
                    for person_id in side_ids)
                changed = False
                for index in range(1, len(row)):
                    left_column, left_id = row[index - 1]
                    right_column, right_id = row[index]
                    if right_column - left_column <= max_gap:
                        continue
                    if left_id not in fixed_ids:
                        positions[left_id] = (
                            source_generation, right_column - max_gap)
                        changed = True
                    elif right_id not in fixed_ids:
                        positions[right_id] = (
                            source_generation, left_column + max_gap)
                        changed = True
                    if changed:
                        ctx.rebuild()
                        break
                if not changed:
                    break

    def enforce_spouse_sibling_side_groups():
        handled_pairs = set()
        for source_id, spouse_id in _visible_spouse_pairs(relations, positions):
            pair_key = tuple(sorted((source_id, spouse_id)))
            if pair_key in handled_pairs:
                continue
            handled_pairs.add(pair_key)
            source_generation, source_column = positions[source_id]
            spouse_generation, spouse_column = positions[spouse_id]
            if source_generation != spouse_generation:
                continue
            if source_column <= spouse_column:
                left_id, right_id = source_id, spouse_id
                left_column, right_column = source_column, spouse_column
            else:
                left_id, right_id = spouse_id, source_id
                left_column, right_column = spouse_column, source_column
            left_siblings = [
                sibling_id for sibling_id in _visible_family_sibling_ids(
                    left_id, relations, positions)
                if sibling_id != right_id
            ]
            right_siblings = [
                sibling_id for sibling_id in _visible_family_sibling_ids(
                    right_id, relations, positions)
                if sibling_id != left_id
            ]
            if not left_siblings or not right_siblings:
                continue
            left_siblings = sorted(
                left_siblings,
                key=lambda sibling_id: (
                    abs(positions[sibling_id][1] - left_column),
                    positions[sibling_id][1],
                    sibling_id,
                ))
            right_siblings = sorted(
                right_siblings,
                key=lambda sibling_id: (
                    abs(positions[sibling_id][1] - right_column),
                    positions[sibling_id][1],
                    sibling_id,
                ))
            protected_ids = {left_id, right_id, *left_siblings, *right_siblings}
            desired = {}
            for sibling_id, offset in zip(
                    left_siblings, _side_offsets(len(left_siblings), -1)):
                desired[sibling_id] = left_column + offset
            for sibling_id, offset in zip(
                    right_siblings, _side_offsets(len(right_siblings), 1)):
                desired[sibling_id] = right_column + offset

            for sibling_id, column in sorted(
                    desired.items(), key=lambda item: item[1]):
                ctx.reserve(source_generation, column, protected_ids)
                positions[sibling_id] = (source_generation, column)
                ctx.rebuild()

    def sibling_branch_block(root_id, source_generation):
        block_ids = set()
        stack = [root_id]
        while stack:
            person_id = stack.pop()
            if person_id in block_ids or person_id not in positions:
                continue
            generation = positions[person_id][0]
            if generation < source_generation:
                continue
            block_ids.add(person_id)
            for spouse_id in _visible_spouse_ids(person_id, relations, positions):
                if positions[spouse_id][0] == generation:
                    block_ids.add(spouse_id)
            for child_id in _visible_child_ids(person_id, relations, positions):
                if positions[child_id][0] == generation + 1:
                    stack.append(child_id)
        return block_ids

    def shift_block(block_ids, delta):
        if abs(delta) < 0.001:
            return
        for person_id in block_ids:
            if person_id not in positions:
                continue
            generation, column = positions[person_id]
            positions[person_id] = (generation, column + delta)
        ctx.rebuild()

    def same_row_unit(person_id, generation):
        if person_id not in positions or positions[person_id][0] != generation:
            return ()
        unit_ids = {person_id}
        unit_ids.update(
            spouse_id
            for spouse_id in _visible_spouse_ids(
                person_id, relations, positions)
            if positions[spouse_id][0] == generation
        )
        return tuple(sorted(unit_ids))

    def compact_interleaved_child_family_groups():
        groups_by_generation = defaultdict(dict)
        for source_id in positions:
            source_generation, source_column = positions[source_id]
            child_generation = source_generation + 1
            child_ids = [
                child_id for child_id in _visible_child_ids(
                    source_id, relations, positions)
                if positions[child_id][0] == child_generation
            ]
            if len(child_ids) < 2:
                continue
            unit_keys = []
            seen_unit_keys = set()
            for child_id in child_ids:
                unit_key = same_row_unit(child_id, child_generation)
                if not unit_key or unit_key in seen_unit_keys:
                    continue
                unit_keys.append(unit_key)
                seen_unit_keys.add(unit_key)
            if len(unit_keys) < 2:
                continue
            spouse_columns = _visible_spouse_columns(
                source_id, relations, positions)
            anchor_column = (
                (source_column + spouse_columns[0]) / 2
                if spouse_columns else source_column
            )
            group_key = frozenset(child_ids)
            group = groups_by_generation[child_generation].setdefault(
                group_key,
                {
                    'anchor_columns': [],
                    'unit_keys': unit_keys,
                },
            )
            group['anchor_columns'].append(anchor_column)

        for generation, groups in groups_by_generation.items():
            row_units = []
            claimed_ids = set()
            row_ids = [
                person_id for person_id, (
                    person_generation, _person_column)
                in positions.items()
                if person_generation == generation
            ]
            for person_id in sorted(
                    row_ids, key=lambda item: (positions[item][1], item)):
                if person_id in claimed_ids:
                    continue
                unit_key = same_row_unit(person_id, generation)
                if not unit_key:
                    continue
                claimed_ids.update(unit_key)
                row_units.append(unit_key)

            unit_to_group_key = {}
            group_order = {}
            row_unit_set = set(row_units)
            for group_key, group in groups.items():
                group_units = [
                    unit_key for unit_key in group['unit_keys']
                    if unit_key in row_unit_set
                ]
                if len(group_units) < 2:
                    continue
                group['unit_keys'] = sorted(
                    group_units,
                    key=lambda unit_key: min(
                        positions[person_id][1] for person_id in unit_key),
                )
                group_order[group_key] = (
                    sum(group['anchor_columns'])
                    / len(group['anchor_columns'])
                )
                for unit_key in group['unit_keys']:
                    existing_group_key = unit_to_group_key.get(unit_key)
                    if existing_group_key is None:
                        unit_to_group_key[unit_key] = group_key
                        continue
                    existing_anchor = group_order.get(
                        existing_group_key, 0.0)
                    if abs(group_order[group_key] - min(
                            positions[person_id][1]
                            for person_id in unit_key)) < abs(
                                existing_anchor - min(
                                    positions[person_id][1]
                                    for person_id in unit_key)):
                        unit_to_group_key[unit_key] = group_key

            row_index_by_unit = {
                unit_key: index for index, unit_key in enumerate(row_units)
            }
            ordered_group_keys = sorted(
                (
                    group_key for group_key, group in groups.items()
                    if len(group.get('unit_keys', ())) >= 2
                ),
                key=lambda group_key: (
                    group_order.get(group_key, 0.0),
                    min(row_index_by_unit.get(unit_key, len(row_units))
                        for unit_key in groups[group_key]['unit_keys']),
                ),
            )

            for group_key in ordered_group_keys:
                group_units = [
                    unit_key for unit_key in groups[group_key]['unit_keys']
                    if unit_key in row_index_by_unit
                ]
                unit_indices = [
                    row_index_by_unit[unit_key] for unit_key in group_units
                ]
                if not unit_indices:
                    continue
                first_index = min(unit_indices)
                last_index = max(unit_indices)
                if last_index - first_index + 1 == len(group_units):
                    continue
                current_interval = row_units[first_index:last_index + 1]
                group_unit_set = set(group_units)
                interval_units = [
                    *group_units,
                    *(unit_key for unit_key in current_interval
                      if unit_key not in group_unit_set),
                ]
                interval_columns = [
                    positions[person_id][1]
                    for unit_key in interval_units
                    for person_id in unit_key
                ]
                interval_span = max(interval_columns) - min(interval_columns)
                if interval_span > MIN_COLUMN_SPACING * 16:
                    continue

                unit_block_ids = {}
                unit_mins = {}
                unit_block_offsets = {}
                for unit_key in interval_units:
                    unit_min = min(
                        positions[person_id][1] for person_id in unit_key)
                    block_ids = set()
                    for person_id in unit_key:
                        block_ids.update(
                            sibling_branch_block(person_id, generation))
                    unit_block_ids[unit_key] = block_ids
                    unit_mins[unit_key] = unit_min
                    block_offsets = [
                        positions[person_id][1] - unit_min
                        for person_id in block_ids
                    ]
                    unit_block_offsets[unit_key] = (
                        min(block_offsets), max(block_offsets))

                def build_interval_plan(start_column):
                    cursor = start_column
                    planned = []
                    previous_block_right = None
                    for unit_key in interval_units:
                        block_left, block_right = (
                            unit_block_offsets[unit_key])
                        if (previous_block_right is not None
                                and cursor + block_left
                                < previous_block_right + MIN_COLUMN_SPACING):
                            cursor = (
                                previous_block_right
                                + MIN_COLUMN_SPACING
                                - block_left
                            )
                        planned.append((
                            unit_key,
                            cursor - unit_mins[unit_key],
                            unit_block_ids[unit_key],
                        ))
                        previous_block_right = cursor + block_right
                    return planned

                def planned_positions_for(plan):
                    moving_deltas = {}
                    for _unit_key, delta, block_ids in plan:
                        if abs(delta) < 0.001:
                            continue
                        for person_id in block_ids:
                            existing_delta = moving_deltas.get(person_id)
                            if (existing_delta is not None
                                    and abs(existing_delta - delta) >= 0.001):
                                return None, None
                            moving_deltas[person_id] = delta
                    if not moving_deltas:
                        return None, None

                    planned_positions = {
                        person_id: (
                            person_generation, person_column + delta)
                        for person_id, delta in moving_deltas.items()
                        for person_generation, person_column in (
                            positions[person_id],)
                    }
                    planned_by_generation = defaultdict(list)
                    for person_id, (person_generation, person_column) in (
                            planned_positions.items()):
                        planned_by_generation[person_generation].append(
                            (person_id, person_column))

                    for planned_nodes in planned_by_generation.values():
                        for index, (left_id, left_column) in enumerate(
                                planned_nodes):
                            for right_id, right_column in planned_nodes[
                                    index + 1:]:
                                if left_id == right_id:
                                    continue
                                if abs(left_column - right_column) < (
                                        MIN_COLUMN_SPACING - 1e-9):
                                    return None, None

                    for person_id, (person_generation, person_column) in (
                            planned_positions.items()):
                        for blocker_id, (
                                blocker_generation, blocker_column
                        ) in positions.items():
                            if blocker_id in moving_deltas:
                                continue
                            if blocker_generation != person_generation:
                                continue
                            if abs(person_column - blocker_column) < (
                                    MIN_COLUMN_SPACING - 1e-9):
                                return None, None

                    shift_cost = sum(
                        abs(delta) * len(block_ids)
                        for _unit_key, delta, block_ids in plan
                    )
                    return planned_positions, shift_cost

                candidate_starts = {min(interval_columns)}
                for unit_key, delta, _block_ids in build_interval_plan(0.0):
                    candidate_starts.add(unit_mins[unit_key] - (
                        unit_mins[unit_key] + delta))

                selected_positions = None
                selected_cost = None
                for start_column in sorted(candidate_starts):
                    candidate_positions, shift_cost = planned_positions_for(
                        build_interval_plan(start_column))
                    if candidate_positions is None:
                        continue
                    if selected_cost is None or shift_cost < selected_cost:
                        selected_positions = candidate_positions
                        selected_cost = shift_cost
                if selected_positions is None:
                    continue

                for person_id, target_position in selected_positions.items():
                    positions[person_id] = target_position
                ctx.rebuild()
                return True
        return False

    def sibling_cluster_branch_block(root_id, source_generation):
        root_ids = set()
        queue = deque([root_id])
        while queue:
            person_id = queue.popleft()
            if person_id in root_ids or person_id not in positions:
                continue
            if positions[person_id][0] != source_generation:
                continue
            root_ids.add(person_id)
            queue.extend(_visible_family_sibling_ids(
                person_id, relations, positions))
        block_ids = set()
        for sibling_id in root_ids:
            if sibling_id not in positions:
                continue
            if positions[sibling_id][0] != source_generation:
                continue
            block_ids.update(sibling_branch_block(
                sibling_id, source_generation))
        return block_ids

    def reserve_family_branch_slot(generation, column, protected_ids,
                                   direction):
        protected_ids = set(protected_ids)
        for _ in range(max(1, len(positions) * 3)):
            conflicts = [
                target_id for target_id, (target_generation, target_column)
                in positions.items()
                if target_id not in protected_ids
                and target_generation == generation
                and abs(target_column - column) < MIN_COLUMN_SPACING
            ]
            if not conflicts:
                return
            if direction >= 0:
                boundary = min(positions[target_id][1]
                               for target_id in conflicts)
                same_row_ids = [
                    target_id for target_id, (
                        target_generation, target_column)
                    in positions.items()
                    if target_id not in protected_ids
                    and target_generation == generation
                    and target_column >= boundary
                ]
                delta = MIN_COLUMN_SPACING
            else:
                boundary = max(positions[target_id][1]
                               for target_id in conflicts)
                same_row_ids = [
                    target_id for target_id, (
                        target_generation, target_column)
                    in positions.items()
                    if target_id not in protected_ids
                    and target_generation == generation
                    and target_column <= boundary
                ]
                delta = -MIN_COLUMN_SPACING
            shifted_ids = set()
            for target_id in same_row_ids:
                shifted_ids.update(sibling_cluster_branch_block(
                    target_id, generation))
            shifted_ids -= protected_ids
            if not shifted_ids:
                return
            shift_block(shifted_ids, delta)

    def align_detached_child_branches():
        aligned_child_groups = set()
        for source_id in sorted(
                list(positions),
                key=lambda item: (positions[item][0], positions[item][1])):
            source_generation, source_column = positions[source_id]
            if source_generation >= positions[center_id][0]:
                continue
            child_generation = source_generation + 1
            child_ids = [
                child_id for child_id in _visible_child_ids(
                    source_id, relations, positions)
                if positions[child_id][0] == child_generation
            ]
            if not child_ids:
                continue
            if len(child_ids) != 2:
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
            child_columns = [positions[child_id][1] for child_id in child_ids]
            child_center = (min(child_columns) + max(child_columns)) / 2
            delta_to_parent = base_column - child_center
            if abs(delta_to_parent) <= MIN_COLUMN_SPACING * 5:
                continue
            child_blocks = {
                child_id: sibling_branch_block(child_id, child_generation)
                for child_id in child_ids
            }
            protected_ids = {source_id, *child_ids}
            protected_ids.update(
                spouse_id
                for spouse_id in _visible_spouse_ids(
                    source_id, relations, positions)
                if positions[spouse_id][0] == source_generation)
            for block_ids in child_blocks.values():
                protected_ids.update(block_ids)
            direction = 1 if delta_to_parent < 0 else -1
            desired_columns = {
                child_id: base_column + offset
                for child_id, offset in zip(
                    child_ids, _centered_offsets(len(child_ids)))
            }
            for child_id, column in sorted(
                    desired_columns.items(), key=lambda item: item[1]):
                reserve_family_branch_slot(
                    child_generation, column, protected_ids, direction)
                child_delta = column - positions[child_id][1]
                shift_block(child_blocks[child_id], child_delta)

    def realign_child_branch_groups():
        aligned_child_groups = set()
        for source_id in (center_id,):
            if source_id not in positions:
                continue
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
            child_columns = [positions[child_id][1] for child_id in child_ids]
            child_center = (min(child_columns) + max(child_columns)) / 2
            if abs(base_column - child_center) <= MIN_COLUMN_SPACING * 1.1:
                continue
            child_blocks = {
                child_id: sibling_branch_block(child_id, child_generation)
                for child_id in child_ids
            }
            protected_ids = {source_id, *child_ids}
            protected_ids.update(
                spouse_id
                for spouse_id in _visible_spouse_ids(
                    source_id, relations, positions)
                if positions[spouse_id][0] == source_generation)
            for block_ids in child_blocks.values():
                protected_ids.update(block_ids)
            desired_columns = {
                child_id: base_column + offset
                for child_id, offset in zip(
                    child_ids, _centered_offsets(len(child_ids)))
            }
            for child_id, column in sorted(
                    desired_columns.items(), key=lambda item: item[1]):
                child_delta = column - positions[child_id][1]
                if abs(child_delta) < 0.001:
                    continue
                direction = 1 if child_delta > 0 else -1
                reserve_family_branch_slot(
                    child_generation, column, protected_ids, direction)
                shift_block(child_blocks[child_id], child_delta)

    def compact_sibling_branch_blocks():
        handled_groups = set()
        for source_id in sorted(
                list(positions),
                key=lambda item: (positions[item][0], positions[item][1])):
            source_generation, source_column = positions[source_id]
            spouse_columns = _visible_spouse_columns(
                source_id, relations, positions)
            if not spouse_columns:
                continue
            direction = (
                -1 if any(column > source_column
                          for column in spouse_columns)
                else 1
            )
            sibling_ids = [
                sibling_id for sibling_id in _visible_family_sibling_ids(
                    source_id, relations, positions)
                if (direction < 0 and positions[sibling_id][1] < source_column
                    or direction > 0
                    and positions[sibling_id][1] > source_column)
            ]
            if not sibling_ids:
                continue
            group_key = (source_generation, frozenset([source_id, *sibling_ids]))
            if group_key in handled_groups:
                continue
            handled_groups.add(group_key)
            units = []
            claimed_ids = set()
            for sibling_id in sibling_ids:
                if sibling_id in claimed_ids:
                    continue
                block_ids = sibling_branch_block(
                    sibling_id, source_generation)
                block_ids -= claimed_ids
                if not block_ids:
                    continue
                claimed_ids.update(block_ids)
                units.append(block_ids)
            if len(units) < 2 and not any(
                    len(unit) > 1 for unit in units):
                continue
            if direction < 0:
                ordered_units = sorted(
                    units,
                    key=lambda unit: max(
                        positions[person_id][1] for person_id in unit),
                    reverse=True,
                )
            else:
                ordered_units = sorted(
                    units,
                    key=lambda unit: min(
                        positions[person_id][1] for person_id in unit),
                )
            settled_ids = set()
            all_unit_ids = set().union(*units)
            for unit in ordered_units:
                if direction < 0:
                    max_shift = None
                    for person_id in unit:
                        generation, column = positions[person_id]
                        blockers = [
                            blocker_column
                            for blocker_id, (
                                    blocker_generation, blocker_column)
                            in positions.items()
                            if blocker_id not in unit
                            and (
                                blocker_id not in all_unit_ids
                                or blocker_id in settled_ids
                            )
                            and blocker_generation == generation
                            and blocker_column > column
                        ]
                        if blockers:
                            available = (
                                min(blockers) - MIN_COLUMN_SPACING - column)
                            max_shift = (
                                available if max_shift is None
                                else min(max_shift, available)
                            )
                    shift = max(0.0, max_shift or 0.0)
                else:
                    min_shift = None
                    for person_id in unit:
                        generation, column = positions[person_id]
                        blockers = [
                            blocker_column
                            for blocker_id, (
                                    blocker_generation, blocker_column)
                            in positions.items()
                            if blocker_id not in unit
                            and (
                                blocker_id not in all_unit_ids
                                or blocker_id in settled_ids
                            )
                            and blocker_generation == generation
                            and blocker_column < column
                        ]
                        if blockers:
                            available = (
                                max(blockers) + MIN_COLUMN_SPACING - column)
                            min_shift = (
                                available if min_shift is None
                                else max(min_shift, available)
                            )
                    shift = min(0.0, min_shift or 0.0)
                if abs(shift) >= 0.001:
                    for person_id in unit:
                        generation, column = positions[person_id]
                        positions[person_id] = (generation, column + shift)
                    ctx.rebuild()
                settled_ids.update(unit)

    def place_initial_nodes():
        while queue:
            source_id = queue.popleft()
            source_generation, source_column = positions[source_id]
            for category in LAYOUT_TREE_CATEGORIES:
                targets = relations[source_id].get(category, ())
                if category == 'parents':
                    generation = source_generation - 1
                    offsets = _centered_offsets(
                        len(targets), MIN_COLUMN_SPACING)
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
                    offsets = _side_offsets(
                        len(targets), 1, MIN_COLUMN_SPACING)
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
                        ctx.reserve(
                            generation, column, {target_id, source_id})
                        positions[target_id] = (generation, column)
                        ctx.rebuild()

                for target_id, offset in zip(targets, offsets):
                    if target_id in positions:
                        continue
                    column = target_columns.get(
                        target_id, base_column + offset)
                    if category == 'parents':
                        visible_spouse_ids = [
                            spouse_id for spouse_id in _visible_spouse_ids(
                                target_id, relations, positions)
                            if positions[spouse_id][0] == generation
                        ]
                        if visible_spouse_ids:
                            spouse_id = visible_spouse_ids[0]
                            spouse_generation, spouse_column = (
                                positions[spouse_id])
                            pair_offset = MIN_COLUMN_SPACING / 2
                            if spouse_column <= source_column:
                                spouse_column = source_column - pair_offset
                                column = source_column + pair_offset
                            else:
                                spouse_column = source_column + pair_offset
                                column = source_column - pair_offset
                            ctx.reserve(
                                generation, spouse_column,
                                {spouse_id, source_id})
                            positions[spouse_id] = (
                                spouse_generation, spouse_column)
                            ctx.rebuild()
                        ctx.reserve(
                            generation, column,
                            set(visible_spouse_ids) | {source_id})
                    elif category in ('children', 'spouses'):
                        ctx.reserve(generation, column, source_id)
                    ctx.assign(target_id, generation, column)

        for target_id in visible_ids:
            if target_id in positions:
                continue
            ctx.assign(target_id, 0, 0.0)

    def settle_core_constraints():
        ctx.run_until_stable(
            (enforce_spouse_adjacency, enforce_child_alignment),
            max_iterations=10,
        )

    def resolve_initial_row_conflicts():
        enforce_spouse_adjacency()
        ctx.compact_row_gaps({center_id})
        enforce_spouse_adjacency()
        ctx.resolve_same_row_conflicts({center_id})

    def settle_sibling_positions():
        enforce_sibling_adjacency()
        ctx.rebuild()
        enforce_spouse_adjacency()
        ctx.resolve_same_row_conflicts({center_id})
        ctx.compact_row_gaps({center_id})
        ctx.resolve_same_row_conflicts({center_id})
        enforce_sibling_adjacency()
        ctx.resolve_same_row_conflicts({center_id})

    def align_family_groups():
        enforce_child_alignment()
        enforce_spouse_adjacency()
        enforce_sibling_adjacency()
        enforce_spouse_adjacency()
        enforce_parent_child_alignment()
        enforce_spouse_adjacency()
        compact_sibling_side_gaps()
        compact_child_row_clusters()
        enforce_child_alignment()
        enforce_spouse_adjacency()
        enforce_spouse_sibling_side_groups()
        align_detached_child_branches()
        enforce_spouse_adjacency()

    def compact_family_branches():
        compact_sibling_branch_blocks()
        enforce_spouse_adjacency()
        enforce_child_alignment()
        compact_interleaved_child_family_groups()
        align_detached_child_branches()
        enforce_spouse_adjacency()
        ctx.run_until_stable(
            (
                compact_sibling_branch_blocks,
                enforce_spouse_adjacency,
                compact_sibling_side_gaps,
                compact_interleaved_child_family_groups,
                align_detached_child_branches,
            ),
            max_iterations=3,
        )
        realign_child_branch_groups()
        enforce_parent_child_alignment()
        compact_interleaved_child_family_groups()
        enforce_spouse_adjacency()

    place_initial_nodes()
    settle_core_constraints()
    resolve_initial_row_conflicts()
    settle_sibling_positions()
    align_family_groups()
    compact_family_branches()
    ctx.resolve_same_row_conflicts({center_id})
    for _ in range(min(20, len(positions))):
        if not compact_interleaved_child_family_groups():
            break
        enforce_spouse_adjacency()
    return [
        {
            'id': target_id,
            'generation': positions[target_id][0],
            'column': positions[target_id][1],
            'is_center': target_id == center_id,
        }
        for target_id in visible_ids
    ]
