"""
gedcom_relationship.py

Pure-Python helpers for extracting GEDCOM events and generating plain-English
relationship descriptions from BFS paths.  No tkinter dependency.
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

    u, d, s, valid = _classify(inner)
    if not valid:
        no_sp = [e for e in inner if e != 'spouse']
        if no_sp != inner:
            u, d, s, valid = _classify(no_sp)
        else:
            no_sp = inner
        if not valid and no_sp and no_sp[-1] == 'sibling':
            trimmed = no_sp[:-1]
            if trimmed:
                u, d, s, valid = _classify(trimmed)

    if not valid:
        return None

    u_eff = u + s
    d_eff = d + s

    if d_eff == 0:
        core = _ancestor_term(u, target_sex)
        return core + '-in-law' if lead_sp else 'step-' + core

    if u_eff == 0:
        core = _descendant_term(d, target_sex)
        return core + '-in-law' if trail_sp else 'step-' + core

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


def _smart_chain(path, individuals):
    """Build a compact possessive chain by greedily matching the longest
    recognized sub-path at each position, then joining with "'s ".

    This replaces the naive per-edge chain() fallback and enables compression
    of patterns like 'son's son's son' → 'great-grandson' and
    'husband's sister's husband' → 'brother-in-law'.
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


def describe_relationship(path, individuals, ancestors=None, descendants=None):
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
    """
    if len(path) <= 1:
        return 'same person'

    edges = [e for _, e in path[1:]]
    sexes = [individuals.get(nid, {}).get('sex', '') for nid, _ in path]
    target_sex = sexes[-1]

    target_id = path[-1][0]
    if ancestors and target_id in ancestors:
        return _ancestor_term(ancestors[target_id], target_sex)
    if descendants and target_id in descendants:
        return _descendant_term(descendants[target_id], target_sex)

    # Pure ancestor (all father/mother edges)
    if all(e in _UP_SET for e in edges):
        return _ancestor_term(len(edges), target_sex)

    # Pure descendant (all child edges)
    if all(e == 'child' for e in edges):
        return _descendant_term(len(edges), target_sex)

    # Single edge (sibling, spouse, etc.)
    if len(edges) == 1:
        return _edge_to_term(edges[0], target_sex)

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
        return _smart_chain(path, individuals)

    u, d, s, valid = _classify(inner)
    if not valid:
        no_sp = [e for e in inner if e != 'spouse']
        if no_sp != inner:
            u, d, s, valid = _classify(no_sp)
        else:
            no_sp = inner
        if not valid and no_sp and no_sp[-1] == 'sibling':
            trimmed = no_sp[:-1]
            if trimmed:
                u, d, s, valid = _classify(trimmed)
    if not valid:
        return _smart_chain(path, individuals)

    u_eff = u + s
    d_eff = d + s

    if d_eff == 0:
        return (_ancestor_term(u, target_sex) + '-in-law' if lead_sp
                else 'step-' + _ancestor_term(u, target_sex))

    if u_eff == 0:
        return (_descendant_term(d, target_sex) + '-in-law' if trail_sp
                else 'step-' + _descendant_term(d, target_sex))

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
