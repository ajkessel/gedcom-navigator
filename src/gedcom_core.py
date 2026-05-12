#!/usr/bin/env python3
"""
gedcom_core.py

Shared GEDCOM parsing and BFS engine used by both the CLI and GUI scripts.
Do not import from either script here — this module must remain dependency-free.
"""

import heapq
import re
import tempfile
import zipfile
from collections import deque


# Captures: level, optional xref (@…@), tag (non-space), optional value (rest)
LINE_RE = re.compile(r'^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s+(.*?))?\s*$')

ZIP_MAX_BYTES = 500_000_000  # 500 MB

# Maps GEDCOM CHAR values to Python codec names.
_GEDCOM_ENCODINGS = {
    'UTF-8': 'utf-8-sig',
    'UNICODE': 'utf-16',
    'ANSI': 'cp1252',
    'WINDOWS-1252': 'cp1252',
    'CP1252': 'cp1252',
    'ANSEL': 'latin-1',   # ANSEL is a superset of Latin-1; best approximation
    'ASCII': 'latin-1',   # ASCII files sometimes contain Latin-1 bytes in practice
    'LATIN1': 'latin-1',
    'ISO-8859-1': 'latin-1',
    'MACINTOSH': 'mac_roman',
}


def _detect_encoding(path):
    """Peek at the GEDCOM HEAD record to find the CHAR tag encoding.

    Returns a Python codec name. Falls back to 'utf-8-sig' if unrecognised or absent.
    """
    try:
        with open(path, 'rb') as f:
            raw = f.read(4096)
        # Handle BOM-marked UTF-16
        if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            return 'utf-16'
        # Decode enough of the header as Latin-1 (safe for any single-byte file)
        snippet = raw.decode('latin-1', errors='replace')
        for line in snippet.splitlines():
            m = re.match(r'^\s*1\s+CHAR\s+(\S+)', line, re.IGNORECASE)
            if m:
                key = m.group(1).upper()
                return _GEDCOM_ENCODINGS.get(key, 'utf-8-sig')
    except OSError:
        pass
    return 'utf-8-sig'


def _iter_lines(path, encoding):
    """Open *path* with *encoding* (strict), yielding rstripped lines."""
    with open(path, 'r', encoding=encoding, errors='replace') as f:
        for raw in f:
            yield raw.rstrip('\r\n')


def iter_records(path):
    """Yield each top-level GEDCOM record as a list of (level, xref, tag, value)."""
    encoding = _detect_encoding(path)
    record = []
    for line in _iter_lines(path, encoding):
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        level = int(m.group(1))
        xref = m.group(2)
        tag = m.group(3)
        value = m.group(4) or ''
        if level == 0 and record:
            yield record
            record = []
        record.append((level, xref, tag, value))
    if record:
        yield record


def iter_records_checked(path):
    """Parse GEDCOM, returning (records, warning_or_none).

    Detects the encoding from the GEDCOM CHAR header tag and re-reads with
    that codec.  Warning is non-None only when replacement characters still
    appear after applying the declared encoding.
    """
    encoding = _detect_encoding(path)
    records = []
    record = []
    replacement_lines = 0
    for line in _iter_lines(path, encoding):
        if '�' in line:
            replacement_lines += 1
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        level = int(m.group(1))
        xref = m.group(2)
        tag = m.group(3)
        value = m.group(4) or ''
        if level == 0 and record:
            records.append(record)
            record = []
        record.append((level, xref, tag, value))
    if record:
        records.append(record)

    warning = None
    if replacement_lines:
        warning = (
            f"Warning: {replacement_lines} line(s) contained characters that "
            f"could not be decoded as {encoding} and were replaced with •. "
            f"Some names or dates may be incorrect."
        )
    return records, warning


def extract_year(date_str):
    """Extract a 3- or 4-digit year from a date string."""
    m = re.search(r'\b(\d{3,4})\b', date_str or '')
    return int(m.group(1)) if m else None


