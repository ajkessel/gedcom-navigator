"""Tests for gedcom_core.py — GEDCOM parsing, BFS engine, and utility functions."""
import os
import threading
import zipfile

import pytest

import gedcom_parser as parser_mod
from gedcom_core import (
    SearchCancelled,
    ZIP_MAX_BYTES,
    bfs_find_all_paths,
    bfs_find_dna_matches,
    build_model,
    describe,
    extract_ged_from_zip,
    extract_year,
    format_year,
    iter_records,
    iter_records_checked,
    lifespan,
    neighbors,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ged(tmp_path, content, filename="test.ged"):
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return str(p)


def _make_indi(id, name="", sex="", famc=None, fams=None, dna_markers=None,
               birth_year=None, death_year=None):
    return {
        "id": id, "name": name, "surname": "", "given_name": "",
        "alt_names": [name] if name else [],
        "sex": sex, "famc": famc or [], "fams": fams or [],
        "dna_markers": dna_markers or [],
        "birth_year": birth_year, "death_year": death_year, "_raw": [],
    }


def _make_fam(id, husb=None, wife=None, chil=None):
    return {"id": id, "husb": husb, "wife": wife, "chil": chil or [],
            "marr_date": "", "marr_place": ""}


# ---------------------------------------------------------------------------
# GEDCOM content fixtures
# ---------------------------------------------------------------------------

SIMPLE_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 BIRT
2 DATE 1 JAN 1950
1 FAMS @F1@
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE 15 MAR 1952
1 DEAT
2 DATE 5 APR 2010
1 FAMS @F1@
0 @I3@ INDI
1 NAME Alice /Smith/
1 SEX F
1 BIRT
2 DATE 1980
1 FAMC @F1@
0 @I4@ INDI
1 NAME Bob /Smith/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
0 TRLR
"""

# Synthetic tree exercising historical date styles: BCE birth/death dates and
# a Julian/Gregorian dual year. Deliberately does NOT reuse debug/dates.ged.
HISTORICAL_DATES_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Gaius /Julius/
1 BIRT
2 DATE 13 JUL 100 B.C.
1 DEAT
2 DATE 15 MAR 44 B.C.
0 @I2@ INDI
1 NAME Old /Style/
1 BIRT
2 DATE 10 JAN 1708/9
1 DEAT
2 DATE 15 APR 1699/00
0 @I3@ INDI
1 NAME Single /Digit/
1 BIRT
2 DATE 1 B.C.
0 TRLR
"""

DNA_MTTAG_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @T1@ _MTTAG
1 NAME DNA Match Tag
0 @T2@ _MTTAG
1 NAME Other Tag
0 @I1@ INDI
1 NAME Start /Person/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME DNA Match /Person/
1 SEX M
1 _MTTAG @T1@
1 FAMC @F1@
0 @I3@ INDI
1 NAME Not DNA /Person/
1 SEX F
1 _MTTAG @T2@
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
1 CHIL @I3@
0 TRLR
"""

DNA_PAGE_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Start /Person/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Page Match /Person/
1 SEX F
1 SOUR @S1@
2 PAGE AncestryDNA Match to some person
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 TRLR
"""

DNA_INLINE_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Start /Person/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Inline DNA /Person/
1 SEX F
1 _MTTAG
2 NAME DNA Match Entry
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 TRLR
"""

# Non-Ancestry export: no _MTTAG records, DNA matches encoded in the various
# custom-field forms produced by other genealogy software.
DNA_ALTERNATE_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Start /Person/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Even Match /Person/
1 SEX F
1 EVEN
2 TYPE DNA Match
1 FAMC @F1@
0 @I3@ INDI
1 NAME Fact Match /Person/
1 SEX M
1 FACT Shared 120 cM
2 TYPE DNA
1 FAMC @F1@
0 @I4@ INDI
1 NAME Tag Match /Person/
1 SEX F
1 _DNAMATCH Y
1 FAMC @F1@
0 @I5@ INDI
1 NAME Refn Match /Person/
1 SEX M
1 REFN kit-12345
2 TYPE DNA kit
1 FAMC @F1@
0 @I6@ INDI
1 NAME Note Only /Person/
1 SEX F
1 NOTE Possible DNA cousin, not yet confirmed
1 FAMC @F1@
0 @I7@ INDI
1 NAME Plain Person /Person/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I5@
1 CHIL @I6@
1 CHIL @I7@
0 TRLR
"""

# Ancestry file (has _MTTAG) that also carries a stray custom FACT mentioning
# DNA. The FACT must be ignored because _MTTAG records are present.
DNA_MTTAG_WITH_FACT_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @T1@ _MTTAG
1 NAME DNA Match Tag
0 @I1@ INDI
1 NAME Start /Person/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Stray Fact /Person/
1 SEX F
1 FACT Shared 80 cM
2 TYPE DNA
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
0 TRLR
"""


# ===========================================================================
# extract_year
# ===========================================================================

class TestExtractYear:
    def test_standard_gedcom_date(self):
        assert extract_year("1 JAN 1950") == 1950

    def test_year_only(self):
        assert extract_year("1950") == 1950

    def test_three_digit_year(self):
        assert extract_year("900") == 900

    def test_abbreviated_qualifier(self):
        assert extract_year("ABT 1850") == 1850

    def test_none_input(self):
        assert extract_year(None) is None

    def test_empty_string(self):
        assert extract_year("") is None

    def test_two_digit_year_not_matched(self):
        assert extract_year("98") is None

    def test_no_digits(self):
        assert extract_year("ABC DEF") is None

    def test_five_digit_sequence_not_matched(self):
        # word-boundary regex won't match 4-digit prefix of a 5-digit run
        assert extract_year("12345") is None

    def test_year_with_range_returns_first(self):
        # "1800-1850" — the '-' is a word boundary so 1800 matches
        result = extract_year("1800-1850")
        assert result == 1800

    # --- BCE dates: returned as negative years -----------------------------
    def test_bce_four_digit(self):
        assert extract_year("1001 B.C.") == -1001

    def test_bce_three_digit(self):
        assert extract_year("101 B.C.") == -101

    def test_bce_two_digit(self):
        # 1- and 2-digit BCE years must still parse (the B.C. disambiguates
        # them from a day-of-month number).
        assert extract_year("11 B.C.") == -11

    def test_bce_single_digit(self):
        assert extract_year("1 B.C.") == -1

    def test_bce_with_full_gedcom_date(self):
        assert extract_year("15 MAR 44 B.C.") == -44

    def test_bce_no_periods(self):
        assert extract_year("753 BC") == -753

    def test_bce_bce_spelling(self):
        assert extract_year("44 BCE") == -44

    def test_bce_case_insensitive(self):
        assert extract_year("100 b.c.") == -100

    # --- Julian/Gregorian dual years: resolve to New Style (later) year ----
    def test_dual_year_single_digit_suffix(self):
        # "1708/9" is 1708 Old Style / 1709 New Style -> 1709
        assert extract_year("10 JAN 1708/9") == 1709

    def test_dual_year_two_digit_suffix(self):
        # "1699/00" is 1699 Old Style / 1700 New Style -> 1700
        assert extract_year("15 APR 1699/00") == 1700

    def test_dual_year_century_rollover(self):
        assert extract_year("1599/0") == 1600

    def test_dual_year_bare(self):
        assert extract_year("1745/6") == 1746


class TestHistoricalDateParsing:
    """End-to-end: BCE and dual-year dates flow into birth/death years."""

    def test_bce_birth_and_death_years(self, tmp_path):
        p = _write_ged(tmp_path, HISTORICAL_DATES_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I1@"]["birth_year"] == -100
        assert indiv["@I1@"]["death_year"] == -44

    def test_dual_years_resolve_to_new_style(self, tmp_path):
        p = _write_ged(tmp_path, HISTORICAL_DATES_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I2@"]["birth_year"] == 1709
        assert indiv["@I2@"]["death_year"] == 1700

    def test_single_digit_bce_birth_year(self, tmp_path):
        p = _write_ged(tmp_path, HISTORICAL_DATES_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I3@"]["birth_year"] == -1

    def test_bce_lifespan_rendering(self, tmp_path):
        p = _write_ged(tmp_path, HISTORICAL_DATES_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert lifespan(indiv["@I1@"]) == "100 BC-44 BC"


# ===========================================================================
# iter_records / iter_records_checked
# ===========================================================================

class TestIterRecords:
    def test_correct_record_count(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        records = list(iter_records(p))
        # HEAD, I1, I2, I3, I4, F1, TRLR = 7
        assert len(records) == 7

    def test_head_record_structure(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        head = list(iter_records(p))[0]
        assert head[0] == (0, None, "HEAD", "")

    def test_individual_xref_parsed(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        records = list(iter_records(p))
        i1 = records[1]
        assert i1[0][1] == "@I1@"
        assert i1[0][2] == "INDI"

    def test_malformed_line_skipped(self, tmp_path):
        content = "0 HEAD\n!not a gedcom line\n0 @I1@ INDI\n1 NAME Test\n0 TRLR\n"
        p = _write_ged(tmp_path, content)
        records = list(iter_records(p))
        assert len(records) == 3

    def test_blank_lines_skipped(self, tmp_path):
        content = "0 HEAD\n\n\n0 @I1@ INDI\n1 NAME Test\n0 TRLR\n"
        p = _write_ged(tmp_path, content)
        records = list(iter_records(p))
        assert len(records) == 3

    def test_subrecords_attached_to_parent(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        records = list(iter_records(p))
        i1 = records[1]
        # Should have NAME, SEX, BIRT, DATE, FAMS subrecords
        tags = [t for _, _, t, _ in i1]
        assert "NAME" in tags
        assert "SEX" in tags
        assert "BIRT" in tags


class TestIterRecordsChecked:
    def test_clean_file_returns_no_warning(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        records, warning = iter_records_checked(p)
        assert warning is None
        assert len(records) == 7

    def test_encoding_issue_triggers_warning(self, tmp_path):
        p = tmp_path / "latin1.ged"
        # Latin-1 byte that is invalid UTF-8 → replaced with U+FFFD
        p.write_bytes(b"0 HEAD\n0 @I1@ INDI\n1 NAME Jos\xe9\n0 TRLR\n")
        _, warning = iter_records_checked(str(p))
        assert warning is not None
        assert "UTF-8" in warning or "replaced" in warning.lower()

    def test_records_still_returned_with_bad_encoding(self, tmp_path):
        p = tmp_path / "latin1.ged"
        p.write_bytes(b"0 HEAD\n0 @I1@ INDI\n1 NAME Jos\xe9\n0 TRLR\n")
        records, _ = iter_records_checked(str(p))
        assert len(records) == 3  # HEAD, I1, TRLR


# ===========================================================================
# build_model
# ===========================================================================

class TestBuildModel:
    def test_parses_all_individuals(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert set(indiv) >= {"@I1@", "@I2@", "@I3@", "@I4@"}

    def test_parses_family(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        _, fams, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        fam = fams["@F1@"]
        assert fam["husb"] == "@I1@"
        assert fam["wife"] == "@I2@"
        assert "@I3@" in fam["chil"]
        assert "@I4@" in fam["chil"]

    def test_parses_name_components(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I1@"]["name"] == "John Smith"
        assert indiv["@I1@"]["surname"] == "Smith"
        assert indiv["@I1@"]["given_name"] == "John"

    def test_parses_sex(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I1@"]["sex"] == "M"
        assert indiv["@I2@"]["sex"] == "F"

    def test_parses_birth_year(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I1@"]["birth_year"] == 1950
        assert indiv["@I2@"]["birth_year"] == 1952
        assert indiv["@I3@"]["birth_year"] == 1980

    def test_parses_death_year(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert indiv["@I2@"]["death_year"] == 2010
        assert indiv["@I1@"]["death_year"] is None

    def test_parses_famc_fams(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert "@F1@" in indiv["@I1@"]["fams"]
        assert "@F1@" in indiv["@I3@"]["famc"]

    def test_parses_parentage_metadata(self, tmp_path):
        ged = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @DAD@ INDI
1 NAME Dad /Person/
1 FAMS @F1@
0 @MOM@ INDI
1 NAME Mom /Person/
1 FAMS @F1@
0 @CHILD@ INDI
1 NAME Child /Person/
1 FAMC @F1@
2 PEDI foster
1 ADOP
2 FAMC @F1@
3 ADOP HUSB
0 @F1@ FAM
1 HUSB @DAD@
1 WIFE @MOM@
1 CHIL @CHILD@
2 _FREL natural
2 _MREL step
0 TRLR
"""
        p = _write_ged(tmp_path, ged)
        _indiv, fams, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")

        link = fams["@F1@"]["child_links"]["@CHILD@"]
        assert link["family"] == "foster"
        assert link["father"] == "adopted"
        assert link["mother"] == "step"

    def test_no_dna_markers_in_plain_file(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        for indi in indiv.values():
            assert indi["dna_markers"] == []

    def test_mttag_pointer_adds_dna_marker(self, tmp_path):
        p = _write_ged(tmp_path, DNA_MTTAG_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert len(indiv["@I2@"]["dna_markers"]) > 0
        # Non-matching tag should not be flagged
        assert len(indiv["@I3@"]["dna_markers"]) == 0

    def test_mttag_tag_records_collected(self, tmp_path):
        p = _write_ged(tmp_path, DNA_MTTAG_GED)
        _, _, tags, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert "@T1@" in tags
        assert tags["@T1@"] == "DNA Match Tag"

    def test_page_marker_adds_dna_marker(self, tmp_path):
        p = _write_ged(tmp_path, DNA_PAGE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert len(indiv["@I2@"]["dna_markers"]) > 0
        assert any("AncestryDNA" in m for m in indiv["@I2@"]["dna_markers"])

    def test_page_marker_case_insensitive(self, tmp_path):
        content = DNA_PAGE_GED.replace("AncestryDNA", "ANCESTRYDNA")
        p = _write_ged(tmp_path, content)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "ancestrydna")
        assert len(indiv["@I2@"]["dna_markers"]) > 0

    def test_inline_mttag_adds_dna_marker(self, tmp_path):
        p = _write_ged(tmp_path, DNA_INLINE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert len(indiv["@I2@"]["dna_markers"]) > 0

    def test_clean_file_no_encoding_warning(self, tmp_path):
        p = _write_ged(tmp_path, SIMPLE_GED)
        _, _, _, _, warn, error, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert warn is None
        assert error is None

    def test_custom_dna_keyword_not_matched(self, tmp_path):
        # DNA_MTTAG_GED uses "DNA Match Tag"; searching for a different keyword
        # should not flag I2
        p = _write_ged(tmp_path, DNA_MTTAG_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "XYZ_NOMATCH", "AncestryDNA")
        assert indiv["@I2@"]["dna_markers"] == []

    def test_empty_file_returns_model_error(self, tmp_path):
        p = _write_ged(tmp_path, "")
        individuals, families, tags, _, warning, error, _, _ = build_model(
            p, "DNA", "AncestryDNA")
        assert individuals == {}
        assert families == {}
        assert tags == {}
        assert warning is None
        assert error is not None
        assert "No GEDCOM records" in error

    def test_file_without_individuals_returns_model_error(self, tmp_path):
        p = _write_ged(tmp_path, "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n0 TRLR\n")
        individuals, _, _, _, _, error, _, _ = build_model(p, "DNA", "AncestryDNA")
        assert individuals == {}
        assert error is not None
        assert "No individual records" in error

    def test_ftm_photo_candidate_is_first(self, tmp_path):
        ged = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Alice /Smith/
1 OBJE
2 FILE other.jpg
1 _PHOTO portrait.jpg
0 TRLR
"""
        p = _write_ged(tmp_path, ged)
        individuals, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        candidates = individuals["@I1@"]["media_candidates"]
        assert candidates[0]["kind"] == "_PHOTO"
        assert candidates[0]["file"] == "portrait.jpg"

    def test_primary_obje_reference_merges_top_level_media(self, tmp_path):
        ged = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Alice /Smith/
1 OBJE @M1@
2 _PRIM Y
0 @M1@ OBJE
1 FILE portraits/alice.jpg
1 FORM jpg
1 TITL Alice Smith
0 TRLR
"""
        p = _write_ged(tmp_path, ged)
        individuals, _, _, media, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        candidate = individuals["@I1@"]["media_candidates"][0]
        assert media["@M1@"]["file"] == "portraits/alice.jpg"
        assert candidate["ref"] == "@M1@"
        assert candidate["file"] == "portraits/alice.jpg"
        assert candidate["primary"] is True

    def test_inline_obje_and_empty_file_metadata_are_preserved(self, tmp_path):
        ged = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Alice /Smith/
1 OBJE
2 FILE
3 FORM jpg
3 TITL Ancestry placeholder
1 OBJE
2 FILE Alice Smith.png
3 FORM png
3 TITL Alice Smith
0 TRLR
"""
        p = _write_ged(tmp_path, ged)
        individuals, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        candidates = individuals["@I1@"]["media_candidates"]
        assert candidates[0]["file"] == "Alice Smith.png"
        assert candidates[0]["name_match"] is True
        assert candidates[1]["file"] == ""
        assert candidates[1]["title"] == "Ancestry placeholder"

    def test_empty_primary_media_stays_selected_for_fallback(self, tmp_path):
        ged = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Alice /Smith/
1 OBJE
2 FILE
2 _PRIM Y
2 TITL Missing primary
1 OBJE
2 FILE Alice Smith.png
2 TITL Alice Smith
0 TRLR
"""
        p = _write_ged(tmp_path, ged)
        individuals, _, _, _, _, _, _, _ = build_model(p, "DNA", "AncestryDNA")
        candidates = individuals["@I1@"]["media_candidates"]
        assert candidates[0]["primary"] is True
        assert candidates[0]["file"] == ""


# ===========================================================================
# Non-Ancestry (alternate) DNA detection
# ===========================================================================

class TestAlternateDnaDetection:
    def test_alternate_fields_flag_when_no_mttag(self, tmp_path):
        p = _write_ged(tmp_path, DNA_ALTERNATE_GED)
        indiv, _, _, _, _, _, uses_alt, catalog = build_model(
            p, "DNA", "AncestryDNA")
        assert uses_alt is True
        # EVEN / FACT / custom _DNA tag / REFN all flagged
        assert indiv["@I2@"]["dna_markers"]
        assert indiv["@I3@"]["dna_markers"]
        assert indiv["@I4@"]["dna_markers"]
        assert indiv["@I5@"]["dna_markers"]
        # NOTE not scanned by default
        assert indiv["@I6@"]["dna_markers"] == []
        # Unrelated plain person never flagged
        assert indiv["@I7@"]["dna_markers"] == []

    def test_note_field_flags_when_enabled(self, tmp_path):
        p = _write_ged(tmp_path, DNA_ALTERNATE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(
            p, "DNA", "AncestryDNA", detection_fields="note")
        assert indiv["@I6@"]["dna_markers"]
        # With only NOTE enabled, EVEN-based match is not flagged
        assert indiv["@I2@"]["dna_markers"] == []

    def test_discovery_catalog_populated(self, tmp_path):
        p = _write_ged(tmp_path, DNA_ALTERNATE_GED)
        _, _, _, _, _, _, _, catalog = build_model(p, "DNA", "AncestryDNA")
        entries = {(r["kind"], r["type"]) for r in catalog}
        assert ("EVEN", "DNA Match") in entries
        assert ("FACT", "DNA") in entries
        assert ("REFN", "DNA kit") in entries
        assert ("_TAG", "_DNAMATCH") in entries

    def test_mttag_file_ignores_alternate_fields(self, tmp_path):
        p = _write_ged(tmp_path, DNA_MTTAG_WITH_FACT_GED)
        indiv, _, _, _, _, _, uses_alt, catalog = build_model(
            p, "DNA", "AncestryDNA")
        # _MTTAG present -> alternate detection disabled, stray FACT ignored
        assert uses_alt is False
        assert catalog == []
        assert indiv["@I2@"]["dna_markers"] == []

    def test_empty_keyword_flags_nobody(self, tmp_path):
        p = _write_ged(tmp_path, DNA_ALTERNATE_GED)
        indiv, _, _, _, _, _, _, _ = build_model(p, "", "")
        assert all(not i["dna_markers"] for i in indiv.values())

    def test_derive_dna_flags_tuple_and_list_equivalent(self):
        raw_tuples = [
            (0, "@I1@", "INDI", ""),
            (1, None, "FACT", "Shared 120 cM"),
            (2, None, "TYPE", "DNA"),
        ]
        raw_lists = [list(t) for t in raw_tuples]
        kwargs = dict(
            dna_keyword="DNA", page_marker="AncestryDNA",
            scan_alternate=True,
            alternate_fields=parser_mod.DEFAULT_ALTERNATE_FIELDS)
        markers_t, tags_t = parser_mod.derive_dna_flags(raw_tuples, {}, **kwargs)
        markers_l, tags_l = parser_mod.derive_dna_flags(raw_lists, {}, **kwargs)
        assert markers_t == markers_l and markers_t
        assert tags_t == tags_l


# ===========================================================================
# neighbors
# ===========================================================================

class TestNeighbors:
    def setup_method(self):
        self.indiv = {
            "@ME@":     _make_indi("@ME@", "Me", "M", famc=["@F1@"], fams=["@F2@"]),
            "@DAD@":    _make_indi("@DAD@", "Dad", "M", fams=["@F1@"]),
            "@MOM@":    _make_indi("@MOM@", "Mom", "F", fams=["@F1@"]),
            "@SIB@":    _make_indi("@SIB@", "Sibling", "F", famc=["@F1@"]),
            "@SPOUSE@": _make_indi("@SPOUSE@", "Spouse", "F", fams=["@F2@"]),
            "@CHILD@":  _make_indi("@CHILD@", "Child", "M", famc=["@F2@"]),
        }
        self.fams = {
            "@F1@": _make_fam("@F1@", husb="@DAD@", wife="@MOM@",
                              chil=["@ME@", "@SIB@"]),
            "@F2@": _make_fam("@F2@", husb="@ME@", wife="@SPOUSE@",
                              chil=["@CHILD@"]),
        }

    def test_father_edge(self):
        nb = dict(neighbors("@ME@", self.indiv, self.fams))
        assert nb.get("@DAD@") == "father"

    def test_mother_edge(self):
        nb = dict(neighbors("@ME@", self.indiv, self.fams))
        assert nb.get("@MOM@") == "mother"

    def test_sibling_edge(self):
        nb = dict(neighbors("@ME@", self.indiv, self.fams))
        assert nb.get("@SIB@") == "sibling"

    def test_spouse_edge(self):
        nb = dict(neighbors("@ME@", self.indiv, self.fams))
        assert nb.get("@SPOUSE@") == "spouse"

    def test_child_edge(self):
        nb = dict(neighbors("@ME@", self.indiv, self.fams))
        assert nb.get("@CHILD@") == "child"

    def test_missing_person_yields_nothing(self):
        result = list(neighbors("@NOBODY@", self.indiv, self.fams))
        assert result == []

    def test_self_not_yielded_as_sibling(self):
        nb = dict(neighbors("@SIB@", self.indiv, self.fams))
        assert "@SIB@" not in nb

    def test_missing_family_reference_skipped(self):
        # Individual references a family that doesn't exist
        indi = {"@ORPHAN@": _make_indi("@ORPHAN@", famc=["@NONEXISTENT_FAM@"])}
        result = list(neighbors("@ORPHAN@", indi, {}))
        assert result == []


# ===========================================================================
# bfs_find_dna_matches
# ===========================================================================

class TestBfsFindDnaMatches:
    def setup_method(self):
        # Chain: @ME@ → @CHILD@ (child) → @GC@ (child, DNA-flagged)
        self.indiv = {
            "@ME@":    _make_indi("@ME@", "Me", "M", fams=["@F1@"]),
            "@CHILD@": _make_indi("@CHILD@", "Child", "F", famc=["@F1@"],
                                  fams=["@F2@"]),
            "@GC@":    _make_indi("@GC@", "Grandchild", "M", famc=["@F2@"],
                                  dna_markers=["DNA tag"]),
        }
        self.fams = {
            "@F1@": _make_fam("@F1@", husb="@ME@", chil=["@CHILD@"]),
            "@F2@": _make_fam("@F2@", husb="@CHILD@", chil=["@GC@"]),
        }

    def test_finds_dna_match_at_correct_distance(self):
        results = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                       top_n=5, max_depth=50)
        assert len(results) == 1
        dist, path = results[0]
        assert dist == 2

    def test_path_ends_at_dna_match(self):
        results = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                       top_n=5, max_depth=50)
        assert results[0][1][-1][0] == "@GC@"

    def test_path_starts_at_start_node(self):
        results = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                       top_n=5, max_depth=50)
        assert results[0][1][0][0] == "@ME@"

    def test_returns_empty_for_unknown_start(self):
        results = bfs_find_dna_matches("@UNKNOWN@", self.indiv, self.fams,
                                       top_n=5, max_depth=50)
        assert results == []

    def test_depth_limit_prevents_finding_distant_match(self):
        results = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                       top_n=5, max_depth=1)
        assert results == []

    def test_top_n_limits_results(self):
        # Add a second DNA match at the same depth
        self.indiv["@GC2@"] = _make_indi("@GC2@", "GC2", "F", famc=["@F2@"],
                                          dna_markers=["DNA tag"])
        self.fams["@F2@"]["chil"].append("@GC2@")
        results = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                       top_n=1, max_depth=50)
        assert len(results) == 1

    @pytest.mark.parametrize(
        ("top_n", "max_depth"),
        [(0, 50), (-1, 50), (5, 0), (5, -1), ("abc", 50)],
    )
    def test_rejects_non_positive_limits(self, top_n, max_depth):
        with pytest.raises(ValueError):
            bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                 top_n=top_n, max_depth=max_depth)

    def test_returns_empty_when_no_dna_markers(self):
        results = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                       top_n=5, max_depth=50)
        # GC is the only match; remove it and check empty result
        self.indiv["@GC@"]["dna_markers"] = []
        results2 = bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                        top_n=5, max_depth=50)
        assert results2 == []

    def test_cancel_event_stops_search(self):
        cancel_event = threading.Event()
        cancel_event.set()
        with pytest.raises(SearchCancelled):
            bfs_find_dna_matches("@ME@", self.indiv, self.fams,
                                 top_n=5, max_depth=50,
                                 cancel_event=cancel_event)


