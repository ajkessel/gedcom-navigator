#!/usr/bin/env python3
"""
gedcom_search.py

Relationship graph traversal and pathfinding for GEDCOM family models.
"""

import heapq
import time
from collections import deque

from gedcom_relationship import (
    describe_relationship as _describe_rel,
    get_ancestor_depths as _get_ancestor_depths,
    get_descendant_depths as _get_descendant_depths,
    prepare_family_lookup as _prepare_family_lookup,
)

_GUI_YIELD_CHECKS = 4096
_GUI_YIELD_SECONDS = 0


class SearchCancelled(Exception):
    """Raised when a long-running search is canceled by the caller."""


def _check_cancelled(cancel_event):
    """Raise SearchCancelled if cancel_event has been set.

    GUI searches pass a cancellation event from a worker thread.  Periodically
    yielding here gives Tk's main thread a chance to animate progress while the
    worker is running CPU-heavy Python loops.
    """
    if cancel_event is None:
        return
    if cancel_event.is_set():
        raise SearchCancelled()
    try:
        checks = getattr(cancel_event, '_gedcom_check_count', 0) + 1
        if checks >= _GUI_YIELD_CHECKS:
            checks = 0
            time.sleep(_GUI_YIELD_SECONDS)
        setattr(cancel_event, '_gedcom_check_count', checks)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _positive_int(value, name):
    """Return value as a positive integer or raise ValueError."""
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return parsed


def neighbors(indi_id, individuals, families):
    """Yield (neighbor_id, edge_label) for one BFS step.

    Edges:
      father / mother  via FAMC (parents)
      sibling          via FAMC (other children of the same family)
      spouse           via FAMS (the other partner)
      child            via FAMS (children of this person)
    """
    indi = individuals.get(indi_id)
    if not indi:
        return
    for fam_id in indi['famc']:
        fam = families.get(fam_id)
        if not fam:
            continue
        if fam['husb'] and fam['husb'] != indi_id:
            yield fam['husb'], 'father'
        if fam['wife'] and fam['wife'] != indi_id:
            yield fam['wife'], 'mother'
        for child_id in fam['chil']:
            if child_id != indi_id:
                yield child_id, 'sibling'
    for fam_id in indi['fams']:
        fam = families.get(fam_id)
        if not fam:
            continue
        if fam['husb'] and fam['husb'] != indi_id:
            yield fam['husb'], 'spouse'
        if fam['wife'] and fam['wife'] != indi_id:
            yield fam['wife'], 'spouse'
        for child_id in fam['chil']:
            yield child_id, 'child'


class _NeighborCache:
    """Lazily cache full neighbor lists for path searches."""

    def __init__(self, individuals, families):
        self._individuals = individuals
        self._families = families
        self._cache = {}

    def __call__(self, indi_id):
        cached = self._cache.get(indi_id)
        if cached is None:
            cached = tuple(neighbors(indi_id, self._individuals, self._families))
            self._cache[indi_id] = cached
        return cached


class _BfsNeighborExpander:
    """Yield BFS neighbors while expanding each family child list once."""

    def __init__(self, individuals, families):
        self._individuals = individuals
        self._families = families
        self._expanded_sibling_fams = set()
        self._expanded_spouse_fams = set()

    def __call__(self, indi_id):
        indi = self._individuals.get(indi_id)
        if not indi:
            return
        for fam_id in indi['famc']:
            fam = self._families.get(fam_id)
            if not fam:
                continue
            if fam['husb'] and fam['husb'] != indi_id:
                yield fam['husb'], 'father'
            if fam['wife'] and fam['wife'] != indi_id:
                yield fam['wife'], 'mother'
            if fam_id in self._expanded_sibling_fams:
                continue
            self._expanded_sibling_fams.add(fam_id)
            for child_id in fam['chil']:
                if child_id != indi_id:
                    yield child_id, 'sibling'
        for fam_id in indi['fams']:
            fam = self._families.get(fam_id)
            if not fam or fam_id in self._expanded_spouse_fams:
                continue
            self._expanded_spouse_fams.add(fam_id)
            if fam['husb'] and fam['husb'] != indi_id:
                yield fam['husb'], 'spouse'
            if fam['wife'] and fam['wife'] != indi_id:
                yield fam['wife'], 'spouse'
            for child_id in fam['chil']:
                yield child_id, 'child'