def build_model(gedcom_path, dna_keyword, page_marker):
    """Parse the GEDCOM and return (individuals, families, tag_records, encoding_warning).

    individuals[id] = {
        id, name, sex, famc[], fams[], dna_markers[],
        birth_year, death_year, _raw
    }
    families[id]    = {id, husb, wife, chil[]}
    tag_records[id] = name string (from the NAME subrecord of an _MTTAG record)
    encoding_warning = string or None
    """
    records, encoding_warning = iter_records_checked(gedcom_path)

    individuals = {}
    families = {}
    tag_records = {}

    # Pass 1: collect _MTTAG definitions so we can later resolve references.
    for rec in records:
        head_level, head_xref, head_tag, _ = rec[0]
        if head_level != 0 or head_xref is None:
            continue
        if head_tag == '_MTTAG':
            tag_name = ''
            for level, _xref, tag, value in rec[1:]:
                if level == 1 and tag == 'NAME' and not tag_name:
                    tag_name = value.strip()
            tag_records[head_xref] = tag_name

    page_marker_l = page_marker.lower()

    # Pass 2: individuals and families
    for rec in records:
        head_level, head_xref, head_tag, _ = rec[0]
        if head_level != 0 or head_xref is None:
            continue

        if head_tag == 'INDI':
            indi = {
                'id': head_xref,
                'name': '',
                'surname': '',
                'given_name': '',
                'alt_names': [],
                'sex': '',
                'famc': [],
                'fams': [],
                'dna_markers': [],
                'birth_year': None,
                'death_year': None,
                '_mttag_refs': [],
                '_raw': rec,
            }

            n = len(rec)
            for i, (level, _xref, tag, value) in enumerate(rec):
                if i == 0:
                    continue

                if level == 1 and tag == 'NAME':
                    cleaned = value.replace('/', '').strip()
                    if not indi['name']:
                        indi['name'] = cleaned
                        slash_start = value.find('/')
                        slash_end = value.rfind('/')
                        if slash_start != -1 and slash_end > slash_start:
                            indi['surname'] = value[slash_start +
                                                    1:slash_end].strip()
                            indi['given_name'] = value[:slash_start].strip()
                        else:
                            indi['given_name'] = cleaned
                    if cleaned:
                        indi['alt_names'].append(cleaned)
                elif level == 1 and tag == 'SEX':
                    indi['sex'] = value.strip()
                elif level == 1 and tag == 'FAMC':
                    indi['famc'].append(value.strip())
                elif level == 1 and tag == 'FAMS':
                    indi['fams'].append(value.strip())
                elif level == 1 and tag == '_MTTAG':
                    v = value.strip()
                    if v.startswith('@') and v.endswith('@'):
                        indi['_mttag_refs'].append(v)
                    else:
                        # Inline form: 1 _MTTAG / 2 NAME DNA Match
                        for j in range(i + 1, n):
                            l2, _, t2, v2 = rec[j]
                            if l2 <= 1:
                                break
                            if l2 == 2 and t2 == 'NAME':
                                if dna_keyword.lower() in v2.lower():
                                    indi['dna_markers'].append(
                                        f'_MTTAG (inline): {v2.strip()}'
                                    )
                                break
                elif level == 1 and tag in ('BIRT', 'DEAT'):
                    for j in range(i + 1, n):
                        l2, _, t2, v2 = rec[j]
                        if l2 <= 1:
                            break
                        if l2 == 2 and t2 == 'DATE':
                            year = extract_year(v2)
                            if year:
                                if tag == 'BIRT':
                                    indi['birth_year'] = year
                                else:
                                    indi['death_year'] = year
                            break
                elif tag == 'PAGE' and page_marker_l and page_marker_l in value.lower():
                    indi['dna_markers'].append(
                        f'Source citation: "{value.strip()}"'
                    )

            individuals[head_xref] = indi

        elif head_tag == 'FAM':
            fam = {'id': head_xref, 'husb': None, 'wife': None, 'chil': [],
                   'marr_date': '', 'marr_place': ''}
            n = len(rec)
            for i, (level, _xref, tag, value) in enumerate(rec):
                if i == 0:
                    continue
                if level == 1 and tag == 'HUSB':
                    fam['husb'] = value.strip()
                elif level == 1 and tag == 'WIFE':
                    fam['wife'] = value.strip()
                elif level == 1 and tag == 'CHIL':
                    fam['chil'].append(value.strip())
                elif level == 1 and tag == 'MARR':
                    for j in range(i + 1, n):
                        l2, _, t2, v2 = rec[j]
                        if l2 <= 1:
                            break
                        if l2 == 2 and t2 == 'DATE' and not fam['marr_date']:
                            fam['marr_date'] = v2.strip()
                        elif l2 == 2 and t2 == 'PLAC' and not fam['marr_place']:
                            fam['marr_place'] = v2.strip()
            families[head_xref] = fam

    # Pass 3: resolve _MTTAG pointer references against the tag dictionary
    dna_kw_l = dna_keyword.lower()
    for indi in individuals.values():
        for ref in indi.pop('_mttag_refs'):
            tag_name = tag_records.get(ref, '')
            if tag_name and dna_kw_l in tag_name.lower():
                indi['dna_markers'].append(
                    f'Tag: {tag_name} ({ref})'
                )

    return individuals, families, tag_records, encoding_warning


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