# ===========================================================================
# bfs_find_all_paths
# ===========================================================================

class TestBfsFindAllPaths:
    def setup_method(self):
        # Chain: @A@ → @B@ (child) → @C@ (child)
        self.indiv = {
            "@A@": _make_indi("@A@", "A", "M", fams=["@F1@"]),
            "@B@": _make_indi("@B@", "B", "M", famc=["@F1@"], fams=["@F2@"]),
            "@C@": _make_indi("@C@", "C", "F", famc=["@F2@"]),
            "@X@": _make_indi("@X@", "X", "F"),  # disconnected
        }
        self.fams = {
            "@F1@": _make_fam("@F1@", husb="@A@", chil=["@B@"]),
            "@F2@": _make_fam("@F2@", husb="@B@", chil=["@C@"]),
        }

    def test_same_start_and_end(self):
        paths, trunc = bfs_find_all_paths("@A@", "@A@", self.indiv, self.fams)
        # Returns [[(start_id, None)]]
        assert len(paths) == 1
        assert paths[0][0][0] == "@A@"
        assert trunc is False

    @pytest.mark.parametrize(
        ("top_n", "max_depth"),
        [(0, 50), (-1, 50), (5, 0), (5, -1), ("abc", 50)],
    )
    def test_rejects_non_positive_limits(self, top_n, max_depth):
        with pytest.raises(ValueError):
            bfs_find_all_paths("@A@", "@C@", self.indiv, self.fams,
                               top_n=top_n, max_depth=max_depth)

    def test_finds_direct_path(self):
        paths, _ = bfs_find_all_paths("@A@", "@C@", self.indiv, self.fams)
        assert len(paths) >= 1
        assert paths[0][0][0] == "@A@"
        assert paths[0][-1][0] == "@C@"

    def test_path_length_matches_distance(self):
        # A→B→C has distance 2, so path has 3 nodes
        paths, _ = bfs_find_all_paths("@A@", "@C@", self.indiv, self.fams)
        assert len(paths[0]) == 3

    def test_unknown_start_returns_empty(self):
        paths, trunc = bfs_find_all_paths("@UNKNOWN@", "@C@",
                                          self.indiv, self.fams)
        assert paths == []
        assert trunc is False

    def test_unknown_end_returns_empty(self):
        paths, trunc = bfs_find_all_paths("@A@", "@UNKNOWN@",
                                          self.indiv, self.fams)
        assert paths == []
        assert trunc is False

    def test_disconnected_nodes_returns_empty(self):
        paths, _ = bfs_find_all_paths("@A@", "@X@", self.indiv, self.fams)
        assert paths == []

    def test_edge_labels_on_path(self):
        paths, _ = bfs_find_all_paths("@A@", "@C@", self.indiv, self.fams)
        path = paths[0]
        # path[0] = (start, None), path[1] = (B, 'child'), path[2] = (C, 'child')
        assert path[0][1] is None
        assert path[1][1] == "child"
        assert path[2][1] == "child"

    def test_cancel_event_stops_path_search(self):
        cancel_event = threading.Event()
        cancel_event.set()
        with pytest.raises(SearchCancelled):
            bfs_find_all_paths("@A@", "@C@", self.indiv, self.fams,
                               cancel_event=cancel_event)


