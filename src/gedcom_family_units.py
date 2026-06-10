#!/usr/bin/env python3
"""
gedcom_family_units.py

Family-unit model for the family-tree graph layout.

A family unit mirrors a GEDCOM FAM record: a set of parents (partners) and
the children they had together.  Children are grouped by their *full* parent
set, so full siblings share a unit while half- and step-siblings fall into
separate units even when the distinguishing parent is not visible.
"""


def infer_family_members(visible_ids, edges):
    """Build per-person relation lists from edge triples (fallback only).

    Used when the caller cannot supply real family membership data, e.g.
    legacy call sites that only have the visible graph.  Parent sets are then
    limited to visible parents.
    """
    members = {
        visible_id: {
            'parents': [], 'siblings': [], 'spouses': [], 'children': [],
        }
        for visible_id in visible_ids
    }

    def add(person_id, category, other_id):
        entry = members.get(person_id)
        if entry is not None and other_id not in entry[category]:
            entry[category].append(other_id)

    for source_id, target_id, category in edges:
        if category == 'spouses':
            add(source_id, 'spouses', target_id)
            add(target_id, 'spouses', source_id)
        elif category == 'siblings':
            add(source_id, 'siblings', target_id)
            add(target_id, 'siblings', source_id)
        elif category == 'children':
            add(source_id, 'children', target_id)
            add(target_id, 'parents', source_id)
        elif category == 'parents':
            add(source_id, 'parents', target_id)
            add(target_id, 'children', source_id)
    return members


def _parentless_sibling_groups(parentless_ids, family_members):
    """Group children with no known parents by mutual sibling membership."""
    parentless = set(parentless_ids)
    groups = []
    assigned = {}
    for person_id in parentless_ids:
        if person_id in assigned:
            continue
        group = [person_id]
        assigned[person_id] = group
        queue = [person_id]
        while queue:
            current = queue.pop()
            for sibling_id in family_members.get(
                    current, {}).get('siblings', ()):
                if sibling_id in parentless and sibling_id not in assigned:
                    assigned[sibling_id] = group
                    group.append(sibling_id)
                    queue.append(sibling_id)
        groups.append(group)
    return groups


