#!/usr/bin/env python3
# cspell:ignore smth
"""
gedcom_dna_finder_cli.py

Given a GEDCOM file and a target person, find the closest relative(s)
who are flagged as DNA matches.

Two DNA-flag signals are detected (either is sufficient):

  1. A source-citation PAGE line whose text contains "AncestryDNA Match"
     (the format Ancestry uses when you tag a person as a DNA match in
     an Ancestry-managed tree, e.g.
       2 PAGE AncestryDNA Match to James Q. Smith
     attached at any depth under the individual's record).

  2. An _MTTAG line whose value is a pointer to a tag-record whose NAME
     field matches a configurable keyword (default: "DNA"), e.g.
       1 _MTTAG @T182059@
     where the tag record at top level is something like
       0 @T182059@ _MTTAG
       1 NAME DNA Match

Use --list-tags first to see all tag definitions in your file, and
--list-flagged to see every flagged individual. Then run a normal query.

Pure stdlib; no external dependencies.

Usage examples:

  # Inspect all tag definitions present in your GEDCOM
  python gedcom_dna_finder_cli.py tree.ged --list-tags

  # List every DNA-flagged person
  python gedcom_dna_finder_cli.py tree.ged --list-flagged

  # Find the 3 nearest DNA-flagged relatives of a person, by name
  python gedcom_dna_finder_cli.py tree.ged "John A Smith"

  # Names are tokenized: this matches "John Adam Smith"
  # without needing the middle name.
  python gedcom_dna_finder_cli.py tree.ged "John Smith"

  # Find by exact INDI ID (with or without surrounding @)
  python gedcom_dna_finder_cli.py tree.ged @I1234@
  python gedcom_dna_finder_cli.py tree.ged I1234

  # Tighten the tag filter to "DNA Match" only (exclude DNA Connection etc.)
  python gedcom_dna_finder_cli.py tree.ged "John Smith" --tag-keyword "DNA Match"

  # Fuzzy match (tolerates typos and spelling variants):
  # "John Smth" will still find "John Adam Smith".
  python gedcom_dna_finder_cli.py tree.ged "John Smith" --fuzzy
  python gedcom_dna_finder_cli.py tree.ged "John Smith" --fuzzy --fuzzy-threshold 0.7
"""

import argparse
import difflib
import os
import re
import sys

from gedcom_core import (
    build_model,
    bfs_find_dna_matches,
    describe,
    extract_ged_from_zip,
)


# ---------------------------------------------------------------------------
# Lookup and output
# ---------------------------------------------------------------------------

def find_target(individuals, query, fuzzy=False, fuzzy_threshold=0.6, fuzzy_max=30):
    """Return a ranked list of (indi_id, score) candidates for `query`.

    Score is None for exact-intent matches (INDI ID lookup or token match).
    Score is a float in [0, 1] for fuzzy matches (only present when
    `fuzzy=True`). Token matches are listed first, then fuzzy matches by
    descending score.

    Name matching is whitespace-tokenized and order-independent: the query
    "John Smith" matches "John Adam Smith", and so does
    "smith john". Each token is a case-insensitive substring match,
    so partial tokens like "Smith" also work.
    """
    q = query.strip()

    # Direct INDI ID lookups (unaffected by tokenization or fuzzy).
    if q.startswith('@') and q.endswith('@'):
        return [(q, None)] if q in individuals else []
    if re.fullmatch(r'[A-Za-z]+\d+', q):
        candidate = f'@{q}@'
        if candidate in individuals:
            return [(candidate, None)]

    q_lower = q.lower()
    tokens = q_lower.split()
    if not tokens:
        return []

    # Token match: every whitespace-separated token must appear (as a
    # substring) somewhere in at least one of the person's names, in any order.
    def _token_match(indi):
        names = indi['alt_names'] or [indi['name']]
        return any(all(tok in name.lower() for tok in tokens) for name in names)

    token_matches = [iid for iid, indi in individuals.items()
                     if _token_match(indi)]
    token_matches.sort(key=lambda iid: individuals[iid]['name'].lower())

    if not fuzzy:
        return [(iid, None) for iid in token_matches]

    # Fuzzy: add anything similar enough that wasn't already a token match.
    # SequenceMatcher with seq2 set once is faster (it caches b2j on seq2).
    token_match_set = set(token_matches)
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(q_lower)
    fuzzy_candidates = []
    for iid, indi in individuals.items():
        if iid in token_match_set:
            continue
        names = indi['alt_names'] or ([indi['name']] if indi['name'] else [])
        if not names:
            continue
        best_score = 0.0
        for name in names:
            matcher.set_seq1(name.lower())
            if matcher.quick_ratio() < fuzzy_threshold:
                continue
            score = matcher.ratio()
            if score > best_score:
                best_score = score
        if best_score >= fuzzy_threshold:
            fuzzy_candidates.append((best_score, iid))

    fuzzy_candidates.sort(
        key=lambda x: (-x[0], individuals[x[1]]['name'].lower()))
    fuzzy_candidates = fuzzy_candidates[:fuzzy_max]

    result = [(iid, None) for iid in token_matches]
    result.extend((iid, score) for score, iid in fuzzy_candidates)
    return result


