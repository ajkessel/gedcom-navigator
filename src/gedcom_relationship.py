"""
gedcom_relationship.py

Pure-Python helpers for extracting GEDCOM events and generating plain-English
relationship descriptions from BFS paths. This is the most complex part of the
application.
"""

from collections import deque
from dataclasses import dataclass

PARENTAGE_BIRTH = 'birth'
PARENTAGE_ADOPTED = 'adopted'
PARENTAGE_FOSTER = 'foster'
PARENTAGE_STEP = 'step'
PARENTAGE_SEALING = 'sealing'
PARENTAGE_GUARDIAN = 'guardian'
PARENTAGE_OTHER = 'other'

BIOLOGICAL_PARENTAGE = frozenset({PARENTAGE_BIRTH})
NON_BIOLOGICAL_PARENTAGE = frozenset({
    PARENTAGE_ADOPTED,
    PARENTAGE_FOSTER,
    PARENTAGE_STEP,
    PARENTAGE_SEALING,
    PARENTAGE_GUARDIAN,
    PARENTAGE_OTHER,
})

_PARENTAGE_ALIASES = {
    '': PARENTAGE_BIRTH,
    'birth': PARENTAGE_BIRTH,
    'biological': PARENTAGE_BIRTH,
    'bio': PARENTAGE_BIRTH,
    'natural': PARENTAGE_BIRTH,
    'adopted': PARENTAGE_ADOPTED,
    'adoptive': PARENTAGE_ADOPTED,
    'foster': PARENTAGE_FOSTER,
    'step': PARENTAGE_STEP,
    'stepchild': PARENTAGE_STEP,
    'sealing': PARENTAGE_SEALING,
    'sealed': PARENTAGE_SEALING,
    'guardian': PARENTAGE_GUARDIAN,
    'guardianship': PARENTAGE_GUARDIAN,
}


# ---------------------------------------------------------------------------
# GEDCOM event helpers
# ---------------------------------------------------------------------------

def normalize_parentage(value):
    """Return a canonical parent-child relationship kind."""
    key = (value or '').strip().casefold()
    return _PARENTAGE_ALIASES.get(key, PARENTAGE_OTHER)


def _parent_role_in_family(parent_id, fam):
    if parent_id == fam.get('husb'):
        return 'father'
    if parent_id == fam.get('wife'):
        return 'mother'
    return None


def _parentage_from_child_link(fam, child_id, role=None):
    link = (fam.get('child_links') or {}).get(child_id, {})
    if role and link.get(role):
        return normalize_parentage(link.get(role))
    if link.get('family'):
        return normalize_parentage(link.get('family'))
    return PARENTAGE_BIRTH


def parent_child_relationship(parent_id, child_id, individuals, families):
    """Return the parentage kind for parent_id -> child_id.

    Missing metadata is treated as ordinary birth parentage because many GEDCOM
    exports omit explicit PEDI/FREL/MREL values for biological families.
    """
    if not parent_id or not child_id:
        return None
    child = individuals.get(child_id, {})
    fam_ids = list(child.get('famc', ()))
    if not fam_ids:
        fam_ids = [
            fam_id for fam_id, fam in families.items()
            if child_id in fam.get('chil', ())
        ]
    for fam_id in fam_ids:
        fam = families.get(fam_id)
        if not fam or child_id not in fam.get('chil', ()):
            continue
        role = _parent_role_in_family(parent_id, fam)
        if role:
            return _parentage_from_child_link(fam, child_id, role)
    return None


def is_biological_parent(parent_id, child_id, individuals, families):
    """Return whether parent_id is an ordinary biological/default parent."""
    return parent_child_relationship(
        parent_id, child_id, individuals, families) in BIOLOGICAL_PARENTAGE


def biological_parent_ids(child_id, individuals, families):
    """Return biological/default parent IDs for child_id."""
    parents = []
    seen = set()
    child = individuals.get(child_id, {})
    for fam_id in child.get('famc', ()):
        fam = families.get(fam_id)
        if not fam:
            continue
        for parent_id in (fam.get('husb'), fam.get('wife')):
            if (parent_id and parent_id in individuals
                    and parent_id not in seen
                    and is_biological_parent(
                        parent_id, child_id, individuals, families)):
                parents.append(parent_id)
                seen.add(parent_id)
    return parents


def biological_child_ids(parent_id, individuals, families):
    """Return biological/default children for parent_id."""
    children = []
    seen = set()
    parent = individuals.get(parent_id, {})
    for fam_id in parent.get('fams', ()):
        fam = families.get(fam_id)
        if not fam:
            continue
        if parent_id not in (fam.get('husb'), fam.get('wife')):
            continue
        for child_id in fam.get('chil', ()):
            if (child_id and child_id in individuals and child_id not in seen
                    and is_biological_parent(
                        parent_id, child_id, individuals, families)):
                children.append(child_id)
                seen.add(child_id)
    return children