def build_family_units(visible_ids, edges, family_members=None,
                       parent_kind=None):
    """Return (units, person_units) for the visible family graph.

    Each unit is a dict:
      'partners'     visible parents/spouses, deterministic order
      'all_parents'  frozenset of the full parent set (may include hidden ids)
      'children'     visible children of exactly this parent set, birth order

    person_units maps person id -> {'as_partner': [...], 'as_child': [...]}
    holding unit indices.

    parent_kind, when given, is a callable (parent_id, child_id) -> kind
    string ('step', 'adopted', 'birth', ...).  Step-parents are excluded
    from a child's parent set: the child belongs to its real family's unit,
    and the step relationship stays visible through the step-parent's
    marriage.  A child whose recorded parents are all step keeps them, so
    it still gets a connector.
    """
    inferred = family_members is None
    if inferred:
        family_members = infer_family_members(visible_ids, edges)
    visible = set(visible_ids)

    units = []
    units_by_key = {}
    person_units = {
        visible_id: {'as_partner': [], 'as_child': []}
        for visible_id in visible_ids
    }

    def members_for(person_id):
        return family_members.get(person_id, {})

    def unit_for_key(key):
        index = units_by_key.get(key)
        if index is None:
            index = len(units)
            units_by_key[key] = index
            units.append({
                'partners': [
                    parent_id for parent_id in key if parent_id in visible
                ],
                'all_parents': frozenset(key),
                'children': [],
            })
        return index

    def real_parents(child_id):
        parents = tuple(members_for(child_id).get('parents', ()))
        if parent_kind is None or not parents:
            return parents
        non_step = tuple(
            parent_id for parent_id in parents
            if parent_kind(parent_id, child_id) != 'step'
        )
        return non_step or parents

    parent_sets = {
        child_id: real_parents(child_id) for child_id in visible_ids
    }
    # People without recorded parents share their sibling's family: in
    # GEDCOM terms siblings sit in the same FAM record, so a sibling link
    # implies the same parent set.
    changed = True
    while changed:
        changed = False
        for child_id in visible_ids:
            if parent_sets[child_id]:
                continue
            for sibling_id in members_for(child_id).get('siblings', ()):
                if parent_sets.get(sibling_id):
                    parent_sets[child_id] = parent_sets[sibling_id]
                    changed = True
                    break
    if inferred:
        # Edge-only graphs usually record just one parent per child.  When
        # that parent has exactly one visible spouse, treat the couple as
        # the child's parents (real callers pass family_members, where the
        # true parent set distinguishes step relationships).
        for child_id in visible_ids:
            parents = parent_sets[child_id]
            if len(parents) != 1:
                continue
            spouses = [
                spouse_id
                for spouse_id in members_for(parents[0]).get('spouses', ())
                if spouse_id in visible
            ]
            if len(spouses) == 1:
                parent_sets[child_id] = (parents[0], spouses[0])

    parentless = []
    for child_id in visible_ids:
        parents = parent_sets[child_id]
        if not parents:
            if members_for(child_id).get('siblings'):
                parentless.append(child_id)
            continue
        index = unit_for_key(tuple(sorted(parents)))
        units[index]['children'].append(child_id)
        person_units[child_id]['as_child'].append(index)

    for group in _parentless_sibling_groups(parentless, family_members):
        visible_group = [pid for pid in group if pid in visible]
        if len(visible_group) < 2:
            continue
        index = len(units)
        units.append({
            'partners': [],
            'all_parents': frozenset(),
            'children': list(visible_group),
        })
        for child_id in visible_group:
            person_units[child_id]['as_child'].append(index)

    # Couples connected only by spouse edges (no shared visible children).
    for source_id, target_id, category in edges:
        if category != 'spouses':
            continue
        if source_id not in visible or target_id not in visible:
            continue
        couple = frozenset((source_id, target_id))
        if any(couple <= unit['all_parents'] for unit in units):
            continue
        unit_for_key(tuple(sorted(couple)))
    for person_id in visible_ids:
        for spouse_id in members_for(person_id).get('spouses', ()):
            if spouse_id not in visible:
                continue
            couple = frozenset((person_id, spouse_id))
            if any(couple <= unit['all_parents'] for unit in units):
                continue
            unit_for_key(tuple(sorted(couple)))

    for index, unit in enumerate(units):
        for partner_id in unit['partners']:
            partner_units = person_units[partner_id]['as_partner']
            if index not in partner_units:
                partner_units.append(index)

    _order_unit_members(units, person_units, visible_ids, family_members)
    return units, person_units


def _order_unit_members(units, person_units, visible_ids, family_members):
    """Order partners by spouse-list order and children by birth order."""
    list_order = {pid: i for i, pid in enumerate(visible_ids)}

    for unit in units:
        partners = unit['partners']
        if len(partners) > 1:
            partners.sort(key=lambda pid: list_order.get(pid, len(list_order)))
        children = unit['children']
        if len(children) > 1:
            birth_order = {}
            for partner_id in unit['all_parents']:
                for i, child_id in enumerate(
                        family_members.get(partner_id, {}).get(
                            'children', ())):
                    birth_order.setdefault(child_id, i)
            children.sort(key=lambda cid: (
                birth_order.get(cid, len(birth_order)),
                list_order.get(cid, len(list_order)),
            ))

    for person_id, entry in person_units.items():
        spouse_order = {
            sid: i for i, sid in enumerate(
                family_members.get(person_id, {}).get('spouses', ()))
        }

        def partner_sort_key(index, _person_id=person_id,
                             _spouse_order=spouse_order):
            unit = units[index]
            others = [
                pid for pid in unit['partners'] if pid != _person_id
            ]
            if not others:
                return (len(_spouse_order) + 1, index)
            return (min(_spouse_order.get(pid, len(_spouse_order))
                        for pid in others), index)

        entry['as_partner'].sort(key=partner_sort_key)
