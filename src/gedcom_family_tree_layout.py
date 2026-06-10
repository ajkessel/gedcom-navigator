#!/usr/bin/env python3
"""
gedcom_family_tree_layout.py

Family-tree layout built on explicit family units.

The layout works in three stages:
  1. ``build_family_units`` groups visible people into FAM-like units.
  2. A BFS spanning tree is built over the bipartite person/unit graph,
     assigning generations and cutting cycles (pedigree collapse).
  3. A recursive block layout assigns columns.  The unit of recursion is a
     *spouse chain*: a row of people connected by marriages, placed at fixed
     MIN_COLUMN_SPACING steps so spouses are always adjacent.  Siblings,
     children groups, and ancestor chains attach around the row; attachments
     aim for centered positions and slide sideways only as far as
     per-generation contour merging requires, so overlaps are impossible by
     construction (off-center parent or child groups render as elbow
     connectors).
"""

from collections import deque

from gedcom_family_units import build_family_units

MIN_COLUMN_SPACING = 1.0
_EPSILON = 1e-9


class FamilyTreeLayout(list):
    """Layout node list that also carries per-unit child bus descriptors."""

    def __init__(self, nodes, child_buses=()):
        super().__init__(nodes)
        self.child_buses = list(child_buses)


def layout_family_tree_units(center_id, visible_ids, edges,
                             family_members=None, parent_kind=None):
    """Return family-tree nodes with generation and column coordinates."""
    if not visible_ids:
        return FamilyTreeLayout([])
    if center_id not in visible_ids:
        center_id = visible_ids[0]

    units, person_units = build_family_units(
        visible_ids, edges, family_members, parent_kind)

    columns = {}
    generations = {}
    next_free_column = [0.0]

    roots = [center_id] + [vid for vid in visible_ids if vid != center_id]
    for root_id in roots:
        if root_id in columns:
            continue
        tree, gens = _build_spanning_tree(root_id, units, person_units)
        block = _layout_chain([root_id], tree, gens, units)
        _commit_block(block, gens, columns, generations,
                      next_free_column, bool(columns))

    buses = []
    for unit in units:
        children = [cid for cid in unit['children'] if cid in columns]
        if not children:
            continue
        partners = [pid for pid in unit['partners'] if pid in columns]
        children.sort(key=lambda cid: columns[cid])
        buses.append({
            'parent_ids': tuple(partners),
            'all_parents': unit['all_parents'],
            'children': children,
        })

    nodes = [
        {
            'id': person_id,
            'generation': generations[person_id],
            'column': columns[person_id],
            'is_center': person_id == center_id,
        }
        for person_id in visible_ids
    ]
    return FamilyTreeLayout(nodes, buses)


def _build_spanning_tree(root_id, units, person_units):
    """BFS the person/unit graph; return tree structure and generations.

    person_children[p] = [(unit_index, 'down'|'up'), ...] units traversed
    from p; unit_children[index] = {'via', 'direction', 'partners',
    'children'} listing only people first reached through that unit.
    """
    person_children = {}
    unit_children = {}
    generations = {root_id: 0}
    visited_people = {root_id}
    visited_units = set()
    discovered_as = {root_id: (None, 'root')}
    tree_parent = {root_id: None}
    queue = deque([root_id])

    def is_tree_ancestor(candidate_id, person_id):
        current = person_id
        while current is not None:
            if current == candidate_id:
                return True
            current = tree_parent.get(current)
        return False

    while queue:
        person_id = queue.popleft()
        gen = generations[person_id]
        entries = person_units.get(
            person_id, {'as_partner': (), 'as_child': ()})
        traversals = [
            (index, 'down') for index in entries['as_partner']
            if index not in visited_units
        ] + [
            (index, 'up') for index in entries['as_child']
            if index not in visited_units
        ]
        person_children[person_id] = []
        for index, direction in traversals:
            visited_units.add(index)
            unit = units[index]
            if direction == 'down':
                partner_gen, child_gen = gen, gen + 1
            else:
                partner_gen, child_gen = gen - 1, gen
            new_partners = []
            for partner_id in unit['partners']:
                if partner_id in visited_people:
                    if partner_id == person_id:
                        continue
                    # Cycle cut: prefer cutting a parent-child link over a
                    # marriage.  A partner who sits in a sibling group of
                    # another branch is pulled into this marriage row; the
                    # parent bus reaches them with an elbow connector.
                    source_unit, role = discovered_as.get(
                        partner_id, (None, None))
                    if (role == 'child'
                            and generations[partner_id] == partner_gen
                            and not is_tree_ancestor(partner_id, person_id)):
                        old_node = unit_children.get(source_unit)
                        if old_node and partner_id in old_node['children']:
                            old_node['children'].remove(partner_id)
                            discovered_as[partner_id] = (index, 'partner')
                            tree_parent[partner_id] = person_id
                            new_partners.append(partner_id)
                    continue
                visited_people.add(partner_id)
                generations[partner_id] = partner_gen
                discovered_as[partner_id] = (index, 'partner')
                tree_parent[partner_id] = person_id
                new_partners.append(partner_id)
                queue.append(partner_id)
            new_children = []
            for child_id in unit['children']:
                if child_id in visited_people:
                    continue
                visited_people.add(child_id)
                generations[child_id] = child_gen
                discovered_as[child_id] = (index, 'child')
                tree_parent[child_id] = person_id
                new_children.append(child_id)
                queue.append(child_id)
            if not new_partners and not new_children:
                visited_units.discard(index)
                continue
            person_children[person_id].append((index, direction))
            unit_children[index] = {
                'via': person_id,
                'direction': direction,
                'partners': new_partners,
                'children': new_children,
            }
    return (
        {'person': person_children, 'unit': unit_children},
        generations,
    )