def _spouse_ids(indi_id, individuals, families):
    spouses = []
    seen = set()
    indi = individuals.get(indi_id, {})
    for fam_id in indi.get('fams', ()):
        fam = families.get(fam_id)
        if not fam:
            continue
        spouse_id = fam.get('wife') if fam.get('husb') == indi_id else fam.get('husb')
        if spouse_id and spouse_id in individuals and spouse_id not in seen:
            spouses.append(spouse_id)
            seen.add(spouse_id)
    return spouses


def infer_step_sibling_ids(indi_id, individuals, families):
    """Return people who are step-siblings by parent-spouse topology."""
    result = []
    seen = set()
    own_bio_parents = set(biological_parent_ids(indi_id, individuals, families))
    for parent_id in own_bio_parents:
        for spouse_id in _spouse_ids(parent_id, individuals, families):
            if spouse_id in own_bio_parents:
                continue
            for child_id in biological_child_ids(spouse_id, individuals, families):
                if child_id == indi_id or child_id in seen:
                    continue
                if own_bio_parents.intersection(
                        biological_parent_ids(child_id, individuals, families)):
                    continue
                result.append(child_id)
                seen.add(child_id)
    return result


def sibling_relationship(left_id, right_id, individuals, families):
    """Return full, half, step, sibling, or None for two people."""
    if left_id == right_id:
        return None
    left_parents = set(biological_parent_ids(left_id, individuals, families))
    right_parents = set(biological_parent_ids(right_id, individuals, families))
    shared = left_parents.intersection(right_parents)
    if len(shared) >= 2:
        return 'full'
    if len(shared) == 1:
        return 'half'
    if right_id in infer_step_sibling_ids(left_id, individuals, families):
        return 'step'
    if left_id in infer_step_sibling_ids(right_id, individuals, families):
        return 'step'
    if families:
        for fam in families.values():
            children = fam.get('chil', ())
            if left_id in children and right_id in children:
                return 'sibling'
    return None

def _extract_event(raw, event_tag):
    """Return (date_str, place_str) for the first occurrence of event_tag in raw."""
    date, place = '', ''
    in_event = False
    for level, _xref, tag, value in raw:
        if level == 1:
            if tag == event_tag:
                in_event = True
                date, place = '', ''
            elif in_event:
                break  # left the event's sub-records
            else:
                in_event = False
        elif in_event and level == 2:
            if tag == 'DATE' and not date:
                date = value.strip()
            elif tag == 'PLAC' and not place:
                place = value.strip()
    return date, place


# ---------------------------------------------------------------------------
# Relationship narrative helpers
# ---------------------------------------------------------------------------

def _edge_to_term(edge, sex):
    """Single edge + target sex → plain-English word."""
    if edge in ('father', 'mother'):
        return edge
    if edge == 'sibling':
        return 'brother' if sex == 'M' else ('sister' if sex == 'F' else 'sibling')
    if edge == 'child':
        return 'son' if sex == 'M' else ('daughter' if sex == 'F' else 'child')
    if edge == 'spouse':
        return 'husband' if sex == 'M' else ('wife' if sex == 'F' else 'spouse')
    return edge


_ORDINALS = ['', 'first', 'second', 'third', 'fourth', 'fifth',
             'sixth', 'seventh', 'eighth', 'ninth', 'tenth']
_REMOVALS = {1: 'once', 2: 'twice', 3: 'three times',
             4: 'four times', 5: 'five times'}

_UP_SET = {'father', 'mother'}


@dataclass(frozen=True)
class RelationshipClassification:
    """Structured relationship parts plus the formatted English phrase."""
    description: str
    kind: str
    up: int = 0
    down: int = 0
    sibling: int = 0
    lead_spouse: int = 0
    trail_spouse: int = 0
    spouse_detour: bool = False


