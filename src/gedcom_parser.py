#!/usr/bin/env python3
"""
gedcom_parser.py

GEDCOM record parsing, model building, encoding detection, and archive extraction.
"""

import re
import os
import tempfile
import zipfile

from gedcom_debug import log_exception
from gedcom_relationship import normalize_parentage
from gedcom_transliteration import add_transliterated_names

# Captures: level, optional xref (@…@), tag (non-space), optional value (rest)
LINE_RE = re.compile(r'^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s+(.*?))?\s*$')

ZIP_MAX_BYTES = 500_000_000  # 500 MB
ZIP_COPY_CHUNK_BYTES = 1024 * 1024

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

    Returns a Python codec name. Falls back to 'utf-8-sig' if unrecognized or absent.
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


# A BCE marker: BC, BCE, B.C., B.C.E. (case-insensitive), optionally spaced.
# The digits immediately preceding the marker are the (1-4 digit) year.
_BCE_RE = re.compile(r'(\d{1,4})\s*B\.?\s*C\.?(?:\s*E\.?)?', re.IGNORECASE)
# Julian/Gregorian dual year, e.g. "1708/9" or "1699/00". The part before the
# slash is the Old Style (Julian) year; the New Style (Gregorian) year is always
# the following calendar year, since dual dates fall in the Jan-Mar overlap.
_DUAL_RE = re.compile(r'\b(\d{3,4})/\d{1,4}\b')
# Plain 3- or 4-digit year.
_YEAR_RE = re.compile(r'\b(\d{3,4})\b')


def extract_year(date_str):
    """Extract a signed year from a GEDCOM date string.

    Returns a positive int for CE/AD years and a *negative* int for BCE years
    (e.g. "44 B.C." -> -44), or None when no year can be found. Julian/Gregorian
    dual years such as "10 JAN 1708/9" resolve to the New Style (later) year.
    """
    s = date_str or ''
    m = _BCE_RE.search(s)
    if m:
        return -int(m.group(1))
    m = _DUAL_RE.search(s)
    if m:
        return int(m.group(1)) + 1
    m = _YEAR_RE.search(s)
    return int(m.group(1)) if m else None


def _record_text(rec, parent_index):
    """Return GEDCOM text continued/concatenated under rec[parent_index]."""
    text = rec[parent_index][3] or ''
    parent_level = rec[parent_index][0]
    for level, _xref, tag, value in rec[parent_index + 1:]:
        if level <= parent_level:
            break
        if level == parent_level + 1 and tag == 'CONC':
            text += value or ''
        elif level == parent_level + 1 and tag == 'CONT':
            text += '\n' + (value or '')
    return text.strip()


def _media_details_from_block(block):
    """Extract FILE/FORM/TITL/_PRIM details from a GEDCOM OBJE-like block."""
    details = {
        'file': '',
        'format': '',
        'title': '',
        'primary': False,
    }
    for i, (_level, _xref, tag, value) in enumerate(block):
        text = (value or '').strip()
        if tag == 'FILE' and not details['file']:
            details['file'] = _record_text(block, i)
        elif tag == 'FORM' and not details['format']:
            details['format'] = text
        elif tag in ('TITL', 'TITLE') and not details['title']:
            details['title'] = _record_text(block, i)
        elif tag == '_PRIM' and text.upper().startswith('Y'):
            details['primary'] = True
    return details


def _top_level_media_record(rec):
    """Return a normalized top-level OBJE media record."""
    media = {'id': rec[0][1], '_raw': rec}
    media.update(_media_details_from_block(rec[1:]))
    return media


def _person_media_candidate(tag, value, block):
    """Return a normalized person-level media candidate."""
    value = (value or '').strip()
    candidate = {
        'kind': tag,
        'ref': '',
        'file': '',
        'format': '',
        'title': '',
        'primary': False,
    }
    if value.startswith('@') and value.endswith('@'):
        candidate['ref'] = value
    elif value:
        candidate['file'] = value
    candidate.update({
        key: val for key, val in _media_details_from_block(block).items()
        if val not in ('', False)
    })
    return candidate


def _candidate_name_matches(candidate, person_name):
    """Return whether candidate title or filename appears to name the person."""
    person_name = (person_name or '').replace('/', ' ').strip().lower()
    if not person_name:
        return False
    haystacks = [
        (candidate.get('title') or '').lower(),
        os.path.splitext(os.path.basename(candidate.get('file') or ''))[0].lower(),
    ]
    compact_person = re.sub(r'\s+', ' ', person_name)
    compact_tokens = set(compact_person.split())
    for hay in haystacks:
        hay = re.sub(r'[_\-\s]+', ' ', hay)
        if compact_person and compact_person in hay:
            return True
        if compact_tokens and compact_tokens.issubset(set(hay.split())):
            return True
    return False


