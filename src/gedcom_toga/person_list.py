"""Toolkit-free helpers for the Toga person list.

Pure functions over the domain `individuals` dict — no Toga, no tkinter — so they are
unit-testable headlessly and shared cleanly with the view. Mirrors the ordering and
search behaviour of the legacy `SearchMixin`.
"""
from gedcom_display import format_year
from gedcom_name_search import find_candidates


def sorted_person_ids(individuals):
    """Stable name-then-id ordering (matches the tkinter person list)."""
    return sorted(
        individuals,
        key=lambda iid: (individuals[iid].get("name", "").lower(), iid),
    )


def person_row(individuals, iid, *, show_id=False):
    """One table row as a dict keyed by the Toga Table accessors (+ `id` for lookup)."""
    indi = individuals.get(iid, {})
    name = indi.get("name") or iid
    if show_id:
        name = f"{name}  [{iid}]"
    return {
        "id": iid,
        "name": name,
        "born": format_year(indi.get("birth_year")),
        "died": format_year(indi.get("death_year")),
    }


def visible_ids(individuals, query, sorted_ids, *, fuzzy=False,
                fuzzy_threshold=0.72, max_display=2000):
    """Ids to display: the full sorted list when the query is empty, otherwise the
    ranked search candidates from `find_candidates`. Capped at `max_display`.

    Returns `(ids, truncated)`.
    """
    q = (query or "").strip()
    if not q:
        ids = list(sorted_ids)
    else:
        ids = [iid for iid, _score in find_candidates(
            individuals, q, fuzzy=fuzzy, fuzzy_threshold=fuzzy_threshold)]
    truncated = len(ids) > max_display
    return ids[:max_display], truncated