class _FamilyLookup:
    """Indexed view of families for repeated relationship checks."""

    def __init__(self, families):
        self._families = families
        self._parents_by_child = None
        self._family_ids_by_child = None
        self._parent_sets_by_child = None

    def __bool__(self):
        return bool(self._families)

    def get(self, fam_id, default=None):
        return self._families.get(fam_id, default)

    def values(self):
        return self._families.values()

    def is_parent_of(self, parent_id, child_id):
        self._ensure_indexes()
        return parent_id in self._parents_by_child.get(child_id, ())

    def share_child_family(self, left_id, right_id):
        self._ensure_indexes()
        left_fams = self._family_ids_by_child.get(left_id, ())
        right_fams = self._family_ids_by_child.get(right_id, ())
        return bool(left_fams and right_fams and left_fams.intersection(right_fams))

    def are_coparents_of(self, left_id, right_id, child_id):
        self._ensure_indexes()
        for parents in self._parent_sets_by_child.get(child_id, ()):
            if left_id in parents and right_id in parents:
                return True
        return False

    def _ensure_indexes(self):
        if self._parents_by_child is not None:
            return
        parents_by_child = {}
        family_ids_by_child = {}
        parent_sets_by_child = {}
        for fam_id, fam in self._families.items():
            parents = {
                parent_id
                for parent_id in (fam.get('husb'), fam.get('wife'))
                if parent_id
            }
            for child_id in fam.get('chil', []):
                family_ids_by_child.setdefault(child_id, set()).add(fam_id)
                parent_sets_by_child.setdefault(child_id, []).append(parents)
                biological_parents = {
                    parent_id for parent_id in parents
                    if _parentage_from_child_link(
                        fam, child_id, _parent_role_in_family(parent_id, fam))
                    in BIOLOGICAL_PARENTAGE
                }
                if biological_parents:
                    parents_by_child.setdefault(child_id, set()).update(
                        biological_parents)
        self._parents_by_child = parents_by_child
        self._family_ids_by_child = family_ids_by_child
        self._parent_sets_by_child = parent_sets_by_child


def prepare_family_lookup(families):
    """Return an indexed family view suitable for repeated relationship labels."""
    if families is None or isinstance(families, _FamilyLookup):
        return families
    return _FamilyLookup(families)


def _nth_great(n):
    """Return 'great-' for n==1, '2nd-great-' for n==2, etc.  n==0 returns ''."""
    if n == 0:
        return ''
    if n == 1:
        return 'great-'
    if 11 <= n % 100 <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}-great-'


def _ancestor_term(n, sex):
    if n == 1:
        return 'father' if sex == 'M' else ('mother' if sex == 'F' else 'parent')
    gp = 'grandfather' if sex == 'M' else (
        'grandmother' if sex == 'F' else 'grandparent')
    return _nth_great(n - 2) + gp


def _descendant_term(n, sex):
    if n == 1:
        return 'son' if sex == 'M' else ('daughter' if sex == 'F' else 'child')
    gc = 'grandson' if sex == 'M' else (
        'granddaughter' if sex == 'F' else 'grandchild')
    return _nth_great(n - 2) + gc


def _non_biological_parent_term(kind, sex):
    parent = 'father' if sex == 'M' else ('mother' if sex == 'F' else 'parent')
    if kind == PARENTAGE_STEP:
        return 'step-' + parent
    if kind == PARENTAGE_ADOPTED:
        return 'adoptive ' + parent
    if kind in (PARENTAGE_FOSTER, PARENTAGE_SEALING):
        return 'foster ' + parent
    if kind in (PARENTAGE_GUARDIAN, PARENTAGE_OTHER):
        return 'non-biological ' + parent
    return parent


def _non_biological_child_term(kind, sex):
    child = 'son' if sex == 'M' else ('daughter' if sex == 'F' else 'child')
    if kind == PARENTAGE_STEP:
        return 'step-' + child
    if kind == PARENTAGE_ADOPTED:
        return 'adopted ' + child
    if kind in (PARENTAGE_FOSTER, PARENTAGE_SEALING):
        return 'foster ' + child
    if kind in (PARENTAGE_GUARDIAN, PARENTAGE_OTHER):
        return 'non-biological ' + child
    return child


def _qualified_sibling_term(kind, sex):
    sibling = 'brother' if sex == 'M' else (
        'sister' if sex == 'F' else 'sibling')
    if kind == 'half':
        return 'half-' + sibling
    if kind == 'step':
        return 'step-' + sibling
    return sibling


def _classify(seq):
    """Classify an edge sequence as up/lateral/down.  Returns (u, d, s, valid)."""
    st = 'up'
    uu = dd = ss = 0
    ok = True
    for e in seq:
        if st == 'up':
            if e in _UP_SET:
                uu += 1
            elif e == 'sibling':
                ss += 1
                st = 'down'
            elif e == 'child':
                dd += 1
                st = 'down'
            else:
                ok = False
                break
        elif st == 'down':
            if e == 'child':
                dd += 1
            else:
                ok = False
                break
    return uu, dd, ss, ok


def _strip_spouse_detours(seq):
    """Remove only spouse hops that act like nuclear-family detours.

    Only strips spouse→child (e.g. uncle→wife→child ≈ uncle→child).
    Does NOT strip spouse→sibling: that hop is a genuine lateral connection
    between two family branches (e.g. user's father→spouse→maternal aunt)
    and removing it produces an incorrect relationship label.
    """
    result = []
    changed = False
    for i, edge in enumerate(seq):
        if (edge == 'spouse'
                and 0 < i < len(seq) - 1
                and seq[i + 1] == 'child'):
            changed = True
            continue
        result.append(edge)
    return result, changed