def bfs_find_dna_matches(start_id, individuals, families, top_n, max_depth,
                         cancel_event=None):
    """Return a list of (distance, path) for the nearest DNA-flagged people.

    The BFS continues through DNA-flagged nodes, so a flagged person
    a few hops past another flagged person can still be discovered.
    """
    top_n = _positive_int(top_n, "top_n")
    max_depth = _positive_int(max_depth, "max_depth")

    if start_id not in individuals:
        return []

    # predecessor[node] = (predecessor_id, edge_label_into_node)
    predecessor = {start_id: None}
    queue = deque([(start_id, 0)])
    found = []
    bfs_neighbors = _BfsNeighborExpander(individuals, families)

    while queue:
        _check_cancelled(cancel_event)
        current_id, dist = queue.popleft()
        if dist >= max_depth:
            continue
        for neighbor_id, edge_label in bfs_neighbors(current_id):
            _check_cancelled(cancel_event)
            if neighbor_id in predecessor:
                continue
            predecessor[neighbor_id] = (current_id, edge_label)
            new_dist = dist + 1
            if individuals[neighbor_id]['dna_markers']:
                found.append((new_dist, neighbor_id))
                if len(found) >= top_n:
                    break
            queue.append((neighbor_id, new_dist))
        if len(found) >= top_n:
            break

    results = []
    for dist, end_id in found:
        path = []
        node = end_id
        while node is not None:
            pred = predecessor[node]
            if pred is None:
                path.append((node, None))
                break
            path.append((node, pred[1]))
            node = pred[0]
        path.reverse()
        results.append((dist, path))
    return results

_UP_EDGES = frozenset({'father', 'mother'})