def bfs_find_dna_matches(start_id, individuals, families, top_n, max_depth):
    """Return a list of (distance, path) for the nearest DNA-flagged people.

    The BFS continues through DNA-flagged nodes, so a flagged person
    a few hops past another flagged person can still be discovered.
    """
    if start_id not in individuals:
        return []

    # predecessor[node] = (predecessor_id, edge_label_into_node)
    predecessor = {start_id: None}
    queue = deque([(start_id, 0)])
    found = []

    while queue:
        current_id, dist = queue.popleft()
        if dist >= max_depth:
            continue
        for neighbor_id, edge_label in neighbors(current_id, individuals, families):
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


def lifespan(indi):
    """Return a string representing the individual's lifespan."""
    b, d = indi.get('birth_year'), indi.get('death_year')
    if b and d:
        return f'{b}-{d}'
    if b:
        return f'b. {b}'
    if d:
        return f'd. {d}'
    return ''


def describe(indi, show_id=True):
    """Return a string describing the individual, including their name, lifespan, and ID."""
    name = indi['name'] or '(unknown)'
    span = lifespan(indi)
    if show_id:
        return f'{name} ({span}) [{indi["id"]}]' if span else f'{name} [{indi["id"]}]'
    return f'{name} ({span})' if span else name


def _is_spouse_detour_of(longer, shorter):
    """Return True if `longer` is `shorter` with one or more spouse-detour nodes inserted."""
    shorter_ids = {nid for nid, _ in shorter}
    shorter_list = [nid for nid, _ in shorter]
    if longer[0][0] != shorter_list[0] or longer[-1][0] != shorter_list[-1]:
        return False
    if len(longer) <= len(shorter):
        return False
    filtered = []
    i = 0
    while i < len(longer):
        nid, _ = longer[i]
        if nid in shorter_ids:
            filtered.append(nid)
            i += 1
        elif (i + 1 < len(longer)
              and longer[i + 1][1] == 'spouse'
              and longer[i + 1][0] in shorter_ids):
            i += 1
        else:
            return False
    return filtered == shorter_list


def _filter_spouse_detours(paths):
    """Remove paths that are spouse-detour variants of a shorter path in the same list."""
    if len(paths) <= 1:
        return paths
    paths = sorted(paths, key=len)
    kept = [paths[0]]
    for candidate in paths[1:]:
        if not any(_is_spouse_detour_of(candidate, keeper) for keeper in kept):
            kept.append(candidate)
    return kept