def _is_parent_of(parent_id, child_id, families):
    if hasattr(families, 'is_parent_of'):
        return families.is_parent_of(parent_id, child_id)
    for fam in families.values():
        if child_id in fam.get('chil', []):
            if parent_id in (fam.get('husb'), fam.get('wife')):
                return True
    return False


def _share_child_family(left_id, right_id, families):
    if hasattr(families, 'share_child_family'):
        return families.share_child_family(left_id, right_id)
    for fam in families.values():
        if left_id in fam.get('chil', []) and right_id in fam.get('chil', []):
            return True
    return False


def _are_coparents_of(left_id, right_id, child_id, families):
    if hasattr(families, 'are_coparents_of'):
        return families.are_coparents_of(left_id, right_id, child_id)
    for fam in families.values():
        if child_id not in fam.get('chil', []):
            continue
        parents = {fam.get('husb'), fam.get('wife')}
        if left_id in parents and right_id in parents:
            return True
    return False


def _path_edges(path):
    return [edge for _, edge in path[1:]]


def _strip_spouse_detours_from_path(path, families):
    """Remove spouse→child only when the child belongs to both spouses."""
    result = [path[0]]
    changed = False
    i = 1
    while i < len(path):
        edge = path[i][1]
        if (edge == 'spouse'
                and i + 1 < len(path)
                and path[i + 1][1] == 'child'
                and _are_coparents_of(
                    result[-1][0], path[i][0], path[i + 1][0], families)):
            changed = True
            result.append((path[i + 1][0], 'child'))
            i += 2
            continue
        result.append(path[i])
        i += 1
    return result, changed


def _trailing_sibling_trim_is_safe(u, d, s):
    """A cousin/sibling's sibling can share the same term; pure up/down cannot."""
    if u == 0 and d == 0:
        return False
    return (u + s) > 0 and (d + s) > 0


def _sibling_normalize(edges):
    """Collapse sibling-equivalent patterns in an edge sequence.

    Three rules applied iteratively until stable:
    1. parent→child ≡ sibling: going up to a shared parent and down to a
       different child is the same relationship type as a direct sibling hop.
    2. sibling→parent ≡ parent: going to a sibling then up to their parent
       reaches your own parent (siblings share parents), so the sibling hop is
       redundant.  Collapses "brother's aunt" → "aunt".
    3. Consecutive sibling edges collapse to one (sibling's sibling = sibling).

    Rules iterate until stable because one substitution can expose another
    (e.g. sibling→parent can expose a new parent→child pair on the next pass).
    """
    result = list(edges)
    while True:
        changed = False
        new = []
        i = 0
        while i < len(result):
            if i + 1 < len(result):
                if result[i] in _UP_SET and result[i + 1] == 'child':
                    new.append('sibling')
                    i += 2
                    changed = True
                    continue
                if result[i] == 'sibling' and result[i + 1] in _UP_SET:
                    new.append(result[i + 1])
                    i += 2
                    changed = True
                    continue
            new.append(result[i])
            i += 1
        collapsed = []
        for e in new:
            if e == 'sibling' and collapsed and collapsed[-1] == 'sibling':
                changed = True
                continue
            collapsed.append(e)
        result = collapsed
        if not changed:
            break
    return result


def _sibling_normalize_path(path, families):
    """Collapse sibling-equivalent path segments only when the graph supports it."""
    result = list(path)
    while True:
        changed = False
        new = [result[0]]
        i = 1
        while i < len(result):
            if i + 1 < len(result):
                first_edge = result[i][1]
                second_edge = result[i + 1][1]
                start_id = new[-1][0]
                mid_id = result[i][0]
                end_id = result[i + 1][0]

                if (first_edge in _UP_SET and second_edge == 'child'
                        and _is_parent_of(mid_id, start_id, families)
                        and _is_parent_of(mid_id, end_id, families)):
                    new.append((end_id, 'sibling'))
                    i += 2
                    changed = True
                    continue

                if (first_edge == 'sibling' and second_edge in _UP_SET
                        and _is_parent_of(end_id, start_id, families)):
                    new.append((end_id, second_edge))
                    i += 2
                    changed = True
                    continue

                if (first_edge == 'sibling' and second_edge == 'sibling'
                        and _share_child_family(start_id, end_id, families)):
                    new.append((end_id, 'sibling'))
                    i += 2
                    changed = True
                    continue

            new.append(result[i])
            i += 1

        result = new
        if not changed:
            break
    return result