def _path_kinship_signature(path):
    """Return a canonical kinship tuple used to deduplicate genealogically equivalent paths.

    Two paths represent the same relationship type when they yield the same signature.
    Algorithm:
      1. Strip interior spouse-detour hops (spouse immediately before child/sibling).
      2. Peel bare leading/trailing spouse edges (in-law indicator).
      3. Classify the core as up* [sibling] down*, yielding (u, d, s).
      4. If a trailing sibling causes classification to fail, trim it — but only
         when the path already has both ascending and descending components, so that
         a first cousin's sibling collapses to the same signature as the first cousin.
      5. Fall back to a normalized edge tuple for unusual paths.
    """
    if len(path) <= 1:
        return ('self',)

    raw = [e for _, e in path[1:]]

    # Step 1: strip interior spouse→child detours only.
    # spouse→sibling is a genuine lateral hop (e.g. father→mother→maternal aunt)
    # and must not be stripped, or the resulting classification is wrong.
    edges = []
    i = 0
    while i < len(raw):
        if (raw[i] == 'spouse' and i + 1 < len(raw)
                and raw[i + 1] == 'child'):
            i += 1
        else:
            edges.append(raw[i])
            i += 1

    # Step 1.2: collapse father/mother→child pairs to sibling.
    # Going up to a parent then back down to a different child of that parent
    # is the same generational hop as a direct sibling edge.  This is the
    # ascending-then-descending analogue of the spouse→child strip above.
    # Example: [child, father, child, sibling] → [child, sibling, sibling]
    # which later collapses to [child] (a grandchild of the start).
    collapsed_pc = []
    i = 0
    while i < len(edges):
        if (edges[i] in _UP_EDGES and i + 1 < len(edges)
                and edges[i + 1] == 'child'):
            collapsed_pc.append('sibling')
            i += 2
        else:
            collapsed_pc.append(edges[i])
            i += 1
    edges = collapsed_pc

    # Step 1.3: collapse child→sibling to child.
    # A node's child's sibling is also that node's child — the lateral sibling
    # hop after a descending hop stays at the same generational level and is
    # redundant for kinship-type purposes.  This canonicalises paths like
    # [child, sibling, child] (grandparent→child→sibling→grandchild) to
    # [child, child] (same signature as the direct grandchild path).
    collapsed_cs = []
    for e in edges:
        if e == 'sibling' and collapsed_cs and collapsed_cs[-1] == 'child':
            continue
        collapsed_cs.append(e)
    edges = collapsed_cs

    # Step 1.5: collapse consecutive sibling hops to one.
    # A's sibling's sibling is genealogically the same level as A's sibling
    # (they share the same parents), so routing through uncle1→uncle2→... vs
    # directly through uncle1 represents the same relationship type.
    collapsed = []
    for e in edges:
        if e == 'sibling' and collapsed and collapsed[-1] == 'sibling':
            continue
        collapsed.append(e)
    edges = collapsed

    # Step 2: peel leading/trailing bare spouse edges
    lead_sp = trail_sp = 0
    while edges and edges[0] == 'spouse':
        lead_sp += 1
        edges.pop(0)
    while edges and edges[-1] == 'spouse':
        trail_sp += 1
        edges.pop()

    if not edges:
        return ('spouse', lead_sp, trail_sp)

    def _classify(seq):
        state = 'up'
        u = d = s = 0
        for e in seq:
            if state == 'up':
                if e in _UP_EDGES:
                    u += 1
                elif e == 'sibling':
                    s += 1
                    state = 'down'
                elif e == 'child':
                    d += 1
                    state = 'down'
                else:
                    return None
            else:
                if e == 'child':
                    d += 1
                else:
                    return None
        return u, d, s

    # Step 3: try direct classification
    result = _classify(edges)
    if result:
        u, d, s = result
        return ('kin', u, d, s, lead_sp, trail_sp)

    # Step 4: trim trailing sibling and retry.
    # A trailing sibling means "one of their siblings", which is the same kinship
    # level when the remaining path already has a downward component (child or
    # sibling hop already taken).  Purely-ascending paths must NOT be collapsed:
    # [father, sibling] = uncle/aunt, which differs from [father] = parent.
    if edges[-1] == 'sibling':
        result = _classify(edges[:-1])
        if result:
            u, d, s = result
            if (d + s) > 0:
                return ('kin', u, d, s, lead_sp, trail_sp)

    # Step 5: fallback to normalized edge tuple.
    # Also trim a trailing sibling so paths that reach the same marriage bridge
    # via the target's sibling share a signature with those that don't.
    if edges and edges[-1] == 'sibling':
        edges = edges[:-1]
    if not edges:
        return ('spouse', lead_sp, trail_sp)
    norm = tuple('up' if e in _UP_EDGES else e for e in edges)
    return ('chain', norm, lead_sp, trail_sp)


def _is_spouse_detour_of(longer, shorter):
    """Return True if `longer` is `shorter` with detour nodes inserted.

    Two kinds of detour node are recognised:

    1. Spouse detour: node N where the immediately following node (in shorter)
       is reached from N via a 'spouse' edge.  Any number of these are allowed.
       Example: uncle→wife→child ≡ uncle→child (wife is the detour).

    2. Child→parent detour: node N that was reached via a 'child' edge AND the
       immediately following node (in shorter) is reached from N via a 'father'
       or 'mother' edge.  X→N(child)→Y(parent) ≡ X→Y(spouse) because Y is the
       co-parent of N, i.e. X's spouse.  At most ONE such detour is allowed per
       comparison; paths that require two or more child→parent shortcuts differ
       enough to be kept as distinct relationships.
       Example: Judith→Matthew(child)→Glenn(father) ≡ Judith→Glenn(spouse).
    """
    shorter_ids = {nid for nid, _ in shorter}
    shorter_list = [nid for nid, _ in shorter]
    if longer[0][0] != shorter_list[0] or longer[-1][0] != shorter_list[-1]:
        return False
    if len(longer) <= len(shorter):
        return False
    filtered = []
    child_parent_used = 0
    i = 0
    while i < len(longer):
        nid, incoming_edge = longer[i]
        if nid in shorter_ids:
            filtered.append(nid)
            i += 1
        elif i + 1 < len(longer) and longer[i + 1][0] in shorter_ids:
            next_edge = longer[i + 1][1]
            if next_edge == 'spouse':
                i += 1  # classic spouse detour; unlimited
            elif (next_edge in _UP_EDGES
                  and incoming_edge == 'child'
                  and child_parent_used == 0):
                child_parent_used = 1  # allow at most one
                i += 1
            else:
                return False
        else:
            return False
    return filtered == shorter_list


