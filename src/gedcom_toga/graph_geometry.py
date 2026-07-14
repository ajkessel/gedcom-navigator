"""Pure geometry/lookup helpers for the Toga graph views (Phase 5.3).

The tkinter render mixins (gedcom_gui_graph_common / gedcom_gui_family_tree_render)
import tkinter at module top, so their pure helpers can't be imported here. The small
ones the path-graph popup needs are reimplemented against the raw model dicts:

- `family_members` — immediate parents/siblings/spouses/children of a person (the
  `family_lookup` callable that build/expand layout functions expect). A simplified
  version of the tkinter `_family_tree_members_for` (no step/half classification —
  fine for graph expansion).
- `coparents` — the other parent(s) of a person's given children (the
  `coparent_lookup`), mirroring the tkinter `_co_parents_for_children`.
"""


def family_members(indi_id, individuals, families):
    """Return {parents, siblings, spouses, children} id-lists for one person."""
    empty = {"parents": [], "siblings": [], "spouses": [], "children": []}
    indi = individuals.get(indi_id)
    if not indi:
        return empty
    parents, siblings, spouses, children = [], [], [], []
    seen_p, seen_s, seen_sp, seen_c = set(), set(), set(), set()
    for fam_id in indi.get("famc", ()):
        fam = families.get(fam_id)
        if not fam:
            continue
        for pid in (fam.get("husb"), fam.get("wife")):
            if pid and pid in individuals and pid not in seen_p:
                parents.append(pid)
                seen_p.add(pid)
        for sib in fam.get("chil", ()):
            if sib != indi_id and sib in individuals and sib not in seen_s:
                siblings.append(sib)
                seen_s.add(sib)
    for fam_id in indi.get("fams", ()):
        fam = families.get(fam_id)
        if not fam:
            continue
        spouse = fam.get("wife") if fam.get("husb") == indi_id else fam.get("husb")
        if spouse and spouse in individuals and spouse not in seen_sp:
            spouses.append(spouse)
            seen_sp.add(spouse)
        for ch in fam.get("chil", ()):
            if ch in individuals and ch not in seen_c:
                children.append(ch)
                seen_c.add(ch)
    return {"parents": parents, "siblings": siblings,
            "spouses": spouses, "children": children}


def coparents(indi_id, child_ids, individuals, families):
    """Return the other parent(s) of `indi_id`'s families that include `child_ids`."""
    indi = individuals.get(indi_id)
    if not indi:
        return []
    wanted = set(child_ids)
    out, seen = [], set()
    for fam_id in indi.get("fams", ()):
        fam = families.get(fam_id)
        if not fam:
            continue
        if not any(c in wanted for c in fam.get("chil", ())):
            continue
        parent_id = fam.get("wife") if fam.get("husb") == indi_id else fam.get("husb")
        if parent_id and parent_id in individuals and parent_id not in seen:
            out.append(parent_id)
            seen.add(parent_id)
    return out