def _merge_media_candidate(candidate, media_records):
    """Merge a candidate with its referenced top-level OBJE record, if any."""
    ref = candidate.get('ref')
    if ref and ref in media_records:
        media = media_records[ref]
        merged = dict(candidate)
        for key in ('file', 'format', 'title', 'primary'):
            if not merged.get(key):
                merged[key] = media.get(key, '' if key != 'primary' else False)
        return merged
    return candidate


def _rank_media_candidates(candidates, person_name, media_records):
    """Return person-level media candidates in profile-photo preference order."""
    ranked = []
    for order, candidate in enumerate(candidates):
        merged = _merge_media_candidate(candidate, media_records)
        name_match = _candidate_name_matches(merged, person_name)
        if merged.get('kind') == '_PHOTO':
            rank = 0
        elif merged.get('primary'):
            rank = 1
        elif name_match:
            rank = 2
        else:
            rank = 3
        merged['name_match'] = name_match
        ranked.append((rank, order, merged))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [candidate for _rank, _order, candidate in ranked]


# Alternate (non-Ancestry) DNA-detection field modes. Used only when a file
# contains no _MTTAG records. NOTE is excluded from the defaults because free
# text frequently mentions "DNA" incidentally (high false-positive rate).
ALTERNATE_FIELD_MODES = ('EVEN', 'FACT', '_ATTR', '_TAG', 'REFN', 'NOTE')
DEFAULT_ALTERNATE_FIELDS = frozenset({'EVEN', 'FACT', '_ATTR', '_TAG', 'REFN'})

# Accepts both short CLI spellings and canonical tag tokens.
_FIELD_ALIASES = {
    'even': 'EVEN', 'fact': 'FACT', 'attr': '_ATTR', '_attr': '_ATTR',
    'tag': '_TAG', '_tag': '_TAG', 'refn': 'REFN', 'note': 'NOTE',
}


def normalize_detection_fields(value):
    """Return a frozenset of valid alternate-field modes from a list/set/str.

    ``None`` yields the default set. Unknown tokens are ignored. An input that
    resolves to nothing falls back to the default set.
    """
    if value is None:
        return DEFAULT_ALTERNATE_FIELDS
    items = value.split(',') if isinstance(value, str) else value
    out = set()
    for item in items:
        token = _FIELD_ALIASES.get(str(item).strip().lower())
        if token:
            out.add(token)
    return frozenset(out) if out else DEFAULT_ALTERNATE_FIELDS


def _entry_child_type(raw, start, n):
    """Return the level-2 TYPE value under raw[start], or '' if none."""
    for j in range(start + 1, n):
        l2, t2, v2 = raw[j][0], raw[j][2], raw[j][3]
        if l2 <= 1:
            break
        if l2 == 2 and t2 == 'TYPE':
            return v2.strip()
    return ''


def _field_descriptor(type_val, value):
    """Return the human-meaningful label for a custom EVEN/FACT/_ATTR/REFN field.

    Normally the ``2 TYPE`` value is the label. Some software (e.g. MyHeritage)
    writes a generic ``2 TYPE Custom`` and puts the real label in the field value
    instead — ``1 FACT MyHeritage DNA`` / ``2 TYPE Custom`` — so when TYPE is
    empty or the placeholder "Custom" we fall back to the field value.
    """
    t = (type_val or '').strip()
    v = (value or '').strip()
    if t and t.lower() != 'custom':
        return t
    return v or t