def _filter_spouse_detours(paths):
    """Remove paths that are detour variants of a shorter path in the same list."""
    if len(paths) <= 1:
        return paths
    paths = sorted(paths, key=len)
    kept = [paths[0]]
    for candidate in paths[1:]:
        if not any(_is_spouse_detour_of(candidate, keeper) for keeper in kept):
            kept.append(candidate)
    return kept


def _find_shortest_path(start_id, target_id, individuals, families, max_depth,
                        exclude=None, cancel_event=None):
    """BFS shortest path from start to target; returns path list or None.

    exclude: optional set of node IDs to skip (except target_id itself).
    """
    if start_id not in individuals or target_id not in individuals:
        return None
    if start_id == target_id:
        return [(start_id, None)]
    _exclude = frozenset(exclude) if exclude else frozenset()
    predecessor = {start_id: None}
    queue = deque([(start_id, 0)])
    bfs_neighbors = _BfsNeighborExpander(individuals, families)
    while queue:
        _check_cancelled(cancel_event)
        current_id, dist = queue.popleft()
        if dist >= max_depth:
            continue
        for neighbor_id, edge_label in bfs_neighbors(current_id):
            _check_cancelled(cancel_event)
            if neighbor_id in predecessor:
                continue
            if neighbor_id in _exclude and neighbor_id != target_id:
                continue
            predecessor[neighbor_id] = (current_id, edge_label)
            if neighbor_id == target_id:
                path = []
                node = target_id
                while node is not None:
                    pred = predecessor[node]
                    if pred is None:
                        path.append((node, None))
                        break
                    path.append((node, pred[1]))
                    node = pred[0]
                path.reverse()
                return path
            queue.append((neighbor_id, dist + 1))
    return None


def _reverse_edge_for_path(edge, from_sex):
    """Reverse a reverse-BFS edge to get the corresponding forward-path edge.

    When the reverse BFS traverses edge `edge` from `from_node` to `to_node`,
    the forward path edge going from `to_node` to `from_node` is:
      father/mother → child  (we went UP to a parent; forward is DOWN to that child)
      child → father/mother  (we went DOWN to a child; forward is UP to that parent)
      sibling/spouse → same  (symmetric edges)
    `from_sex` is the sex of `from_node` (the node closer to end in reverse BFS),
    used only when reversing a 'child' edge.
    """
    if edge in ('father', 'mother'):
        return 'child'
    if edge == 'child':
        return 'father' if from_sex == 'M' else 'mother' if from_sex == 'F' else 'father'
    return edge  # 'sibling' and 'spouse' are symmetric