def _classify_indirect(inner, path=None, families=None):
    """Classify a non-trivial edge sequence.

    Returns (u, d, s, used_spouse_detour, valid).  Interior spouse edges are
    stripped only when they look like a detour through a relative's spouse to
    that family unit's child or sibling.  A final sibling hop may be trimmed
    for cousin/sibling-style relationships, but never when doing so would turn
    "child's sibling" or "spouse's sibling" into a fake step relationship.

    Consecutive sibling edges are collapsed to one before classification:
    uncle→brother→niece and uncle→niece are the same relationship type since
    a sibling's sibling is still a sibling of the original node.

    When families and a matching path are provided, shortcuts that can cross a
    non-biological boundary are verified against the family graph.  Unverified
    spouse and half-sibling branches fall back to _smart_chain instead of being
    described as biological cousins, ancestors, or descendants.
    """
    if families and path:
        stripped_path, spouse_changed = _strip_spouse_detours_from_path(
            path, families)
        if 'spouse' in _path_edges(stripped_path):
            return 0, 0, 0, False, False

        normalized_path = _sibling_normalize_path(stripped_path, families)
        normalized = _path_edges(normalized_path)
        sibling_changed = normalized_path != stripped_path

        u, d, s, valid = _classify(normalized)
        if valid:
            return u, d, s, spouse_changed or sibling_changed, True
        return 0, 0, 0, False, False

    # Normalize sibling-equivalent patterns: parent→child ≡ sibling (going up
    # to a shared parent and down to a different child is a sibling hop).
    # Then collapse consecutive sibling runs (uncle→brother→niece ≡ uncle→niece).
    # Must be re-applied after spouse stripping because the strip can expose new
    # parent→child adjacencies (e.g. father→spouse→child → father→child after
    # spouse is removed).
    normalized = _sibling_normalize(inner)
    sibling_changed = normalized != inner
    inner = normalized

    u, d, s, valid = _classify(inner)
    if valid:
        # sibling→parent ≡ parent: the ancestor reached via sibling normalization
        # is a direct biological relative (your sibling's parent = your parent),
        # so spouse_detour=True suppresses the spurious 'step-' prefix.
        return u, d, s, sibling_changed, True

    no_sp, changed = _strip_spouse_detours(inner)
    if changed:
        no_sp = _sibling_normalize(no_sp)
        u, d, s, valid = _classify(no_sp)
        if valid:
            return u, d, s, True, True
        if no_sp and no_sp[-1] == 'sibling':
            trimmed = no_sp[:-1]
            if trimmed:
                u, d, s, valid = _classify(trimmed)
                if valid and _trailing_sibling_trim_is_safe(u, d, s):
                    return u, d, s, True, True

    if inner and inner[-1] == 'sibling':
        trimmed = inner[:-1]
        if trimmed:
            u, d, s, valid = _classify(trimmed)
            if valid and _trailing_sibling_trim_is_safe(u, d, s):
                return u, d, s, False, True

    return 0, 0, 0, False, False


def _relationship_from_classification(u, d, s, target_sex, lead_sp=0,
                                      trail_sp=0, spouse_detour=False):
    """Turn a classified edge sequence into a relationship phrase."""
    u_eff = u + s
    d_eff = d + s

    if d_eff == 0:
        core = _ancestor_term(u, target_sex)
        if lead_sp:
            return core + '-in-law'
        return core if spouse_detour else 'step-' + core

    if u_eff == 0:
        core = _descendant_term(d, target_sex)
        if trail_sp:
            return core + '-in-law'
        return core if spouse_detour else 'step-' + core

    cn = min(u_eff, d_eff) - 1
    rem = abs(u_eff - d_eff)
    more_desc = d_eff > u_eff

    if cn == 0 and rem == 0:
        core = 'brother' if target_sex == 'M' else (
            'sister' if target_sex == 'F' else 'sibling')
    elif cn == 0:
        if more_desc:
            core = 'nephew' if target_sex == 'M' else (
                'niece' if target_sex == 'F' else 'niece/nephew')
        else:
            core = 'uncle' if target_sex == 'M' else (
                'aunt' if target_sex == 'F' else 'uncle/aunt')
        if rem > 1:
            core = _nth_great(rem - 1) + core
    else:
        n_str = _ORDINALS[cn] if cn < len(_ORDINALS) else f'{cn}th'
        r_str = _REMOVALS.get(rem, f'{rem} times')
        core = f'{n_str} cousin' + (f' {r_str} removed' if rem else '')

    return core + '-in-law' if (lead_sp or trail_sp) else core


def _relationship_efficiency_score(desc):
    """Lower score means a more compact relationship phrase."""
    possessives = desc.count("'s ")
    words = len(desc.split())
    return possessives, words, len(desc)