class _Block:
    """A laid-out sub-graph: columns per person plus contour per generation.

    The contour is a sorted list of (low, high) segments per generation.
    Segments whose gap is too narrow to ever hold content (less than twice
    the column spacing) are merged, so real holes are preserved and blocks
    can be fitted into them.
    """

    __slots__ = ('cols', 'extent')

    def __init__(self):
        self.cols = {}
        self.extent = {}

    def place(self, person_id, gen, col):
        self.cols[person_id] = col
        self._add_segment(gen, col, col)

    def _add_segment(self, gen, low, high):
        segments = self.extent.setdefault(gen, [])
        merge_gap = 2 * MIN_COLUMN_SPACING - _EPSILON
        merged = []
        for seg_low, seg_high in segments:
            if seg_high + merge_gap < low or seg_low - merge_gap > high:
                merged.append((seg_low, seg_high))
            else:
                low = min(low, seg_low)
                high = max(high, seg_high)
        merged.append((low, high))
        merged.sort()
        self.extent[gen] = merged

    def shift(self, dx):
        if abs(dx) < _EPSILON:
            return self
        for person_id in self.cols:
            self.cols[person_id] += dx
        self.extent = {
            gen: [(low + dx, high + dx) for low, high in segments]
            for gen, segments in self.extent.items()
        }
        return self

    def absorb(self, other):
        self.cols.update(other.cols)
        for gen, segments in other.extent.items():
            for low, high in segments:
                self._add_segment(gen, low, high)
        return self


def _min_shift_right(acc, block):
    """Smallest dx placing block entirely right of acc without overlap."""
    shift = None
    for gen, segments in block.extent.items():
        if gen not in acc.extent:
            continue
        acc_high = acc.extent[gen][-1][1]
        need = acc_high + MIN_COLUMN_SPACING - segments[0][0]
        if shift is None or need > shift:
            shift = need
    return shift


def _max_shift_left(acc, block):
    """Largest dx placing block entirely left of acc without overlap."""
    shift = None
    for gen, segments in block.extent.items():
        if gen not in acc.extent:
            continue
        acc_low = acc.extent[gen][0][0]
        need = acc_low - MIN_COLUMN_SPACING - segments[-1][1]
        if shift is None or need < shift:
            shift = need
    return shift


def _overlaps(acc, block, dx):
    for gen, segments in block.extent.items():
        acc_segments = acc.extent.get(gen)
        if not acc_segments:
            continue
        for low, high in segments:
            for acc_low, acc_high in acc_segments:
                if (low + dx < acc_high + MIN_COLUMN_SPACING - _EPSILON
                        and high + dx
                        > acc_low - MIN_COLUMN_SPACING + _EPSILON):
                    return True
    return False