def derive_dna_flags(raw, tag_records, *, dna_keyword, page_marker,
                     scan_alternate, alternate_fields):
    """Return (dna_markers, tags) for one individual's _raw record.

    The single source of truth for DNA-flag detection, shared by build_model
    and apply_dna_flags. ``raw`` may hold tuples (fresh parse) or lists (after a
    JSON cache round-trip); entries are read positionally as
    (level, xref, tag, value), only indexing level/tag/value.

    Unconditional rules (every file): inline ``_MTTAG``/``2 NAME``, ``_MTTAG``
    pointer references resolved against ``tag_records``, and ``PAGE`` source
    citations matching ``page_marker``. Alternate rules (custom EVEN/FACT/_ATTR/
    REFN/NOTE and custom ``_DNA``-style tags) run only when ``scan_alternate`` is
    set and the field's mode is present in ``alternate_fields``.
    """
    dna_markers = []
    tags = []
    page_marker_l = (page_marker or '').lower()
    dna_kw_l = (dna_keyword or '').lower()
    fields = alternate_fields or frozenset()
    raw = raw or []
    n = len(raw)
    mttag_refs = []

    for i in range(1, n):
        entry = raw[i]
        level, tag, value = entry[0], entry[2], entry[3]

        # --- Unconditional Ancestry rules ---
        if level == 1 and tag == '_MTTAG':
            v = value.strip()
            if v.startswith('@') and v.endswith('@'):
                mttag_refs.append(v)
            else:
                for j in range(i + 1, n):
                    l2, t2, v2 = raw[j][0], raw[j][2], raw[j][3]
                    if l2 <= 1:
                        break
                    if l2 == 2 and t2 == 'NAME':
                        name_val = v2.strip()
                        tags.append(name_val)
                        if dna_kw_l and dna_kw_l in name_val.lower():
                            dna_markers.append(f'_MTTAG (inline): {name_val}')
                        break
        elif tag == 'PAGE' and page_marker_l and page_marker_l in value.lower():
            dna_markers.append(f'Source citation: "{value.strip()}"')

        # --- Alternate (non-Ancestry) rules, keyword-gated ---
        elif scan_alternate and dna_kw_l and level == 1:
            if tag in ('EVEN', 'FACT', '_ATTR') and tag in fields:
                type_val = _entry_child_type(raw, i, n)
                if dna_kw_l in f'{type_val} {value}'.lower():
                    label = {'EVEN': 'Event', 'FACT': 'Fact',
                             '_ATTR': 'Attribute'}[tag]
                    desc = _field_descriptor(type_val, value)
                    dna_markers.append(f'{label}: {desc}')
                    tags.append(desc)
            elif tag == 'REFN' and 'REFN' in fields:
                type_val = _entry_child_type(raw, i, n)
                if dna_kw_l in f'{type_val} {value}'.lower():
                    desc = _field_descriptor(type_val, value)
                    dna_markers.append(f'Reference: {desc}')
                    tags.append(desc)
            elif tag == 'NOTE' and 'NOTE' in fields:
                if dna_kw_l in value.lower():
                    desc = value.strip()
                    dna_markers.append(f'Note: {desc[:60]}')
                    tags.append(desc)
            elif (tag.startswith('_') and tag != '_MTTAG'
                  and '_TAG' in fields and dna_kw_l in tag.lower()):
                dna_markers.append(f'Custom tag: {tag}')
                tags.append(tag)

    for ref in mttag_refs:
        tag_name = tag_records.get(ref, '')
        if tag_name:
            tags.append(tag_name)
            if dna_kw_l and dna_kw_l in tag_name.lower():
                dna_markers.append(f'Tag: {tag_name} ({ref})')

    return dna_markers, tags


def _discover_custom_fields(records):
    """Catalog non-Ancestry custom field types across all INDI records.

    Returns a sorted list of {'kind', 'type', 'count'} dicts describing distinct
    custom EVEN/FACT/_ATTR/REFN TYPE values and custom ``_``-prefixed level-1
    tags, so the GUI tag browser and CLI --list-tags can show the user what is
    available to match on. NOTE free text is intentionally excluded.
    """
    counts = {}
    for rec in records:
        if not rec:
            continue
        head_level, _head_xref, head_tag, _ = rec[0]
        if head_level != 0 or head_tag != 'INDI':
            continue
        n = len(rec)
        for i in range(1, n):
            level, _x, tag, value = rec[i]
            if level != 1:
                continue
            if tag in ('EVEN', 'FACT', '_ATTR', 'REFN'):
                type_val = _field_descriptor(_entry_child_type(rec, i, n), value)
                key = (tag, type_val)
            elif tag.startswith('_') and tag != '_MTTAG':
                key = ('_TAG', tag)
            else:
                continue
            counts[key] = counts.get(key, 0) + 1
    return [
        {'kind': kind, 'type': type_val, 'count': count}
        for (kind, type_val), count in sorted(counts.items())
    ]


