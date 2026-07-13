"""Tests for the Toga person-detail / immediate-family helpers
(gedcom_toga.person_detail). Pure logic, no Toga import.
"""
from gedcom_toga import person_detail as pd

INDIVIDUALS = {
    "@I1@": {"id": "@I1@", "name": "Arthur Hart", "birth_year": 1930,
             "death_year": 2017, "fams": ["@F1@"]},
    "@I2@": {"id": "@I2@", "name": "Beatrice Cole", "birth_year": 1932,
             "death_year": 2000, "fams": ["@F1@"]},
    "@I3@": {"id": "@I3@", "name": "Caleb Hart", "birth_year": 1960,
             "famc": ["@F1@"], "fams": ["@F2@", "@F3@"], "dna_markers": ["m"]},
    "@I4@": {"id": "@I4@", "name": "Evelyn Reed", "birth_year": 1962, "fams": ["@F2@"]},
    "@I5@": {"id": "@I5@", "name": "Laura Finch", "birth_year": 1965, "fams": ["@F3@"]},
    "@I6@": {"id": "@I6@", "name": "Maya Hart", "birth_year": 1986, "famc": ["@F2@"]},
    "@I7@": {"id": "@I7@", "name": "Jonah Hart", "birth_year": 1989, "famc": ["@F3@"]},
    "@I9@": {"id": "@I9@", "name": "Orphan Nobody"},
}
FAMILIES = {
    "@F1@": {"husb": "@I1@", "wife": "@I2@", "chil": ["@I3@"]},
    "@F2@": {"husb": "@I3@", "wife": "@I4@", "chil": ["@I6@"]},
    "@F3@": {"husb": "@I3@", "wife": "@I5@", "chil": ["@I7@"]},
}


def test_is_dna_flagged():
    assert pd.is_dna_flagged(INDIVIDUALS["@I3@"]) is True
    assert pd.is_dna_flagged(INDIVIDUALS["@I1@"]) is False


def test_immediate_family_parents_spouses_children():
    fam = pd.immediate_family(INDIVIDUALS, FAMILIES, "@I3@")
    assert fam["parents"] == ["@I1@", "@I2@"]
    assert fam["spouses"] == ["@I4@", "@I5@"]        # both marriages
    assert fam["children"] == ["@I6@", "@I7@"]       # children from both marriages


def test_immediate_family_excludes_self_and_missing_ids():
    fams = dict(FAMILIES)
    fams["@F2@"] = {"husb": "@I3@", "wife": "@I4@", "chil": ["@I6@", "@I3@", "@IXX@"]}
    fam = pd.immediate_family(INDIVIDUALS, fams, "@I3@")
    assert "@I3@" not in fam["children"]             # self excluded
    assert "@IXX@" not in fam["children"]            # nonexistent id excluded


def test_immediate_family_person_with_no_family():
    assert pd.immediate_family(INDIVIDUALS, FAMILIES, "@I9@") == {
        "parents": [], "spouses": [], "children": []}


def test_detail_text_has_header_dna_and_family_sections():
    text = pd.detail_text(INDIVIDUALS, FAMILIES, "@I3@")
    assert "Caleb Hart (b. 1960)" in text
    assert "★ DNA match" in text
    assert "Parents:" in text and "Arthur Hart (1930-2017)" in text
    assert "Spouses:" in text
    assert "Evelyn Reed (b. 1962)" in text and "Laura Finch (b. 1965)" in text
    assert "Children:" in text
    assert "Maya Hart (b. 1986)" in text and "Jonah Hart (b. 1989)" in text


def test_detail_text_show_id_adds_ids():
    text = pd.detail_text(INDIVIDUALS, FAMILIES, "@I3@", show_id=True)
    assert "[@I3@]" in text and "[@I1@]" in text     # header + a parent


def test_detail_text_omits_dna_marker_when_unflagged():
    assert "★ DNA match" not in pd.detail_text(INDIVIDUALS, FAMILIES, "@I1@")


def test_detail_text_unknown_id_returns_empty():
    assert pd.detail_text(INDIVIDUALS, FAMILIES, "@NOPE@") == ""