def _fit_at_desired(acc, block, desired_dx):
    """Shift closest to desired_dx avoiding contour overlap with acc.

    Tries the desired position first, then every placement flush against a
    contour segment boundary (which includes hole interiors), keeping the
    feasible shift nearest to the desired one.
    """
    if not _overlaps(acc, block, desired_dx):
        return desired_dx
    candidates = set()
    for gen, segments in block.extent.items():
        acc_segments = acc.extent.get(gen)
        if not acc_segments:
            continue
        for low, high in segments:
            for acc_low, acc_high in acc_segments:
                candidates.add(acc_high + MIN_COLUMN_SPACING - low)
                candidates.add(acc_low - MIN_COLUMN_SPACING - high)
    feasible = [dx for dx in candidates if not _overlaps(acc, block, dx)]
    if not feasible:
        return desired_dx
    return min(feasible, key=lambda dx: (abs(dx - desired_dx), dx))


def _block_width(block):
    low = min(segments[0][0] for segments in block.extent.values())
    high = max(segments[-1][1] for segments in block.extent.values())
    return high - low


def _chain_members(person_id, tree):
    """Return the spouse-chain row seeded at person_id, depth first.

    Each element is (person_id, owned_down_units) where owned_down_units are
    the marriages traversed from that person.
    """
    down_units = [
        index for index, direction in tree['person'].get(person_id, ())
        if direction == 'down'
    ]
    members = [(person_id, down_units)]
    for index in down_units:
        for partner_id in tree['unit'][index]['partners']:
            members.extend(_chain_members(partner_id, tree))
    return members


def _order_chain_row(members, seed_persons, tree):
    """Order chain members so every married pair sits adjacent when possible.

    The members and their marriages form a graph; when it is a simple path
    (nobody has more than two spouses in the row) the path order is the
    unique arrangement with all couples adjacent.  Star topologies keep the
    depth-first order.
    """
    if len(members) <= 2:
        return members
    by_id = {person_id: (person_id, downs) for person_id, downs in members}
    adjacency = {person_id: [] for person_id, _downs in members}
    for person_id, downs in members:
        for index in downs:
            for partner_id in tree['unit'][index]['partners']:
                adjacency[person_id].append(partner_id)
                adjacency[partner_id].append(person_id)
    for left_id, right_id in zip(seed_persons, seed_persons[1:]):
        adjacency[left_id].append(right_id)
        adjacency[right_id].append(left_id)

    hubs = [pid for pid, neighbors in adjacency.items()
            if len(set(neighbors)) > 2]
    if len(hubs) == 1:
        # Star: one person with several partners.  Walk the first branch
        # leftward from the hub and the remaining branches rightward, so
        # the hub sits between its partners instead of left of all of them.
        hub = hubs[0]
        branches = []
        seen = {hub}
        for neighbor in adjacency[hub]:
            if neighbor in seen:
                continue
            branch = [neighbor]
            seen.add(neighbor)
            while True:
                nxt = [pid for pid in adjacency[branch[-1]]
                       if pid not in seen]
                if not nxt or len(set(adjacency[branch[-1]])) > 2:
                    break
                branch.append(nxt[0])
                seen.add(nxt[0])
            branches.append(branch)
        if len(seen) == len(members):
            path = list(reversed(branches[0])) + [hub]
            for branch in branches[1:]:
                path.extend(branch)
            return [by_id[person_id] for person_id in path]
        return members
    if hubs:
        return members
    endpoints = [pid for pid, neighbors in adjacency.items()
                 if len(set(neighbors)) <= 1]
    if not endpoints:
        return members

    path = [endpoints[0]]
    seen = {endpoints[0]}
    while True:
        nxt = [pid for pid in adjacency[path[-1]] if pid not in seen]
        if not nxt:
            break
        path.append(nxt[0])
        seen.add(nxt[0])
    if len(path) != len(members):
        return members

    first = path.index(seed_persons[0])
    last = path.index(seed_persons[-1])
    if first > last or (first == last and first > (len(path) - 1) / 2):
        path.reverse()
    return [by_id[person_id] for person_id in path]


def _up_unit(person_id, tree):
    for index, direction in tree['person'].get(person_id, ()):
        if direction == 'up':
            return index
    return None


