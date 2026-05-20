#!/usr/bin/env python3
"""
gedcom_name_search.py

Shared ID, token, and fuzzy name matching for CLI and GUI search surfaces.
"""

import difflib
import re


def individual_names(indi, extra_names=None):
    """Return searchable names for an individual record."""
    names = indi.get('alt_names') or [indi.get('name', '')]
    if extra_names:
        names = list(names) + list(extra_names)
    return [name for name in names if name]


def exact_id_candidate(individuals, query):
    """Return an exact INDI ID match for query, or None."""
    q = query.strip()
    if q.startswith('@') and q.endswith('@'):
        return q if q in individuals else None
    if re.fullmatch(r'[A-Za-z]+\d+', q):
        candidate = f'@{q}@'
        if candidate in individuals:
            return candidate
    return None


def token_match(indi, tokens, extra_names=None):
    """Return whether every token appears in at least one name."""
    if not tokens:
        return False
    return any(
        all(tok in name.lower() for tok in tokens)
        for name in individual_names(indi, extra_names=extra_names)
    )


def id_substring_match(indi_id, query):
    """Return whether query appears in the GEDCOM ID."""
    return bool(query) and query.lower() in indi_id.lower()


def fuzzy_score(indi, query, threshold, extra_names=None):
    """Return the best SequenceMatcher score for query against an individual's names."""
    q_lower = query.strip().lower()
    if not q_lower:
        return None

    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(q_lower)
    best_score = 0.0
    tokens = q_lower.split()

    for name in individual_names(indi, extra_names=extra_names):
        name_lower = name.lower()
        matcher.set_seq1(name_lower)
        if matcher.quick_ratio() >= threshold:
            best_score = max(best_score, matcher.ratio())

        if tokens:
            words = name_lower.split()
            token_scores = []
            for token in tokens:
                token_scores.append(max(
                    difflib.SequenceMatcher(None, token, word).ratio()
                    for word in words
                ) if words else 0.0)
            if token_scores and all(score >= threshold for score in token_scores):
                best_score = max(best_score, min(token_scores))

    return best_score if best_score >= threshold else None


def individual_matches_query(indi_id, indi, query, *, fuzzy=False,
                             fuzzy_threshold=0.6, extra_names=None):
    """Return (matched, score) for one individual against a user query.

    Score is None for exact ID, GEDCOM-ID substring, or token matches.  Score is
    a float for fuzzy matches.
    """
    q_lower = query.strip().lower()
    if not q_lower:
        return True, None
    if id_substring_match(indi_id, q_lower):
        return True, None
    if token_match(indi, q_lower.split(), extra_names=extra_names):
        return True, None
    if fuzzy:
        score = fuzzy_score(
            indi, q_lower, fuzzy_threshold, extra_names=extra_names)
        if score is not None:
            return True, score
    return False, None


def find_candidates(individuals, query, *, fuzzy=False, fuzzy_threshold=0.6,
                    fuzzy_max=30, extra_names_by_id=None):
    """Return ranked (indi_id, score) candidates for query."""
    exact = exact_id_candidate(individuals, query)
    if exact:
        return [(exact, None)]

    q_lower = query.strip().lower()
    if not q_lower:
        return []

    direct_matches = []
    fuzzy_candidates = []
    direct_match_ids = set()
    tokens = q_lower.split()
    extra_names_by_id = extra_names_by_id or {}

    for iid, indi in individuals.items():
        extra_names = extra_names_by_id.get(iid)
        direct = (
            id_substring_match(iid, q_lower)
            or token_match(indi, tokens, extra_names=extra_names)
        )
        if direct:
            direct_matches.append(iid)
            direct_match_ids.add(iid)
        elif fuzzy:
            score = fuzzy_score(
                indi, q_lower, fuzzy_threshold, extra_names=extra_names)
            if score is not None:
                fuzzy_candidates.append((score, iid))

    direct_matches.sort(key=lambda iid: individuals[iid].get('name', '').lower())
    fuzzy_candidates.sort(
        key=lambda x: (-x[0], individuals[x[1]].get('name', '').lower()))
    fuzzy_candidates = fuzzy_candidates[:fuzzy_max]

    result = [(iid, None) for iid in direct_matches]
    result.extend(
        (iid, score) for score, iid in fuzzy_candidates
        if iid not in direct_match_ids
    )
    return result
