#!/usr/bin/env python3
# cspell:ignore smth
"""
gedcom_navigator_cli.py

Given a GEDCOM file and a target person, find the closest relative(s)
who are flagged as DNA matches.

DNA-flag signals are detected (any is sufficient):

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

  3. For files with no _MTTAG records (i.e. not Ancestry exports), the
     keyword is matched against alternate custom fields produced by other
     genealogy software: custom events/facts/attributes (EVEN/FACT/_ATTR
     with a 2 TYPE child), reference numbers (REFN), and custom
     "_DNA"-style tags. See --detection-fields.

Use --list-tags first to see all tag (or custom-field) definitions in your
file, and --list-flagged to see every flagged individual. Then run a query.

No third-party packages are required. Optional transliteration packages are used
when installed to improve fuzzy matching for some non-Latin names.

Usage examples:

  # Inspect all tag definitions present in your GEDCOM
  python gedcom_navigator_cli.py tree.ged --list-tags

  # List every DNA-flagged person
  python gedcom_navigator_cli.py tree.ged --list-flagged

  # Find the 3 nearest DNA-flagged relatives of a person, by name
  python gedcom_navigator_cli.py tree.ged "John A Smith"

  # Names are tokenized: this matches "John Adam Smith"
  # without needing the middle name.
  python gedcom_navigator_cli.py tree.ged "John Smith"

  # Find by exact INDI ID (with or without surrounding @)
  python gedcom_navigator_cli.py tree.ged @I1234@
  python gedcom_navigator_cli.py tree.ged I1234

  # Tighten the tag filter to "DNA Match" only (exclude DNA Connection etc.)
  python gedcom_navigator_cli.py tree.ged "John Smith" --tag-keyword "DNA Match"

  # Fuzzy match (tolerates typos, spelling variants, and cached Hebrew/Cyrillic
  # transliterated aliases):
  # "John Smth" will still find "John Adam Smith".
  python gedcom_navigator_cli.py tree.ged "John Smith" --fuzzy
  python gedcom_navigator_cli.py tree.ged "John Smith" --fuzzy --fuzzy-threshold 0.7
"""

import argparse
import os
import sys

from gedcom_display import describe
from gedcom_debug import (
    configure_debug_logging,
    debug_enabled,
    install_exception_hooks,
    log_exception,
    set_debug_enabled,
)
from gedcom_name_search import find_candidates
from gedcom_parser import build_model, extract_ged_from_zip
from gedcom_search import bfs_find_dna_matches


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def positive_int(value):
    """argparse type for positive integer options."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def ratio_float(value):
    """argparse type for ratios in the inclusive range 0.0 to 1.0."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be a number between 0.0 and 1.0") from exc
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            "must be a number between 0.0 and 1.0")
    return parsed


# ---------------------------------------------------------------------------
# Lookup and output
# ---------------------------------------------------------------------------

def find_target(individuals, query, fuzzy=False, fuzzy_threshold=0.6, fuzzy_max=30):
    """Return a ranked list of (indi_id, score) candidates for `query`."""
    return find_candidates(
        individuals, query, fuzzy=fuzzy,
        fuzzy_threshold=fuzzy_threshold, fuzzy_max=fuzzy_max)


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
    """Parse command-line options and execute the GEDCOM navigator."""
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
    parser.add_argument('--top', type=positive_int, default=3,
                        help='Number of nearest matches to return (default 3).')
    parser.add_argument('--max-depth', type=positive_int, default=50,
                        help='Maximum BFS depth in edges (default 50).')
    parser.add_argument('--page-marker', default='AncestryDNA Match',
                        help='Case-insensitive substring to match in source-citation PAGE text. '
                             'Default: "AncestryDNA Match".')
    parser.add_argument('--tag-keyword', default='DNA',
                        help='Case-insensitive substring to match in _MTTAG NAME values '
                             '(and, for non-Ancestry files, in alternate custom fields). '
                             'Default: "DNA". '
                             'Use "DNA Match" to exclude DNA Connection / Common DNA Ancestor.')
    parser.add_argument('--detection-fields', default=None,
                        help='Comma-separated alternate fields to scan when the file has '
                             'no _MTTAG records: even,fact,attr,tag,refn,note. '
                             'Default: even,fact,attr,tag,refn (note excluded).')
    parser.add_argument('--fuzzy', action='store_true',
                        help='Enable fuzzy name matching. In addition to token matches, '
                             'include names whose similarity to the query exceeds '
                             '--fuzzy-threshold. Useful for typos, spelling variants, '
                             'and cached Hebrew/Cyrillic transliterated aliases.')
    parser.add_argument('--fuzzy-threshold', type=ratio_float, default=0.6,
                        help='Similarity cutoff for --fuzzy, between 0.0 and 1.0 (default 0.6). '
                             'Lower = more matches, higher = stricter. '
                             'Uses difflib.SequenceMatcher.ratio.')
    parser.add_argument('--list-tags', action='store_true',
                        help='Print all _MTTAG definitions (or, for non-Ancestry files, '
                             'the discovered custom-field catalog) and exit.')
    parser.add_argument('--list-flagged', action='store_true',
                        help='Print every individual currently flagged as a DNA match and exit.')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug diagnostics, including exception logging.')
    args = parser.parse_args()

    if args.debug:
        set_debug_enabled(True)
    if debug_enabled():
        configure_debug_logging()
        install_exception_hooks()

    gedcom_path = args.gedcom
    tmp_path = None
    if gedcom_path.lower().endswith('.zip'):
        try:
            tmp_path, ged_name = extract_ged_from_zip(gedcom_path)
            print(f'Extracted {ged_name!r} from ZIP.', file=sys.stderr)
            gedcom_path = tmp_path
        except Exception as e:  # pylint: disable=broad-except
            log_exception(f"extracting GEDCOM from ZIP: {gedcom_path!r}")
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)

    print(f'Parsing {args.gedcom} ...', file=sys.stderr)
    try:
        (
            individuals,
            families,
            tag_records,
            _media_records,
            encoding_warning,
            model_error,
            uses_alternate_tags,
            custom_field_records,
        ) = build_model(
            gedcom_path,
            dna_keyword=args.tag_keyword,
            page_marker=args.page_marker,
            detection_fields=args.detection_fields,
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if encoding_warning:
        print(encoding_warning, file=sys.stderr)

    if model_error:
        print(f'Error: {model_error}', file=sys.stderr)
        sys.exit(1)

    summary = (f'  {len(individuals)} individuals, {len(families)} families, '
               f'{len(tag_records)} _MTTAG definitions')
    if uses_alternate_tags:
        summary += (f', {len(custom_field_records)} custom field types '
                    '(no _MTTAG; using alternate detection)')
    print(summary, file=sys.stderr)

    flagged = [i for i in individuals.values() if i['dna_markers']]
    print(f'  {len(flagged)} DNA-flagged individuals', file=sys.stderr)

    if args.list_tags:
        if tag_records:
            for tid, name in sorted(tag_records.items()):
                print(f'{tid}\t{name}')
        elif custom_field_records:
            print('No _MTTAG records found; discovered custom fields '
                  '(kind\ttype\tcount):')
            for rec in custom_field_records:
                print(f"{rec['kind']}\t{rec['type']}\t{rec['count']}")
        else:
            print('No _MTTAG records or custom fields found.')
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
            msg += (
                '  (try --fuzzy to allow typos, spelling variants, '
                'and Hebrew/Cyrillic transliterated aliases)'
            )
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