def print_result(start_id, individuals, results):
    """Print the results of a DNA match search."""
    start = individuals[start_id]
    print()
    print(f'Starting from: {describe(start)}')
    if start['dna_markers']:
        print('  Note: this person is themselves DNA-flagged.')
        for m in start['dna_markers']:
            print(f'    - {m}')
    print()
    if not results:
        print('No DNA-flagged relatives found within the search depth.')
        return
    for rank, (dist, path) in enumerate(results, 1):
        end_id = path[-1][0]
        end = individuals[end_id]
        print(f'#{rank}: {describe(end)}    (distance: {dist} edges)')
        print('   DNA markers:')
        for m in end['dna_markers']:
            print(f'     - {m}')
        print('   Path:')
        for i, (node_id, edge) in enumerate(path):
            indi = individuals[node_id]
            if i == 0:
                print(f'     {describe(indi)}')
            else:
                print(f'       --[{edge}]--> {describe(indi)}')
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Parse command-line options and execute the DNA finder."""
    parser = argparse.ArgumentParser(
        description='Find the nearest DNA-flagged relative(s) to a target person in a GEDCOM tree.'
    )
    parser.add_argument('gedcom', help='Path to the GEDCOM file (.ged).')
    parser.add_argument('target', help='Target: INDI ID (e.g. @I123@ or I123) or a name. '
                                       'Names are matched by whitespace-separated tokens, '
                                       'each as a case-insensitive substring, in any order — '
                                       'so "John Smith" matches "John Adam Smith". '
                                       'Use "_" as a placeholder when combined with '
                                       '--list-tags or --list-flagged.')
    parser.add_argument('--top', type=int, default=3,
                        help='Number of nearest matches to return (default 3).')
    parser.add_argument('--max-depth', type=int, default=50,
                        help='Maximum BFS depth in edges (default 50).')
    parser.add_argument('--page-marker', default='AncestryDNA Match',
                        help='Case-insensitive substring to match in source-citation PAGE text. '
                             'Default: "AncestryDNA Match".')
    parser.add_argument('--tag-keyword', default='DNA',
                        help='Case-insensitive substring to match in _MTTAG NAME values. '
                             'Default: "DNA". '
                             'Use "DNA Match" to exclude DNA Connection / Common DNA Ancestor.')
    parser.add_argument('--fuzzy', action='store_true',
                        help='Enable fuzzy name matching. In addition to token matches, '
                             'include names whose similarity to the query exceeds '
                             '--fuzzy-threshold. Useful for typos and spelling variants.')
    parser.add_argument('--fuzzy-threshold', type=float, default=0.6,
                        help='Similarity cutoff for --fuzzy, between 0.0 and 1.0 (default 0.6). '
                             'Lower = more matches, higher = stricter. '
                             'Uses difflib.SequenceMatcher.ratio.')
    parser.add_argument('--list-tags', action='store_true',
                        help='Print all _MTTAG definitions found in the file and exit.')
    parser.add_argument('--list-flagged', action='store_true',
                        help='Print every individual currently flagged as a DNA match and exit.')
    args = parser.parse_args()

    gedcom_path = args.gedcom
    tmp_path = None
    if gedcom_path.lower().endswith('.zip'):
        try:
            tmp_path, ged_name = extract_ged_from_zip(gedcom_path)
            print(f'Extracted {ged_name!r} from ZIP.', file=sys.stderr)
            gedcom_path = tmp_path
        except Exception as e:  # pylint: disable=broad-except
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)

    print(f'Parsing {args.gedcom} ...', file=sys.stderr)
    try:
        individuals, families, tag_records, encoding_warning = build_model(
            gedcom_path,
            dna_keyword=args.tag_keyword,
            page_marker=args.page_marker,
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if encoding_warning:
        print(encoding_warning, file=sys.stderr)

    print(f'  {len(individuals)} individuals, {len(families)} families, '
          f'{len(tag_records)} _MTTAG definitions', file=sys.stderr)

    flagged = [i for i in individuals.values() if i['dna_markers']]
    print(f'  {len(flagged)} DNA-flagged individuals', file=sys.stderr)

    if args.list_tags:
        if not tag_records:
            print('No _MTTAG records found.')
        else:
            for tid, name in sorted(tag_records.items()):
                print(f'{tid}\t{name}')
        return

    if args.list_flagged:
        for indi in sorted(flagged, key=lambda x: x['name'].lower()):
            print(describe(indi))
            for m in indi['dna_markers']:
                print(f'  - {m}')
        return

    candidates = find_target(
        individuals, args.target,
        fuzzy=args.fuzzy,
        fuzzy_threshold=args.fuzzy_threshold,
    )
    if not candidates:
        msg = f'No individuals match: {args.target!r}'
        if not args.fuzzy:
            msg += '  (try --fuzzy to allow typos and spelling variants)'
        print(msg, file=sys.stderr)
        sys.exit(1)
    if len(candidates) > 1:
        print(f'Multiple candidates match {args.target!r}:', file=sys.stderr)
        for cid, score in candidates[:25]:
            score_str = f'  [fuzzy: {score:.2f}]' if score is not None else ''
            print(
                f'  {describe(individuals[cid])}{score_str}', file=sys.stderr)
        if len(candidates) > 25:
            print(f'  ... and {len(candidates) - 25} more', file=sys.stderr)
        print('Refine the query, or pass an exact INDI ID.', file=sys.stderr)
        sys.exit(1)

    start_id = candidates[0][0]
    results = bfs_find_dna_matches(
        start_id, individuals, families,
        top_n=args.top, max_depth=args.max_depth,
    )
    print_result(start_id, individuals, results)


if __name__ == '__main__':
    main()
