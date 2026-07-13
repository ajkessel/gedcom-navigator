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


def display_name(indi, name_order="first_last"):
    """Display name honouring the name-order preference (mirrors the tkinter
    `_display_name`): `last_first` -> "Surname, Given" when both are known."""
    if name_order == "last_first":
        surname = indi.get("surname", "")
        given = indi.get("given_name", "")
        if surname and given:
            return f"{surname}, {given}"
        if surname:
            return surname
    return indi.get("name") or "(unknown)"


def person_row(individuals, iid, *, show_id=False, name_order="first_last"):
    """One table row as a dict keyed by the Toga Table accessors (+ `id` for lookup)."""
    indi = individuals.get(iid, {})
    name = display_name(indi, name_order)
    if show_id:
        name = f"{name}  [{iid}]"
    return {
        "id": iid,
        "name": name,
        "born": format_year(indi.get("birth_year")),
        "died": format_year(indi.get("death_year")),
    }


def updated_recent(recent, path, *, cap=10):
    """Return the recent-files list with `path` moved to the front, de-duplicated
    and capped at `cap`."""
    path = str(path)
    return ([path] + [p for p in (recent or []) if p != path])[:cap]


def visible_ids(individuals, query, sorted_ids, *, fuzzy=False,
                fuzzy_threshold=0.72, max_display=2000, dna_only=False):
    """Ids to display: the full sorted list when the query is empty, otherwise the
    ranked search candidates from `find_candidates`. Optionally restricted to
    DNA-flagged people, then capped at `max_display`.

    Returns `(ids, truncated)`.
    """
    q = (query or "").strip()
    if not q:
        ids = list(sorted_ids)
    else:
        ids = [iid for iid, _score in find_candidates(
            individuals, q, fuzzy=fuzzy, fuzzy_threshold=fuzzy_threshold)]
    if dna_only:
        ids = [iid for iid in ids if individuals[iid].get("dna_markers")]
    truncated = len(ids) > max_display
    return ids[:max_display], truncated
