"""Tests for the distributable synthetic GEDCOM sample."""

from pathlib import Path

from gedcom_core import build_model
from gedcom_relationship import get_ancestor_depths


SAMPLE_GEDCOM = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "fictional_genealogy.ged"
)


def _id_for_name(individuals, name):
    matches = [xref for xref, person in individuals.items() if person["name"] == name]
    assert len(matches) == 1
    return matches[0]


def test_synthetic_sample_parse_counts_and_dna_markers():
    individuals, families, tag_records, warning, error = build_model(
        str(SAMPLE_GEDCOM), "DNA", "AncestryDNA Match"
    )

    assert warning is None
    assert error is None
    assert len(individuals) == 1000
    assert len(families) >= 180
    assert sum(1 for person in individuals.values() if len(person["fams"]) > 1) >= 10
    assert tag_records["@T1@"] == "DNA Match"
    assert tag_records["@T2@"] == "Research Lead"
    assert tag_records["@T3@"] == "Needs Verification"

    flagged = [
        person for person in individuals.values()
        if person["dna_markers"]
    ]
    assert len(flagged) == 50
    assert any(
        any(marker.startswith("Tag: DNA Match") for marker in person["dna_markers"])
        for person in flagged
    )
    assert any(
        any(marker.startswith("Source citation:") for marker in person["dna_markers"])
        for person in flagged
    )


def test_synthetic_sample_has_cross_branch_cousin_marriage():
    individuals, families, _, _, error = build_model(
        str(SAMPLE_GEDCOM), "DNA", "AncestryDNA Match"
    )

    assert error is None
    maya = _id_for_name(individuals, "Maya Lynn Hart")
    caleb = _id_for_name(individuals, "Caleb Hart Lane")
    natalie = _id_for_name(individuals, "Natalie Stone Bell")
    arthur = _id_for_name(individuals, "Arthur Miles Hart")
    beatrice = _id_for_name(individuals, "Beatrice Anne Cole")
    joseph = _id_for_name(individuals, "Joseph Samuel Reed")
    helen = _id_for_name(individuals, "Helen Irene Price")

    maya_ancestors = get_ancestor_depths(maya, individuals, families)
    caleb_ancestors = get_ancestor_depths(caleb, individuals, families)
    natalie_ancestors = get_ancestor_depths(natalie, individuals, families)

    assert maya_ancestors[arthur] == 2
    assert maya_ancestors[beatrice] == 2
    assert caleb_ancestors[arthur] == 2
    assert caleb_ancestors[beatrice] == 2
    assert maya_ancestors[joseph] == 3
    assert maya_ancestors[helen] == 3
    assert natalie_ancestors[joseph] == 3
    assert natalie_ancestors[helen] == 3
    assert families["@F10@"]["husb"] == caleb
    assert families["@F10@"]["wife"] == natalie