def bfs_find_all_paths(start_id, end_id, individuals, families, top_n=5, max_depth=50):
    """Find up to top_n distinct paths between start and end.

    Phase 1: standard BFS to find the shortest distance.
    Phase 2: A*-style path search bounded to shortest_distance + 4 edges.

    Returns (paths, truncated) where paths is a list of path lists and
    truncated is True when the exploration cap was hit before finishing.
    """
    if start_id not in individuals or end_id not in individuals:
        return [], False
    if start_id == end_id:
        return [[(start_id, None)]], False

    # Phase 1: find shortest distance
    seen = {start_id}
    q1 = deque([(start_id, 0)])
    shortest = None
    while q1 and shortest is None:
        curr, dist = q1.popleft()
        if dist >= max_depth:
            continue
        for nbr, _ in neighbors(curr, individuals, families):
            if nbr == end_id:
                shortest = dist + 1
                break
            if nbr not in seen:
                seen.add(nbr)
                q1.append((nbr, dist + 1))

    if shortest is None:
        return [], False

    DELTA = 4
    length_limit = min(shortest + DELTA, max_depth)

    # Phase 1.5: reverse BFS from end_id to build a distance-to-end map for pruning
    dist_to_end = {end_id: 0}
    q_rev = deque([(end_id, 0)])
    while q_rev:
        curr, dist = q_rev.popleft()
        if dist >= length_limit:
            continue
        for nbr, _ in neighbors(curr, individuals, families):
            if nbr not in dist_to_end:
                dist_to_end[nbr] = dist + 1
                q_rev.append((nbr, dist + 1))

    # Phase 2: A*-style path search
    MAX_EXPLORE = 100_000

    found = []
    explored = 0
    truncated = False
    _seq = 0

    h0 = dist_to_end.get(start_id, length_limit + 1)
    heap = [(h0, _seq, start_id, ((start_id, None),))]

    while heap and len(found) < top_n:
        if explored >= MAX_EXPLORE:
            truncated = True
            break
        _, _, current_id, path = heapq.heappop(heap)
        explored += 1

        g = len(path) - 1
        path_visited = {nid for nid, _ in path}
        for neighbor_id, edge_label in neighbors(current_id, individuals, families):
            if neighbor_id in path_visited:
                continue
            h = dist_to_end.get(neighbor_id, length_limit + 1)
            new_g = g + 1
            if new_g + h > length_limit:
                continue
            new_path = path + ((neighbor_id, edge_label),)
            if neighbor_id == end_id:
                found.append(list(new_path))
            else:
                _seq += 1
                heapq.heappush(heap, (new_g + h, _seq, neighbor_id, new_path))

    found = _filter_spouse_detours(found)
    return found, truncated


def extract_ged_from_zip(zip_path):
    """Return (temp_ged_path, entry_name) for the first .ged/.gedcom in a ZIP.

    Prefers top-level entries over those inside subdirectories.
    Caller is responsible for deleting the returned temp file.
    """
    with zipfile.ZipFile(zip_path, 'r') as zf:
        ged_names = sorted(
            [n for n in zf.namelist() if n.lower().endswith(('.ged', '.gedcom'))],
            key=lambda n: (n.count('/'), n.lower()),
        )
        if not ged_names:
            raise ValueError(
                "No .ged or .gedcom file found inside the ZIP archive.")
        chosen = ged_names[0]
        info = zf.getinfo(chosen)
        if info.file_size > ZIP_MAX_BYTES:
            raise ValueError(
                f"'{chosen}' claims {info.file_size / 1e6:.0f} MB uncompressed, "
                f"exceeding the {ZIP_MAX_BYTES / 1e6:.0f} MB limit."
            )
        data = zf.read(chosen)
    tmp = tempfile.NamedTemporaryFile(suffix='.ged', delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name, chosen