def _prefer_more_efficient(path_desc, biological_desc):
    if not biological_desc:
        return path_desc
    if (_relationship_efficiency_score(biological_desc)
            < _relationship_efficiency_score(path_desc)):
        return biological_desc
    return path_desc


def _relationship_from_common_ancestor_depths(start_depth, target_depth,
                                              target_sex):
    return _relationship_from_classification(
        start_depth, target_depth, 0, target_sex, spouse_detour=True)


def _classify_relationship_path(path, individuals, families=None):
    """Return structured relationship parts for a directly classifiable path."""
    if len(path) <= 1:
        return RelationshipClassification('same person', 'same')

    edges = [edge for _, edge in path[1:]]
    target_sex = individuals.get(path[-1][0], {}).get('sex', '')

    if len(edges) == 1 and families:
        start_id = path[0][0]
        target_id = path[-1][0]
        edge = edges[0]
        if edge in _UP_SET:
            kind = parent_child_relationship(
                target_id, start_id, individuals, families)
            if kind in NON_BIOLOGICAL_PARENTAGE:
                return RelationshipClassification(
                    _non_biological_parent_term(kind, target_sex),
                    kind,
                    up=1,
                )
        elif edge == 'child':
            kind = parent_child_relationship(
                start_id, target_id, individuals, families)
            if kind in NON_BIOLOGICAL_PARENTAGE:
                return RelationshipClassification(
                    _non_biological_child_term(kind, target_sex),
                    kind,
                    down=1,
                )
        elif edge == 'sibling':
            kind = sibling_relationship(start_id, target_id, individuals, families)
            if kind in ('half', 'step'):
                return RelationshipClassification(
                    _qualified_sibling_term(kind, target_sex),
                    kind,
                    sibling=1,
                )

    if all(edge in _UP_SET for edge in edges):
        return RelationshipClassification(
            _ancestor_term(len(edges), target_sex),
            'ancestor',
            up=len(edges),
        )

    if all(edge == 'child' for edge in edges):
        return RelationshipClassification(
            _descendant_term(len(edges), target_sex),
            'descendant',
            down=len(edges),
        )

    if len(edges) == 1:
        return RelationshipClassification(
            _edge_to_term(edges[0], target_sex),
            edges[0],
        )

    inner = list(edges)
    lead_sp = trail_sp = 0
    while inner and inner[0] == 'spouse':
        lead_sp += 1
        inner.pop(0)
    while inner and inner[-1] == 'spouse':
        trail_sp += 1
        inner.pop()

    if lead_sp == 1 and trail_sp == 1 and inner == ['sibling']:
        core = 'brother' if target_sex == 'M' else (
            'sister' if target_sex == 'F' else 'sibling')
        return RelationshipClassification(
            core + '-in-law',
            'in_law',
            sibling=1,
            lead_spouse=lead_sp,
            trail_spouse=trail_sp,
        )

    if lead_sp == 1 and trail_sp == 1 and inner and all(e == 'child' for e in inner):
        core = _descendant_term(len(inner), target_sex)
        return RelationshipClassification(
            'step-' + core + '-in-law',
            'step_in_law',
            down=len(inner),
            lead_spouse=lead_sp,
            trail_spouse=trail_sp,
        )

    if not inner or lead_sp > 1 or trail_sp > 1 or (lead_sp and trail_sp):
        return None

    inner_path = path[lead_sp:len(path) - trail_sp]
    up, down, sibling, spouse_detour, valid = _classify_indirect(
        inner, path=inner_path, families=families)
    if not valid:
        return None

    desc = _relationship_from_classification(
        up, down, sibling, target_sex, lead_sp, trail_sp, spouse_detour)
    return RelationshipClassification(
        desc,
        'classified',
        up=up,
        down=down,
        sibling=sibling,
        lead_spouse=lead_sp,
        trail_spouse=trail_sp,
        spouse_detour=spouse_detour,
    )


def _biological_relationship(start_id, target_id, individuals, families,
                             start_ancestors=None):
    """Return the closest direct biological relationship, if one exists."""
    if not families:
        return None
    if start_id == target_id:
        return 'same person'

    target_sex = individuals.get(target_id, {}).get('sex', '')
    if start_ancestors is None:
        start_ancestors = get_ancestor_depths(start_id, individuals, families)
    target_ancestors = get_ancestor_depths(target_id, individuals, families)

    if target_id in start_ancestors:
        return _ancestor_term(start_ancestors[target_id], target_sex)
    if start_id in target_ancestors:
        return _descendant_term(target_ancestors[start_id], target_sex)

    common = set(start_ancestors).intersection(target_ancestors)
    if not common:
        return None

    best = None
    for ancestor_id in common:
        start_depth = start_ancestors[ancestor_id]
        target_depth = target_ancestors[ancestor_id]
        # Prefer the relationship through the nearest common ancestor.
        score = (min(start_depth, target_depth),
                 abs(start_depth - target_depth),
                 start_depth + target_depth)
        if best is None or score < best[0]:  # pylint: disable=unsubscriptable-object
            best = (score, start_depth, target_depth)

    _, start_depth, target_depth = best
    return _relationship_from_common_ancestor_depths(
        start_depth, target_depth, target_sex)


