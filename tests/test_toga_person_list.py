"""Tests for the Toga person-list helpers (gedcom_toga.person_list).

Pure logic, no Toga import — safe in the default (non-GUI) test run.
"""
from gedcom_toga import person_list as pl

INDIVIDUALS = {
    "@I1@": {"id": "@I1@", "name": "Bob Smith", "birth_year": 1900, "death_year": 1970},
    "@I2@": {"id": "@I2@", "name": "alice jones", "birth_year": 1850,
             "dna_markers": ["AncestryDNA Match to X"]},
    "@I3@": {"id": "@I3@", "name": "Carol Smith", "dna_markers": []},
    "@I10@": {"id": "@I10@", "name": "Zeta Last", "birth_year": 2000},
}


def test_sorted_person_ids_orders_by_name_then_id():
    # alice, bob, carol, zeta (case-insensitive by name)
    assert pl.sorted_person_ids(INDIVIDUALS) == ["@I2@", "@I1@", "@I3@", "@I10@"]


def test_sorted_person_ids_tiebreaks_on_id_lexicographically():
    # equal names -> tiebreak by the raw string id (as the tkinter list does);
    # "@I10@" < "@I1@" because char 4 is '0'(48) < '@'(64).
    ind = {"@I2@": {"name": "Same"}, "@I10@": {"name": "Same"}, "@I1@": {"name": "Same"}}
    assert pl.sorted_person_ids(ind) == ["@I10@", "@I1@", "@I2@"]


def test_person_row_fields():
    assert pl.person_row(INDIVIDUALS, "@I1@") == {
        "id": "@I1@", "name": "Bob Smith", "born": "1900", "died": "1970"}


def test_person_row_missing_years_are_blank():
    row = pl.person_row(INDIVIDUALS, "@I3@")
    assert row["born"] == "" and row["died"] == ""


def test_person_row_show_id_appends_id():
    row = pl.person_row(INDIVIDUALS, "@I1@", show_id=True)
    assert row["name"].startswith("Bob Smith") and row["name"].endswith("[@I1@]")


def test_visible_ids_empty_query_returns_sorted_unchanged():
    sid = pl.sorted_person_ids(INDIVIDUALS)
    assert pl.visible_ids(INDIVIDUALS, "", sid) == (sid, False)


def test_visible_ids_exact_id_query():
    sid = pl.sorted_person_ids(INDIVIDUALS)
    ids, _ = pl.visible_ids(INDIVIDUALS, "@I1@", sid)
    assert ids == ["@I1@"]


def test_visible_ids_name_query_filters():
    sid = pl.sorted_person_ids(INDIVIDUALS)
    ids, _ = pl.visible_ids(INDIVIDUALS, "smith", sid)
    assert set(ids) == {"@I1@", "@I3@"}


def test_visible_ids_dna_only_keeps_only_flagged():
    sid = pl.sorted_person_ids(INDIVIDUALS)
    ids, _ = pl.visible_ids(INDIVIDUALS, "", sid, dna_only=True)
    assert ids == ["@I2@"]            # falsy dna_markers ([]) is not flagged


def test_visible_ids_max_display_truncates():
    ind = {f"@I{n}@": {"id": f"@I{n}@", "name": f"P{n:03d}"} for n in range(50)}
    sid = pl.sorted_person_ids(ind)
    ids, truncated = pl.visible_ids(ind, "", sid, max_display=10)
    assert len(ids) == 10 and truncated is True


# ---- display_name (name-order preference) ---------------------------------
_NAMED = {"name": "Bob Smith", "surname": "Smith", "given_name": "Bob"}


def test_display_name_first_last_uses_name_field():
    assert pl.display_name(_NAMED) == "Bob Smith"


def test_display_name_last_first_uses_surname_given():
    assert pl.display_name(_NAMED, "last_first") == "Smith, Bob"


def test_display_name_last_first_falls_back_when_incomplete():
    assert pl.display_name({"name": "Madonna"}, "last_first") == "Madonna"
    assert pl.display_name({"name": "", "surname": "Cher"}, "last_first") == "Cher"


def test_display_name_unknown_when_empty():
    assert pl.display_name({}) == "(unknown)"


def test_person_row_respects_name_order():
    ind = {"@I1@": dict(id="@I1@", **_NAMED)}
    assert pl.person_row(ind, "@I1@", name_order="last_first")["name"] == "Smith, Bob"


# ---- updated_recent -------------------------------------------------------
def test_updated_recent_moves_to_front_and_dedupes():
    assert pl.updated_recent(["/a", "/b", "/c"], "/b") == ["/b", "/a", "/c"]


def test_updated_recent_no_duplicate_when_already_first():
    assert pl.updated_recent(["/a", "/b"], "/a") == ["/a", "/b"]


def test_updated_recent_caps_length():
    recent = [f"/{i}" for i in range(20)]
    assert pl.updated_recent(recent, "/new", cap=3) == ["/new", "/0", "/1"]


def test_updated_recent_handles_none():
    assert pl.updated_recent(None, "/a") == ["/a"]