# ===========================================================================
# lifespan / describe
# ===========================================================================

class TestLifespan:
    def _i(self, b=None, d=None):
        return {"birth_year": b, "death_year": d}

    def test_both_years(self):
        assert lifespan(self._i(1950, 2020)) == "1950-2020"

    def test_birth_only(self):
        assert lifespan(self._i(1950)) == "b. 1950"

    def test_death_only(self):
        assert lifespan(self._i(d=2020)) == "d. 2020"

    def test_neither(self):
        assert lifespan(self._i()) == ""

    def test_bce_birth_and_death(self):
        # Born 100 BC, died 44 BC.
        assert lifespan(self._i(-100, -44)) == "100 BC-44 BC"

    def test_bce_birth_only(self):
        assert lifespan(self._i(-44)) == "b. 44 BC"

    def test_bce_to_ce_span(self):
        # Spanning the BCE/CE boundary, e.g. born 4 BC, died AD 30.
        assert lifespan(self._i(-4, 30)) == "4 BC-30"


class TestFormatYear:
    def test_none(self):
        assert format_year(None) == ""

    def test_positive(self):
        assert format_year(1950) == "1950"

    def test_negative_is_bce(self):
        assert format_year(-44) == "44 BC"

    def test_single_digit_bce(self):
        assert format_year(-1) == "1 BC"


