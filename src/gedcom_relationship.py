"""
gedcom_relationship.py

Pure-Python helpers for extracting GEDCOM events and generating plain-English
relationship descriptions from BFS paths. This is the most complex part of the
application.
"""

from collections import deque


# ---------------------------------------------------------------------------
# GEDCOM event helpers
# ---------------------------------------------------------------------------

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


def _collapse_marriage_bridges(edges):
    """Collapse sibling→spouse→sibling to sibling (marriage bridge = same generation).

    When two people are connected via sibling→spouse→sibling, they are at the
    same generational level as direct siblings.  This equivalence is only used
    at the top level of describe_relationship (not in _smart_chain sub-paths),
    controlled by the allow_bridge flag in _classify_indirect.
    """
    result = []
    i = 0
    while i < len(edges):
        if (i + 2 < len(edges)
                and edges[i] == 'sibling'
                and edges[i + 1] == 'spouse'
                and edges[i + 2] == 'sibling'):
            result.append('sibling')
            i += 3
        else:
            result.append(edges[i])
            i += 1
    return result


def _classify_indirect(inner, allow_bridge=False):
    """Classify a non-trivial edge sequence.

    Returns (u, d, s, used_spouse_detour, valid).  Interior spouse edges are
    stripped only when they look like a detour through a relative's spouse to
    that family unit's child or sibling.  A final sibling hop may be trimmed
    for cousin/sibling-style relationships, but never when doing so would turn
    "child's sibling" or "spouse's sibling" into a fake step relationship.

    Consecutive sibling edges are collapsed to one before classification:
    uncle→brother→niece and uncle→niece are the same relationship type since
    a sibling's sibling is still a sibling of the original node.

    allow_bridge: when True, collapse sibling→spouse→sibling patterns (marriage
    bridges) to sibling before classifying.  Enabled both at the top level of
    describe_relationship and in _describe_sub_path (used by _smart_chain), so
    that compound paths like "first cousin once removed-in-law's first cousin
    once removed" are expressed using compact cousin terms rather than the
    verbose possessive chain that would result without the bridge recognition.
    """
    # Normalize sibling-equivalent patterns: parent→child ≡ sibling (going up
    # to a shared parent and down to a different child is a sibling hop).
    # Then collapse consecutive sibling runs (uncle→brother→niece ≡ uncle→niece).
    # Must be re-applied after spouse stripping because the strip can expose new
    # parent→child adjacencies (e.g. father→spouse→child → father→child after
    # spouse is removed).
    normalized = _sibling_normalize(inner)
    sibling_changed = normalized != inner
    inner = normalized

    # Marriage bridge: sibling→spouse→sibling acts as a direct sibling hop.
    # Only applied at top-level classification (not in _smart_chain sub-paths).
    if allow_bridge:
        bridged = _collapse_marriage_bridges(inner)
        if bridged != inner:
            inner = _sibling_normalize(bridged)
            sibling_changed = True

    u, d, s, valid = _classify(inner)
    if valid:
        # sibling→parent ≡ parent: the ancestor reached via sibling normalization
        # is a direct biological relative (your sibling's parent = your parent),
        # so spouse_detour=True suppresses the spurious 'step-' prefix.
        return u, d, s, sibling_changed, True

    no_sp, changed = _strip_spouse_detours(inner)
    if changed:
        no_sp = _sibling_normalize(no_sp)
        # Re-apply marriage bridge collapse after stripping, since stripping a
        # spouse→child detour (e.g. Harris→Eva→Louis) can expose a new
        # sibling→spouse→sibling bridge that wasn't visible before.
        if allow_bridge:
            bridged = _collapse_marriage_bridges(no_sp)
            if bridged != no_sp:
                no_sp = _sibling_normalize(bridged)
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


def _describe_sub_path(sub_path, individuals):
    """Try to describe sub_path compactly.

    Returns a plain-English string if the edge sequence matches a recognized
    pattern (ancestor, descendant, sibling, cousin, in-law, step-, or the
    spouse→sibling→spouse "brother/sister-in-law" idiom).  Returns None when
    no compact pattern matches, signalling _smart_chain to try a shorter slice.
    """
    if len(sub_path) <= 1:
        return 'same person'

    edges = [e for _, e in sub_path[1:]]
    sexes = [individuals.get(nid, {}).get('sex', '') for nid, _ in sub_path]
    target_sex = sexes[-1]

    # Pure ancestor (all parent edges)
    if all(e in _UP_SET for e in edges):
        return _ancestor_term(len(edges), target_sex)

    # Pure descendant (all child edges)
    if all(e == 'child' for e in edges):
        return _descendant_term(len(edges), target_sex)

    # Single edge
    if len(edges) == 1:
        return _edge_to_term(edges[0], target_sex)

    # Strip leading/trailing spouse edges
    inner = list(edges)
    lead_sp = trail_sp = 0
    while inner and inner[0] == 'spouse':
        lead_sp += 1
        inner.pop(0)
    while inner and inner[-1] == 'spouse':
        trail_sp += 1
        inner.pop()

    # spouse → sibling → spouse → "brother/sister-in-law"
    if lead_sp == 1 and trail_sp == 1 and inner == ['sibling']:
        core = 'brother' if target_sex == 'M' else (
            'sister' if target_sex == 'F' else 'sibling')
        return core + '-in-law'

    # spouse → child(ren) → spouse → "step-son/daughter-in-law" etc.
    if lead_sp == 1 and trail_sp == 1 and inner and all(e == 'child' for e in inner):
        core = _descendant_term(len(inner), target_sex)
        return 'step-' + core + '-in-law'

    if not inner or lead_sp > 1 or trail_sp > 1 or (lead_sp and trail_sp):
        return None

    u, d, s, spouse_detour, valid = _classify_indirect(inner, allow_bridge=True)

    if not valid:
        return None

    return _relationship_from_classification(
        u, d, s, target_sex, lead_sp, trail_sp, spouse_detour)