def _marriage_bridge_expansion(start_id, end_id, individuals, families,
                                max_depth, found_labels, found_sigs,
                                start_ancestors, slots, descendants=None,
                                cancel_event=None):
    """Find paths via marriage bridges: X (near start) married to Y (near end).

    Runs bounded BFS from both endpoints to depth half=min(10, max_depth//2).
    For each node X reachable from start, checks whether any of X's spouses Y is
    reachable from end.  When such a bridge (X, Y) is found, the two BFS sub-paths
    are composed into a single path start→…→X→(spouse)→Y→…→end.

    This lets the search discover long compound relationships like
    "first cousin once removed-in-law's first cousin once removed" without
    requiring the A* search to traverse the full depth.
    """
    half = min(10, max_depth // 2)

    # Forward BFS from start_id: pred[node] = (prev_node, edge_label)
    fwd_pred = {start_id: None}
    fwd_q = deque([(start_id, 0)])
    fwd_neighbors = _BfsNeighborExpander(individuals, families)
    while fwd_q:
        _check_cancelled(cancel_event)
        curr, dist = fwd_q.popleft()
        if dist >= half:
            continue
        for nbr, edge in fwd_neighbors(curr):
            _check_cancelled(cancel_event)
            if nbr not in fwd_pred:
                fwd_pred[nbr] = (curr, edge)
                fwd_q.append((nbr, dist + 1))

    # Reverse BFS from end_id: pred[node] = (prev_node, edge_label)
    rev_pred = {end_id: None}
    rev_q = deque([(end_id, 0)])
    rev_neighbors = _BfsNeighborExpander(individuals, families)
    while rev_q:
        _check_cancelled(cancel_event)
        curr, dist = rev_q.popleft()
        if dist >= half:
            continue
        for nbr, edge in rev_neighbors(curr):
            _check_cancelled(cancel_event)
            if nbr not in rev_pred:
                rev_pred[nbr] = (curr, edge)
                rev_q.append((nbr, dist + 1))

    results = []
    seen_bridges = set()  # avoid re-processing the same (X, Y) spouse pair

    for x_id in list(fwd_pred.keys()):
        _check_cancelled(cancel_event)
        if x_id in (start_id, end_id):
            continue
        x_indi = individuals.get(x_id)
        if not x_indi:
            continue
        for fam_id in x_indi.get('fams', []):
            fam = families.get(fam_id)
            if not fam:
                continue
            for y_id in (fam.get('husb'), fam.get('wife')):
                _check_cancelled(cancel_event)
                if not y_id or y_id == x_id:
                    continue
                if y_id not in rev_pred:
                    continue
                if y_id in (start_id, end_id):
                    continue
                bridge = (min(x_id, y_id), max(x_id, y_id))
                if bridge in seen_bridges:
                    continue
                seen_bridges.add(bridge)

                # Reconstruct start→X path from BFS predecessor map
                fwd_path = []
                node = x_id
                while node is not None:
                    pred = fwd_pred.get(node)
                    if pred is None:
                        fwd_path.append((node, None))
                        break
                    fwd_path.append((node, pred[1]))
                    node = pred[0]
                fwd_path.reverse()

                # Reconstruct Y→end path by following rev_pred and reversing edges
                rev_chain = []
                node = y_id
                while True:
                    pred = rev_pred.get(node)
                    if pred is None:
                        break  # reached end_id
                    next_node, rev_edge = pred
                    next_sex = individuals.get(next_node, {}).get('sex', '')
                    fwd_edge = _reverse_edge_for_path(rev_edge, next_sex)
                    rev_chain.append((next_node, fwd_edge))
                    node = next_node

                # Check total path length
                total_edges = (len(fwd_path) - 1) + 1 + len(rev_chain)
                if total_edges > max_depth:
                    continue

                # Reject paths with overlapping nodes between the two sub-paths
                fwd_nodes = {nid for nid, _ in fwd_path}
                rev_nodes = {nid for nid, _ in rev_chain}
                if y_id in fwd_nodes or x_id in rev_nodes or (fwd_nodes & rev_nodes):
                    continue

                full_path = fwd_path + [(y_id, 'spouse')] + rev_chain
                label = _describe_rel(full_path, individuals,
                                      ancestors=start_ancestors,
                                      descendants=descendants,
                                      families=families)
                sig = _path_kinship_signature(full_path)
                if label not in found_labels and sig not in found_sigs:
                    found_labels.add(label)
                    found_sigs.add(sig)
                    results.append(full_path)
                    if len(results) >= slots:
                        return results

    return results


def bfs_find_all_paths(start_id, end_id, individuals, families, top_n=5,
                       max_depth=50, cancel_event=None):
    """Find up to top_n distinct paths between start and end.

    Phase 1: standard BFS to find the shortest distance.
    Phase 2: A*-style path search bounded to shortest_distance + 4 edges.

    Returns (paths, truncated) where paths is a list of path lists and
    truncated is True when the exploration cap was hit before finishing.
    """
    top_n = _positive_int(top_n, "top_n")
    max_depth = _positive_int(max_depth, "max_depth")

    if start_id not in individuals or end_id not in individuals:
        return [], False
    if start_id == end_id:
        return [[(start_id, None)]], False

    # Phase 1: find shortest distance
    seen = {start_id}
    q1 = deque([(start_id, 0)])
    shortest = None
    phase1_neighbors = _BfsNeighborExpander(individuals, families)
    while q1 and shortest is None:
        _check_cancelled(cancel_event)
        curr, dist = q1.popleft()
        if dist >= max_depth:
            continue
        for nbr, _ in phase1_neighbors(curr):
            _check_cancelled(cancel_event)
            if nbr == end_id:
                shortest = dist + 1
                break
            if nbr not in seen:
                seen.add(nbr)
                q1.append((nbr, dist + 1))

    if shortest is None:
        return [], False

    DELTA = max(8, shortest)
    length_limit = min(shortest + DELTA, max_depth)

    # Phase 1.5: reverse BFS from end_id to build a distance-to-end map for pruning
    dist_to_end = {end_id: 0}
    q_rev = deque([(end_id, 0)])
    reverse_neighbors = _BfsNeighborExpander(individuals, families)
    while q_rev:
        _check_cancelled(cancel_event)
        curr, dist = q_rev.popleft()
        if dist >= length_limit:
            continue
        for nbr, _ in reverse_neighbors(curr):
            _check_cancelled(cancel_event)
            if nbr not in dist_to_end:
                dist_to_end[nbr] = dist + 1
                q_rev.append((nbr, dist + 1))

    # Precompute start's biological ancestors/descendants for describe_relationship
    _start_ancestors = _get_ancestor_depths(start_id, individuals, families)
    _start_descendants = _get_descendant_depths(start_id, individuals, families)
    _relationship_families = _prepare_family_lookup(families)

    # Phase 2: A*-style path search
    MAX_EXPLORE = 500_000

    found = []
    found_labels = set()
    found_sigs = set()
    explored = 0
    truncated = False
    _seq = 0

    h0 = dist_to_end.get(start_id, length_limit + 1)
    heap = [(h0, _seq, start_id, ((start_id, None),))]
    path_neighbors = _NeighborCache(individuals, families)

    # Oversample: collect more raw paths than top_n so _filter_spouse_detours
    # has enough candidates to prune from.  Without this, A* stops at top_n,
    # filter removes some as structural detours, and we end up with fewer paths
    # than the user requested.  The extra budget is trimmed back to top_n after
    # filtering and spouse expansion.
    _raw_n = top_n + 12

    # Cache labels as paths are found so the sort step reuses them rather than
    # recomputing.  Keys are id(path_list) which stays stable because
    # _filter_spouse_detours returns the same list objects (not copies).
    _label_cache = {}

    def _add_path(path_list, label, sig):
        found_labels.add(label)
        found_sigs.add(sig)
        found.append(path_list)
        _label_cache[id(path_list)] = label

    while heap and len(found) < _raw_n:
        _check_cancelled(cancel_event)
        if explored >= MAX_EXPLORE:
            truncated = True
            break
        _, _, current_id, path = heapq.heappop(heap)
        explored += 1

        g = len(path) - 1
        path_visited = {nid for nid, _ in path}
        for neighbor_id, edge_label in path_neighbors(current_id):
            _check_cancelled(cancel_event)
            if neighbor_id in path_visited:
                continue
            h = dist_to_end.get(neighbor_id, length_limit + 1)
            new_g = g + 1
            if new_g + h > length_limit:
                continue
            new_path = path + ((neighbor_id, edge_label),)
            if neighbor_id == end_id:
                new_path_list = list(new_path)
                label = _describe_rel(new_path_list, individuals,
                                      ancestors=_start_ancestors,
                                      descendants=_start_descendants,
                                      families=_relationship_families)
                sig = _path_kinship_signature(new_path_list)
                if label not in found_labels and sig not in found_sigs:
                    _add_path(new_path_list, label, sig)
            else:
                _seq += 1
                heapq.heappush(heap, (new_g + h, _seq, neighbor_id, new_path))

    # Filter detours from the A* results before checking the count.
    found = _filter_spouse_detours(found)

    # Targeted spouse expansion: after filtering, if we still need more paths,
    # BFS to each spouse of end_id (excluding end_id itself to avoid routing
    # through the target) and add the spouse-hop path when it has a new label.
    if len(found) < top_n:
        end_ind = individuals.get(end_id, {})
        for fam_id in end_ind.get('fams', []):
            if len(found) >= top_n:
                break
            fam = families.get(fam_id, {})
            if not fam:
                continue
            for spouse_id in (fam.get('husb'), fam.get('wife')):
                _check_cancelled(cancel_event)
                if not spouse_id or spouse_id == end_id:
                    continue
                if len(found) >= top_n:
                    break
                spouse_path = _find_shortest_path(
                    start_id, spouse_id, individuals, families, max_depth - 1,
                    exclude={end_id}, cancel_event=cancel_event)
                if spouse_path is None:
                    continue
                full_path = spouse_path + [(end_id, 'spouse')]
                label = _describe_rel(full_path, individuals,
                                      ancestors=_start_ancestors,
                                      descendants=_start_descendants,
                                      families=_relationship_families)
                sig = _path_kinship_signature(full_path)
                if label not in found_labels and sig not in found_sigs:
                    _add_path(full_path, label, sig)

    # Symmetric spouse expansion: also expand spouses of start_id.  This
    # handles cases like "Randi → Michael (spouse) → Matt (4th cousin)" which
    # the end_id expansion above would miss when Matt has no spouse.
    if len(found) < top_n:
        start_ind = individuals.get(start_id, {})
        for fam_id in start_ind.get('fams', []):
            if len(found) >= top_n:
                break
            fam = families.get(fam_id, {})
            if not fam:
                continue
            for spouse_id in (fam.get('husb'), fam.get('wife')):
                _check_cancelled(cancel_event)
                if not spouse_id or spouse_id == start_id:
                    continue
                if len(found) >= top_n:
                    break
                spouse_path = _find_shortest_path(
                    spouse_id, end_id, individuals, families, max_depth - 1,
                    exclude={start_id}, cancel_event=cancel_event)
                if spouse_path is None:
                    continue
                full_path = [(start_id, None), (spouse_id, 'spouse')] + spouse_path[1:]
                label = _describe_rel(full_path, individuals,
                                      ancestors=_start_ancestors,
                                      descendants=_start_descendants,
                                      families=_relationship_families)
                sig = _path_kinship_signature(full_path)
                if label not in found_labels and sig not in found_sigs:
                    _add_path(full_path, label, sig)

    # Marriage bridge expansion: find paths where X (near start) is married to Y
    # (near end), composing two BFS sub-paths joined by a spouse edge.  This
    # discovers compound relationships like "first cousin once removed-in-law's
    # first cousin once removed" that require more hops than DELTA allows for A*.
    if len(found) < top_n:
        bridge_paths = _marriage_bridge_expansion(
            start_id, end_id, individuals, _relationship_families, max_depth,
            found_labels, found_sigs, _start_ancestors, top_n - len(found),
            descendants=_start_descendants, cancel_event=cancel_event)
        for bp in bridge_paths:
            lbl = _describe_rel(bp, individuals,
                                ancestors=_start_ancestors,
                                descendants=_start_descendants,
                                families=_relationship_families)
            _label_cache[id(bp)] = lbl
        found.extend(bridge_paths)

    # Sort paths by relationship directness: fewer possessive chains first,
    # then by total word count, then by label length.  Reuse cached labels
    # where available; only recompute for paths that slipped through uncached.
    if len(found) > 1:
        def _label_key(path):
            lbl = _label_cache.get(id(path))
            if lbl is None:
                lbl = _describe_rel(path, individuals,
                                    ancestors=_start_ancestors,
                                    descendants=_start_descendants,
                                    families=_relationship_families)
            return lbl.count("'s "), len(lbl.split()), len(lbl)
        found.sort(key=_label_key)

    # Trim to the requested top_n (oversampled A* may have kept more after filtering)
    found = found[:top_n]

    return found, truncated