class TestDescribe:
    def _i(self, name="", b=None, d=None, id="@I1@"):
        return {"id": id, "name": name, "birth_year": b, "death_year": d}

    def test_name_lifespan_and_id(self):
        r = describe(self._i("John Smith", 1950, 2020))
        assert "John Smith" in r
        assert "1950-2020" in r
        assert "@I1@" in r

    def test_name_no_lifespan_with_id(self):
        r = describe(self._i("Jane Doe"))
        assert "Jane Doe" in r
        assert "@I1@" in r

    def test_without_id(self):
        r = describe(self._i("Jane Doe", 1952), show_id=False)
        assert "@I1@" not in r
        assert "Jane Doe" in r

    def test_unknown_name_placeholder(self):
        r = describe(self._i(""))
        assert "(unknown)" in r

    def test_no_lifespan_no_parens_when_show_id_false(self):
        r = describe(self._i("Test Person"), show_id=False)
        assert r == "Test Person"


# ===========================================================================
# extract_ged_from_zip
# ===========================================================================

class TestExtractGedFromZip:
    def _make_zip(self, tmp_path, entries):
        """Create a ZIP file; entries = {name: content_bytes}."""
        zpath = tmp_path / "test.zip"
        with zipfile.ZipFile(str(zpath), "w") as zf:
            for name, content in entries.items():
                zf.writestr(name, content)
        return str(zpath)

    def test_extracts_ged_entry(self, tmp_path):
        zpath = self._make_zip(tmp_path, {"family.ged": b"0 HEAD\n0 TRLR\n"})
        ged_path, entry = extract_ged_from_zip(zpath)
        try:
            assert entry == "family.ged"
            assert os.path.exists(ged_path)
        finally:
            os.unlink(ged_path)

    def test_gedcom_extension_accepted(self, tmp_path):
        zpath = self._make_zip(tmp_path, {"family.gedcom": b"0 HEAD\n0 TRLR\n"})
        ged_path, entry = extract_ged_from_zip(zpath)
        try:
            assert entry == "family.gedcom"
        finally:
            os.unlink(ged_path)

    def test_prefers_top_level_over_nested(self, tmp_path):
        zpath = self._make_zip(tmp_path, {
            "subdir/deep.ged": b"0 HEAD\n0 TRLR\n",
            "top.ged": b"0 HEAD\n0 TRLR\n",
        })
        ged_path, entry = extract_ged_from_zip(zpath)
        try:
            assert entry == "top.ged"
        finally:
            os.unlink(ged_path)

    def test_raises_when_no_ged_in_zip(self, tmp_path):
        zpath = self._make_zip(tmp_path, {"readme.txt": b"hello"})
        with pytest.raises(ValueError, match="No .ged"):
            extract_ged_from_zip(zpath)

    def test_extracted_content_matches_original(self, tmp_path):
        original = b"0 HEAD\n0 @I1@ INDI\n1 NAME Test\n0 TRLR\n"
        zpath = self._make_zip(tmp_path, {"data.ged": original})
        ged_path, _ = extract_ged_from_zip(zpath)
        try:
            assert open(ged_path, "rb").read() == original
        finally:
            os.unlink(ged_path)

    def test_rejects_entry_larger_than_limit(self, tmp_path, monkeypatch):
        import gedcom_parser  # pylint: disable=import-outside-toplevel

        monkeypatch.setattr(gedcom_parser, "ZIP_MAX_BYTES", 10)
        zpath = self._make_zip(tmp_path, {"data.ged": b"0 HEAD\n0 TRLR\n"})
        with pytest.raises(ValueError, match="exceed"):
            extract_ged_from_zip(zpath)

    def test_cancel_event_stops_zip_extraction(self, tmp_path):
        cancel_event = threading.Event()
        cancel_event.set()
        zpath = self._make_zip(tmp_path, {"data.ged": b"0 HEAD\n0 TRLR\n"})
        with pytest.raises(InterruptedError):
            extract_ged_from_zip(zpath, cancel_event=cancel_event)