def _smart_chain(path, individuals, ancestors=None):
    """Build a compact possessive chain by greedily matching the longest
    recognized sub-path at each position, then joining with "'s ".

    This replaces the naive per-edge chain() fallback and enables compression
    of patterns like 'son's son's son' → 'great-grandson' and
    'husband's sister's husband' → 'brother-in-law'.

    ancestors: optional {id: depth} dict of biological ancestors of path[0].
    Used to avoid labelling a biological ancestor as a 'step-' relative when
    the path reaches them via a roundabout route (e.g. father → spouse →
    biological-mother is still "mother", not "step-mother").
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
            desc = _describe_sub_path(path[i:j], individuals)
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

        # Absorb a trailing 'spouse' edge when doing so yields a more compact
        # term (e.g. "first cousin" + "wife" → "first cousin-in-law",
        # "step-son" + "wife" → "step-son-in-law").
        if best_end < len(path) and path[best_end][1] == 'spouse':
            ext_desc = _describe_sub_path(path[i:best_end + 1], individuals)
            if ext_desc is not None and ext_desc != 'same person':
                best_desc = ext_desc
                best_end += 1

        # When an uncle/aunt-type term is an intermediate step (not the final
        # target) and arose from a trailing spouse edge, drop the '-in-law'
        # suffix.  Colloquially, a parent's sibling's spouse is called
        # 'uncle'/'aunt', so "uncle-in-law's father" → "uncle's father".
        if (best_end < len(path)
                and best_desc.endswith('-in-law')
                and path[best_end - 1][1] == 'spouse'):
            base = best_desc[:-len('-in-law')]
            if base == 'uncle' or base.endswith('uncle') \
                    or base == 'aunt' or base.endswith('aunt'):
                best_desc = base

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
                if parent_id and parent_id not in visited:
                    visited.add(parent_id)
                    depths[parent_id] = depth + 1
                    queue.append((parent_id, depth + 1))
    return depths


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
                if child_id and child_id not in visited:
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

    edges = [e for _, e in path[1:]]
    sexes = [individuals.get(nid, {}).get('sex', '') for nid, _ in path]
    target_sex = sexes[-1]

    target_id = path[-1][0]
    biological_desc = _biological_relationship(
        path[0][0], target_id, individuals, families, ancestors)

    if ancestors and target_id in ancestors:
        return _prefer_more_efficient(
            _ancestor_term(ancestors[target_id], target_sex),
            biological_desc)
    if descendants and target_id in descendants:
        return _prefer_more_efficient(
            _descendant_term(descendants[target_id], target_sex),
            biological_desc)

    # Pure ancestor (all father/mother edges)
    if all(e in _UP_SET for e in edges):
        return _prefer_more_efficient(
            _ancestor_term(len(edges), target_sex), biological_desc)

    # Pure descendant (all child edges)
    if all(e == 'child' for e in edges):
        return _prefer_more_efficient(
            _descendant_term(len(edges), target_sex), biological_desc)

    # Single edge (sibling, spouse, etc.)
    if len(edges) == 1:
        return _prefer_more_efficient(
            _edge_to_term(edges[0], target_sex), biological_desc)

    # Strip exactly one leading or one trailing spouse; anything else → smart chain
    inner = list(edges)
    lead_sp = trail_sp = 0
    while inner and inner[0] == 'spouse':
        lead_sp += 1
        inner.pop(0)
    while inner and inner[-1] == 'spouse':
        trail_sp += 1
        inner.pop()

    # spouse → sibling → spouse = "brother/sister-in-law"
    if lead_sp == 1 and trail_sp == 1 and inner == ['sibling']:
        core = 'brother' if target_sex == 'M' else (
            'sister' if target_sex == 'F' else 'sibling')
        return core + '-in-law'

    if not inner or lead_sp > 1 or trail_sp > 1 or (lead_sp and trail_sp):
        smart = _smart_chain(path, individuals, ancestors=ancestors)
        if lead_sp or trail_sp:
            return smart
        return _prefer_more_efficient(smart, biological_desc)

    u, d, s, spouse_detour, valid = _classify_indirect(inner, allow_bridge=True)
    if not valid:
        smart = _smart_chain(path, individuals, ancestors=ancestors)
        if lead_sp or trail_sp:
            return smart
        return _prefer_more_efficient(smart, biological_desc)

    path_desc = _relationship_from_classification(
        u, d, s, target_sex, lead_sp, trail_sp, spouse_detour)
    if lead_sp or trail_sp:
        return path_desc
    return _prefer_more_efficient(path_desc, biological_desc)