def _layout_chain(seed_persons, tree, gens, units):
    """Lay out the spouse-chain row seeded by seed_persons and its subtree."""
    members = []
    for seed_id in seed_persons:
        members.extend(_chain_members(seed_id, tree))
    members = _order_chain_row(members, seed_persons, tree)

    block = _Block()
    row_gen = gens[members[0][0]]
    for offset, (person_id, _down_units) in enumerate(members):
        block.place(person_id, row_gen, offset * MIN_COLUMN_SPACING)

    # Siblings: the chain anchor's siblings pack leftward, siblings of any
    # other row member pack on the right end.  Narrow blocks attach nearest
    # the row so leaf siblings stay compact while branchy siblings (whose
    # descendants force wider gaps) move outward.
    sibling_cols = {}
    for person_id, _down_units in members:
        up_index = _up_unit(person_id, tree)
        if up_index is None:
            continue
        sibling_blocks = [
            (sibling_id, _layout_chain([sibling_id], tree, gens, units))
            for sibling_id in tree['unit'][up_index]['children']
        ]
        sibling_blocks.sort(key=lambda item: _block_width(item[1]))
        outward = person_id == seed_persons[0]
        for sibling_id, sib_block in sibling_blocks:
            if outward:
                low_at_row = block.extent[row_gen][0][0]
                desired = (low_at_row - MIN_COLUMN_SPACING
                           - sib_block.cols[sibling_id])
                limit = _max_shift_left(block, sib_block)
                dx = desired if limit is None else min(desired, limit)
            else:
                high_at_row = block.extent[row_gen][-1][1]
                desired = (high_at_row + MIN_COLUMN_SPACING
                           - sib_block.cols[sibling_id])
                limit = _min_shift_right(block, sib_block)
                dx = desired if limit is None else max(desired, limit)
            sib_block.shift(dx)
            block.absorb(sib_block)
            sibling_cols.setdefault(person_id, []).append(
                sib_block.cols[sibling_id])

    # Children of each marriage hang below, centered under the couple.
    for person_id, down_units in members:
        for index in down_units:
            node = tree['unit'][index]
            children = node['children']
            if not children:
                continue
            packed = [
                (child_id, _layout_chain([child_id], tree, gens, units))
                for child_id in children
            ]
            # Narrow blocks first: leaf siblings stay adjacent instead of
            # being separated by a married sibling's spouse and children.
            packed.sort(key=lambda item: _block_width(item[1]))
            group = _Block()
            prev_col = None
            child_blocks = []
            for child_id, child_block in packed:
                if prev_col is None:
                    group.absorb(child_block)
                else:
                    desired = (prev_col + MIN_COLUMN_SPACING
                               - child_block.cols[child_id])
                    limit = _min_shift_right(group, child_block)
                    dx = desired if limit is None else max(desired, limit)
                    child_block.shift(dx)
                    group.absorb(child_block)
                prev_col = group.cols[child_id]
                child_blocks.append(child_id)
            parent_cols = [
                block.cols[pid] for pid in units[index]['partners']
                if pid in block.cols
            ]
            mid = (sum(parent_cols) / len(parent_cols)
                   if parent_cols else block.cols[person_id])
            kid_cols = [group.cols[cid] for cid in child_blocks]
            kid_center = (min(kid_cols) + max(kid_cols)) / 2
            dx = _fit_at_desired(block, group, mid - kid_center)
            group.shift(dx)
            block.absorb(group)

    # Ancestor chains above, centered over their child and its siblings.
    for person_id, _down_units in members:
        up_index = _up_unit(person_id, tree)
        if up_index is None:
            continue
        partners = tree['unit'][up_index]['partners']
        if not partners:
            continue
        parent_block = _layout_chain(partners, tree, gens, units)
        span_cols = [block.cols[person_id]]
        span_cols.extend(sibling_cols.get(person_id, ()))
        desired_center = (min(span_cols) + max(span_cols)) / 2
        partner_cols = [parent_block.cols[pid] for pid in partners]
        partner_center = (min(partner_cols) + max(partner_cols)) / 2
        dx = _fit_at_desired(block, parent_block,
                             desired_center - partner_center)
        parent_block.shift(dx)
        block.absorb(parent_block)

    return block


def _commit_block(block, gens, columns, generations,
                  next_free_column, placed_any):
    """Write a component's block into the global maps, right of prior ones."""
    if not block.cols:
        return
    low = min(segments[0][0] for segments in block.extent.values())
    dx = 0.0
    if placed_any:
        dx = next_free_column[0] + 2 * MIN_COLUMN_SPACING - low
    for person_id, col in block.cols.items():
        columns[person_id] = col + dx
        generations[person_id] = gens[person_id]
    high = max(segments[-1][1] for segments in block.extent.values())
    next_free_column[0] = max(next_free_column[0], high + dx)
