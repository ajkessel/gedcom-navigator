"""Toolkit-free person-detail + immediate-family helpers for the Toga UI.

Pure functions over the domain `individuals`/`families` dicts — headless-testable, no
Toga. Produces the text shown in the detail pane and the DNA-flag predicate used by the
list filter.
"""
from gedcom_display import describe


def is_dna_flagged(indi):
    """A person is DNA-flagged when the parser recorded DNA markers for them."""
    return bool(indi.get("dna_markers"))


def immediate_family(individuals, families, iid):
    """Return {'parents', 'spouses', 'children'} as lists of individual ids,
    de-duplicated and existence-checked, in GEDCOM order."""
    indi = individuals.get(iid, {})
    parents, spouses, children = [], [], []
    seen = {"p": set(), "s": set(), "c": set()}

    def add(bucket, key, target):
        if target and target in individuals and target not in seen[key] and target != iid:
            seen[key].add(target)
            bucket.append(target)

    for fam_id in indi.get("famc", ()):            # families where iid is a child
        fam = families.get(fam_id) or {}
        add(parents, "p", fam.get("husb"))
        add(parents, "p", fam.get("wife"))
    for fam_id in indi.get("fams", ()):            # families where iid is a spouse
        fam = families.get(fam_id) or {}
        spouse = fam.get("wife") if fam.get("husb") == iid else fam.get("husb")
        add(spouses, "s", spouse)
        for child in fam.get("chil", ()):
            add(children, "c", child)
    return {"parents": parents, "spouses": spouses, "children": children}


def detail_text(individuals, families, iid, *, show_id=False):
    """Multi-line detail for the selected person: header (name + lifespan [+ id]),
    a DNA-match marker, and immediate family grouped by relation."""
    indi = individuals.get(iid)
    if not indi:
        return ""
    lines = [describe(indi, show_id=show_id)]
    if is_dna_flagged(indi):
        lines.append("★ DNA match")

    fam = immediate_family(individuals, families, iid)
    for title, ids in (("Parents", fam["parents"]),
                        ("Spouses", fam["spouses"]),
                        ("Children", fam["children"])):
        if ids:
            lines.append("")
            lines.append(f"{title}:")
            lines.extend(f"  • {describe(individuals[i], show_id=show_id)}" for i in ids)
    return "\n".join(lines)