def _describe_sub_path(sub_path, individuals, families=None):
    """Try to describe sub_path compactly.

    Returns a plain-English string if the edge sequence matches a recognized
    pattern (ancestor, descendant, sibling, cousin, in-law, or step-). Returns
    None when no compact pattern matches, signalling _smart_chain to try a
    shorter slice.
    """
    if len(sub_path) <= 1:
        return 'same person'

    classification = _classify_relationship_path(
        sub_path, individuals, families=families)
    return classification.description if classification else None


def _smart_chain(path, individuals, ancestors=None, descendants=None,
                 families=None):
    """Build a compact possessive chain by greedily matching the longest
    recognized sub-path at each position, then joining with "'s ".

    This replaces the naive per-edge chain() fallback and enables compression
    of patterns like 'son's son's son' → 'great-grandson' and
    'husband's sister's husband' → 'brother-in-law'.

    ancestors: optional {id: depth} dict of biological ancestors of path[0].
    Used to avoid labelling a biological ancestor as a 'step-' relative when
    the path reaches them via a roundabout route (e.g. father → spouse →
    biological-mother is still "mother", not "step-mother").

    descendants: optional {id: depth} dict of biological descendants of path[0].
    Used to avoid labelling a biological descendant as a 'step-' relative when
    the path reaches them via a roundabout route (e.g. spouse → child who is
    also a biological child is still "son", not "step-son").
    """
    if len(path) <= 1:
        return 'same person'

    terms = []
    i = 0
    while i < len(path) - 1:
        best_end = None
        best_desc = None
        # Longest match first: try from the full remaining path down to 2 nodes
        for j in range(len(path), i + 1, -1):
            desc = _describe_sub_path(
                path[i:j], individuals, families=families)
            if desc is not None and desc != 'same person':
                best_end = j
                best_desc = desc
                break

        if best_desc is None:
            # Single-edge fallback
            edge = path[i + 1][1]
            sex = individuals.get(path[i + 1][0], {}).get('sex', '')
            best_desc = _edge_to_term(edge, sex)
            best_end = i + 2

        # If a 'step-' label was produced but the terminal node is a known
        # biological ancestor of path[0], use the direct ancestor term instead.
        # Example: father → wife → biological-mother → should be "mother",
        # not "step-mother".
        if (ancestors and best_desc and best_desc.startswith('step-')
                and best_end > 1):
            terminal_id = path[best_end - 1][0]
            if terminal_id in ancestors:
                terminal_sex = individuals.get(terminal_id, {}).get('sex', '')
                best_desc = _ancestor_term(
                    ancestors[terminal_id], terminal_sex)

        # Same fix for descendants: suppress 'step-' when the terminal node
        # is a known biological descendant of path[0].
        # Example: spouse → child who is ALSO a biological child should be
        # "son", not "step-son".
        if (descendants and best_desc and best_desc.startswith('step-')
                and best_end > 1):
            terminal_id = path[best_end - 1][0]
            if terminal_id in descendants:
                terminal_sex = individuals.get(terminal_id, {}).get('sex', '')
                best_desc = _descendant_term(
                    descendants[terminal_id], terminal_sex)

        # Absorb a trailing 'spouse' edge when doing so yields a more compact
        # term (e.g. "first cousin" + "wife" → "first cousin-in-law",
        # "step-son" + "wife" → "step-son-in-law").
        if best_end < len(path) and path[best_end][1] == 'spouse':
            ext_desc = _describe_sub_path(
                path[i:best_end + 1], individuals, families=families)
            if ext_desc is not None and ext_desc != 'same person':
                best_desc = ext_desc
                best_end += 1

        terms.append(best_desc)
        i = best_end - 1

    return "'s ".join(terms)


def get_ancestor_depths(start_id, individuals, families):
    """BFS over father/mother edges only → {ancestor_id: depth from start}."""
    depths = {}
    queue = deque([(start_id, 0)])
    visited = {start_id}
    while queue:
        current_id, depth = queue.popleft()
        indi = individuals.get(current_id)
        if not indi:
            continue
        for fam_id in indi['famc']:
            fam = families.get(fam_id)
            if not fam:
                continue
            for parent_id in (fam['husb'], fam['wife']):
                if (parent_id and parent_id not in visited
                        and is_biological_parent(
                            parent_id, current_id, individuals, families)):
                    visited.add(parent_id)
                    depths[parent_id] = depth + 1
                    queue.append((parent_id, depth + 1))
    return depths