def build_model(gedcom_path, dna_keyword, page_marker, detection_fields=None):
    """Parse the GEDCOM and return model data plus warnings/errors.

    individuals[id] = {
        id, name, sex, famc[], fams[], dna_markers[], tags[],
        birth_year, death_year, _raw
    }
    families[id]    = {id, husb, wife, chil[]}
    tag_records[id] = name string (from the NAME subrecord of an _MTTAG record)
    uses_alternate_tags = True when the file has no _MTTAG records, so DNA
        detection falls back to custom EVEN/FACT/_ATTR/_DNA/REFN fields.
    custom_field_records = discovered non-Ancestry custom field catalog (only
        populated when uses_alternate_tags is True; else an empty list)
    encoding_warning = string or None
    model_error = string or None; non-None when no usable model could be built
    """
    alternate_fields = normalize_detection_fields(detection_fields)
    records, encoding_warning = iter_records_checked(gedcom_path)

    individuals = {}
    families = {}
    tag_records = {}
    media_records = {}

    # Pass 1: collect _MTTAG definitions and top-level OBJE records so we can
    # later resolve references.
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
        elif head_tag == 'OBJE':
            media_records[head_xref] = _top_level_media_record(rec)

    # Files with no _MTTAG records are not Ancestry exports; fall back to
    # scanning alternate custom fields for DNA markers, and catalog the custom
    # field types found so the user can pick which to match on.
    uses_alternate_tags = not tag_records
    custom_field_records = (
        _discover_custom_fields(records) if uses_alternate_tags else [])

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
                'transliterated_names': [],
                'sex': '',
                'famc': [],
                'fams': [],
                '_famc_pedi': {},
                '_adop_famc': [],
                'dna_markers': [],
                'tags': [],
                'birth_year': None,
                'death_year': None,
                'media_candidates': [],
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
                    fam_id = value.strip()
                    indi['famc'].append(fam_id)
                    for j in range(i + 1, n):
                        l2, _, t2, v2 = rec[j]
                        if l2 <= 1:
                            break
                        if l2 == 2 and t2 == 'PEDI':
                            indi['_famc_pedi'][fam_id] = normalize_parentage(v2)
                            break
                elif level == 1 and tag == 'FAMS':
                    indi['fams'].append(value.strip())
                elif level == 1 and tag == 'ADOP':
                    adop_fam_id = ''
                    adop_role = 'BOTH'
                    for j in range(i + 1, n):
                        l2, _, t2, v2 = rec[j]
                        if l2 <= 1:
                            break
                        if l2 == 2 and t2 == 'FAMC':
                            adop_fam_id = v2.strip()
                            for k in range(j + 1, n):
                                l3, _, t3, v3 = rec[k]
                                if l3 <= 2:
                                    break
                                if l3 == 3 and t3 == 'ADOP':
                                    adop_role = v3.strip().upper() or adop_role
                                    break
                        elif l2 == 2 and t2 == 'ADOP':
                            adop_role = v2.strip().upper() or adop_role
                    if adop_fam_id:
                        indi['_adop_famc'].append((adop_fam_id, adop_role))
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
                elif level == 1 and tag in ('OBJE', '_PHOTO'):
                    block = []
                    for j in range(i + 1, n):
                        l2, x2, t2, v2 = rec[j]
                        if l2 <= 1:
                            break
                        block.append((l2, x2, t2, v2))
                    candidate = _person_media_candidate(tag, value, block)
                    if any(
                        candidate.get(key)
                        for key in ('ref', 'file', 'format', 'title', 'primary')
                    ):
                        indi['media_candidates'].append(candidate)

            indi['media_candidates'] = _rank_media_candidates(
                indi['media_candidates'], indi.get('name', ''), media_records)
            individuals[head_xref] = indi

        elif head_tag == 'FAM':
            fam = {'id': head_xref, 'husb': None, 'wife': None, 'chil': [],
                   'child_links': {}, 'marr_date': '', 'marr_place': ''}
            n = len(rec)
            for i, (level, _xref, tag, value) in enumerate(rec):
                if i == 0:
                    continue
                if level == 1 and tag == 'HUSB':
                    fam['husb'] = value.strip()
                elif level == 1 and tag == 'WIFE':
                    fam['wife'] = value.strip()
                elif level == 1 and tag == 'CHIL':
                    child_id = value.strip()
                    fam['chil'].append(child_id)
                    link = fam['child_links'].setdefault(child_id, {})
                    for j in range(i + 1, n):
                        l2, _, t2, v2 = rec[j]
                        if l2 <= 1:
                            break
                        if l2 == 2 and t2 == 'PEDI':
                            link['family'] = normalize_parentage(v2)
                        elif l2 == 2 and t2 == '_FREL':
                            link['father'] = normalize_parentage(v2)
                        elif l2 == 2 and t2 == '_MREL':
                            link['mother'] = normalize_parentage(v2)
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

    # Pass 2.5: merge individual-side family pedigree/adoption metadata into
    # family child links now that all FAM records are available.
    for indi in individuals.values():
        child_id = indi['id']
        for fam_id, parentage in indi.pop('_famc_pedi', {}).items():
            fam = families.get(fam_id)
            if not fam or child_id not in fam.get('chil', ()):
                continue
            fam.setdefault('child_links', {}).setdefault(
                child_id, {})['family'] = parentage
        for fam_id, adop_role in indi.pop('_adop_famc', []):
            fam = families.get(fam_id)
            if not fam or child_id not in fam.get('chil', ()):
                continue
            link = fam.setdefault('child_links', {}).setdefault(child_id, {})
            role = (adop_role or 'BOTH').upper()
            if role in ('HUSB', 'BOTH'):
                link['father'] = 'adopted'
            if role in ('WIFE', 'BOTH'):
                link['mother'] = 'adopted'

    # Pass 3: derive DNA flags via the shared detection path (Ancestry
    # _MTTAG/PAGE plus, for non-Ancestry files, alternate custom fields).
    for indi in individuals.values():
        indi['dna_markers'], indi['tags'] = derive_dna_flags(
            indi['_raw'], tag_records,
            dna_keyword=dna_keyword, page_marker=page_marker,
            scan_alternate=uses_alternate_tags,
            alternate_fields=alternate_fields,
        )

    add_transliterated_names(individuals)

    model_error = None
    if not records:
        model_error = (
            "No GEDCOM records were found in the selected file. "
            "Please choose a valid .ged or .gedcom file."
        )
    elif not any(rec and rec[0][0] == 0 and rec[0][2] == 'HEAD' for rec in records):
        model_error = (
            "The selected file does not look like a valid GEDCOM file "
            "because it is missing a HEAD record."
        )
    elif not individuals:
        model_error = (
            "No individual records were found in the selected GEDCOM file. "
            "The app needs at least one INDI record to build the family model."
        )

    return (individuals, families, tag_records, media_records,
            encoding_warning, model_error,
            uses_alternate_tags, custom_field_records)