def find_common_ancestors(start_id, end_id, individuals, families):
    """Return the nearest common biological ancestor IDs for two people.

    Multiple ancestors can tie for nearest, commonly the two parents of a pair
    of siblings or the two grandparents shared by first cousins.
    """
    if start_id not in individuals or end_id not in individuals:
        return []
    if start_id == end_id:
        return [start_id]
    if not families:
        return []

    start_ancestors = get_ancestor_depths(start_id, individuals, families)
    start_ancestors[start_id] = 0
    end_ancestors = get_ancestor_depths(end_id, individuals, families)
    end_ancestors[end_id] = 0
    common = {
        ancestor_id
        for ancestor_id in set(start_ancestors).intersection(end_ancestors)
        if ancestor_id in individuals
    }
    if not common:
        return []

    def _score(ancestor_id):
        start_depth = start_ancestors[ancestor_id]
        end_depth = end_ancestors[ancestor_id]
        indi = individuals.get(ancestor_id, {})
        name = indi.get('name') or ancestor_id
        return (
            max(start_depth, end_depth),
            start_depth + end_depth,
            min(start_depth, end_depth),
            name.casefold(),
            ancestor_id,
        )

    best_score = None
    best = []
    for ancestor_id in common:
        score = _score(ancestor_id)
        rank = score[:3]
        if best_score is None or rank < best_score:
            best_score = rank
            best = [ancestor_id]
        elif rank == best_score:
            best.append(ancestor_id)

    return sorted(best, key=_score)


def get_descendant_depths(start_id, individuals, families):
    """BFS over child edges only → {descendant_id: depth from start}."""
    depths = {}
    queue = deque([(start_id, 0)])
    visited = {start_id}
    while queue:
        current_id, depth = queue.popleft()
        indi = individuals.get(current_id)
        if not indi:
            continue
        for fam_id in indi['fams']:
            fam = families.get(fam_id)
            if not fam:
                continue
            for child_id in fam['chil']:
                if (child_id and child_id not in visited
                        and is_biological_parent(
                            current_id, child_id, individuals, families)):
                    visited.add(child_id)
                    depths[child_id] = depth + 1
                    queue.append((child_id, depth + 1))
    return depths


def describe_relationship(path, individuals, ancestors=None, descendants=None,
                          families=None):
    """Return a plain-English relationship from path[0] to path[-1].

    Recognizes ancestors, descendants, siblings, spouses, cousins (all degrees
    and removals), aunts/uncles, nieces/nephews, in-laws, and step-relations.
    Falls back to a compact possessive chain that compresses recognizable
    sub-sequences (e.g. 'son's son's son' → 'great-grandson',
    'husband's sister's husband' → 'brother-in-law').

    ancestors  — optional dict {indi_id: depth} of biological ancestors of
                 path[0], computed by get_ancestor_depths().  When provided,
                 a target who is a known ancestor is always labelled by the
                 direct ancestor term, even if the current path reaches them
                 via a spouse edge (which would otherwise produce "step-X").
    descendants — same idea for biological descendants.
    families — optional family graph.  When provided, a shorter biological
               relationship such as "fourth cousin" can replace a longer
               path-specific description such as "great-aunt's ... cousin".
    """
    if len(path) <= 1:
        return 'same person'

    target_sex = individuals.get(path[-1][0], {}).get('sex', '')

    target_id = path[-1][0]
    biological_desc = _biological_relationship(
        path[0][0], target_id, individuals, families, ancestors)

    if ancestors and target_id in ancestors:
        bio_depth = ancestors[target_id]
        if len(path) - 1 <= bio_depth + 3:
            return _prefer_more_efficient(
                _ancestor_term(bio_depth, target_sex),
                biological_desc)
    if descendants and target_id in descendants:
        bio_depth = descendants[target_id]
        if len(path) - 1 <= bio_depth + 3:
            return _prefer_more_efficient(
                _descendant_term(bio_depth, target_sex),
                biological_desc)

    classification = _classify_relationship_path(
        path, individuals, families=families)
    if classification is not None:
        if classification.lead_spouse or classification.trail_spouse:
            return classification.description
        if classification.kind in (
                'half', 'step', PARENTAGE_ADOPTED, PARENTAGE_FOSTER,
                PARENTAGE_SEALING, PARENTAGE_GUARDIAN, PARENTAGE_OTHER):
            return classification.description
        return _prefer_more_efficient(
            classification.description, biological_desc)

    smart = _smart_chain(
        path, individuals, ancestors=ancestors, descendants=descendants,
        families=families)
    return _prefer_more_efficient(smart, biological_desc)