def apply_dna_flags(individuals, tag_records, dna_keyword, page_marker,
                    uses_alternate_tags=False, detection_fields=None):
    """Re-populate dna_markers and tags for all individuals from their _raw records.

    Safe to call after a cache load or whenever keywords change — no file I/O,
    only O(N) string comparisons over already-parsed tuples/lists. Delegates to
    derive_dna_flags so detection stays in one place. ``uses_alternate_tags``
    (a per-file property restored from the cache) enables the non-Ancestry
    fallback fields named in ``detection_fields``.
    """
    alternate_fields = (
        normalize_detection_fields(detection_fields)
        if uses_alternate_tags else frozenset())
    for indi in individuals.values():
        indi['dna_markers'], indi['tags'] = derive_dna_flags(
            indi.get('_raw') or [], tag_records,
            dna_keyword=dna_keyword, page_marker=page_marker,
            scan_alternate=uses_alternate_tags,
            alternate_fields=alternate_fields,
        )


def extract_ged_from_zip(zip_path, cancel_event=None):
    """Return (temp_ged_path, entry_name) for the first .ged/.gedcom in a ZIP.

    Prefers top-level entries over those inside subdirectories.
    Caller is responsible for deleting the returned temp file.
    """
    tmp_path = None
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
        try:
            with zf.open(info, 'r') as source:
                with tempfile.NamedTemporaryFile(suffix='.ged', delete=False) as tmp:
                    tmp_path = tmp.name
                    copied = 0
                    while True:
                        if cancel_event is not None and cancel_event.is_set():
                            raise InterruptedError("ZIP extraction canceled.")
                        chunk = source.read(ZIP_COPY_CHUNK_BYTES)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > ZIP_MAX_BYTES:
                            raise ValueError(
                                f"'{chosen}' exceeds the {ZIP_MAX_BYTES / 1e6:.0f} MB "
                                "uncompressed limit."
                            )
                        tmp.write(chunk)
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception(f"extracting GEDCOM from ZIP {zip_path!r}")
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
    return tmp_path, chosen
