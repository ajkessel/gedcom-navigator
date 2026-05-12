"""Tests for gedcom_relationship.py — plain-English relationship descriptions."""
import pytest

from gedcom_relationship import (
    _edge_to_term,
    _nth_great,
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _i(sex=""):
    """Minimal individual dict (only 'sex' is needed by describe_relationship)."""
    return {"sex": sex}


def _path(*steps):
    """Build a path list from alternating (id, edge) pairs.

    Usage: _path('@A@', None, '@B@', 'father', '@C@', 'sibling')
    Yields: [('@A@', None), ('@B@', 'father'), ('@C@', 'sibling')]
    """
    it = iter(steps)
    return [(nid, edge) for nid, edge in zip(it, it)]


def _make_indi_full(id, sex="", famc=None, fams=None):
    return {
        "id": id, "name": id, "surname": "", "given_name": "",
        "alt_names": [], "sex": sex,
        "famc": famc or [], "fams": fams or [],
        "dna_markers": [], "birth_year": None, "death_year": None, "_raw": [],
    }


def _make_fam(id, husb=None, wife=None, chil=None):
    return {"id": id, "husb": husb, "wife": wife, "chil": chil or [],
            "marr_date": "", "marr_place": ""}


# ===========================================================================
# _nth_great
# ===========================================================================

class TestNthGreat:
    def test_zero_returns_empty(self):
        assert _nth_great(0) == ""

    def test_one_returns_great(self):
        assert _nth_great(1) == "great-"

    def test_two_returns_2nd_great(self):
        assert _nth_great(2) == "2nd-great-"

    def test_three_returns_3rd_great(self):
        assert _nth_great(3) == "3rd-great-"

    def test_four_returns_4th_great(self):
        assert _nth_great(4) == "4th-great-"

    def test_eleven_uses_th_not_st(self):
        # 11 → 11th (not 11st)
        assert _nth_great(11) == "11th-great-"

    def test_twelve_uses_th(self):
        assert _nth_great(12) == "12th-great-"

    def test_thirteen_uses_th(self):
        assert _nth_great(13) == "13th-great-"

    def test_twenty_one_uses_st(self):
        assert _nth_great(21) == "21st-great-"


# ===========================================================================
# _edge_to_term
# ===========================================================================

class TestEdgeToTerm:
    def test_father_edge(self):
        assert _edge_to_term("father", "M") == "father"

    def test_mother_edge(self):
        assert _edge_to_term("mother", "F") == "mother"

    def test_sibling_male(self):
        assert _edge_to_term("sibling", "M") == "brother"

    def test_sibling_female(self):
        assert _edge_to_term("sibling", "F") == "sister"

    def test_sibling_unknown_sex(self):
        assert _edge_to_term("sibling", "") == "sibling"

    def test_child_male(self):
        assert _edge_to_term("child", "M") == "son"

    def test_child_female(self):
        assert _edge_to_term("child", "F") == "daughter"

    def test_child_unknown_sex(self):
        assert _edge_to_term("child", "") == "child"

    def test_spouse_male(self):
        assert _edge_to_term("spouse", "M") == "husband"

    def test_spouse_female(self):
        assert _edge_to_term("spouse", "F") == "wife"

    def test_spouse_unknown(self):
        assert _edge_to_term("spouse", "") == "spouse"


# ===========================================================================
# describe_relationship
# ===========================================================================

class TestSamePerson:
    def test_single_node_path(self):
        indiv = {"@A@": _i("M")}
        assert describe_relationship([("@A@", None)], indiv) == "same person"


class TestDirectAncestors:
    def test_father(self):
        indiv = {"@ME@": _i("M"), "@DAD@": _i("M")}
        path = _path("@ME@", None, "@DAD@", "father")
        assert describe_relationship(path, indiv) == "father"

    def test_mother(self):
        indiv = {"@ME@": _i("M"), "@MOM@": _i("F")}
        path = _path("@ME@", None, "@MOM@", "mother")
        assert describe_relationship(path, indiv) == "mother"

    def test_grandfather(self):
        indiv = {"@ME@": _i(), "@DAD@": _i(), "@GP@": _i("M")}
        path = _path("@ME@", None, "@DAD@", "father", "@GP@", "father")
        assert describe_relationship(path, indiv) == "grandfather"

    def test_grandmother(self):
        indiv = {"@ME@": _i(), "@DAD@": _i(), "@GM@": _i("F")}
        path = _path("@ME@", None, "@DAD@", "father", "@GM@", "mother")
        assert describe_relationship(path, indiv) == "grandmother"

    def test_great_grandfather(self):
        indiv = {k: _i("M") for k in ["@ME@", "@D1@", "@D2@", "@GGP@"]}
        path = _path("@ME@", None, "@D1@", "father", "@D2@", "father",
                     "@GGP@", "father")
        assert describe_relationship(path, indiv) == "great-grandfather"

    def test_2nd_great_grandfather(self):
        ids = ["@ME@", "@D1@", "@D2@", "@D3@", "@GGGGP@"]
        indiv = {k: _i("M") for k in ids}
        path = _path("@ME@", None, "@D1@", "father", "@D2@", "father",
                     "@D3@", "father", "@GGGGP@", "father")
        assert describe_relationship(path, indiv) == "2nd-great-grandfather"

    def test_unknown_sex_ancestor_uses_neutral_term(self):
        indiv = {"@ME@": _i(), "@PAR@": _i("")}
        path = _path("@ME@", None, "@PAR@", "father")
        assert describe_relationship(path, indiv) == "parent"


class TestDirectDescendants:
    def test_son(self):
        indiv = {"@ME@": _i("M"), "@SON@": _i("M")}
        path = _path("@ME@", None, "@SON@", "child")
        assert describe_relationship(path, indiv) == "son"

    def test_daughter(self):
        indiv = {"@ME@": _i("M"), "@DAUG@": _i("F")}
        path = _path("@ME@", None, "@DAUG@", "child")
        assert describe_relationship(path, indiv) == "daughter"

    def test_grandson(self):
        indiv = {"@ME@": _i(), "@C@": _i(), "@GS@": _i("M")}
        path = _path("@ME@", None, "@C@", "child", "@GS@", "child")
        assert describe_relationship(path, indiv) == "grandson"

    def test_granddaughter(self):
        indiv = {"@ME@": _i(), "@C@": _i(), "@GD@": _i("F")}
        path = _path("@ME@", None, "@C@", "child", "@GD@", "child")
        assert describe_relationship(path, indiv) == "granddaughter"

    def test_great_granddaughter(self):
        indiv = {k: _i("F") for k in ["@ME@", "@C@", "@GC@", "@GGC@"]}
        path = _path("@ME@", None, "@C@", "child", "@GC@", "child",
                     "@GGC@", "child")
        result = describe_relationship(path, indiv)
        assert result == "great-granddaughter"

    def test_unknown_sex_descendant(self):
        indiv = {"@ME@": _i(), "@C@": _i("")}
        path = _path("@ME@", None, "@C@", "child")
        assert describe_relationship(path, indiv) == "child"


class TestSiblingsAndSpouses:
    def test_brother(self):
        indiv = {"@ME@": _i(), "@BRO@": _i("M")}
        path = _path("@ME@", None, "@BRO@", "sibling")
        assert describe_relationship(path, indiv) == "brother"

    def test_sister(self):
        indiv = {"@ME@": _i(), "@SIS@": _i("F")}
        path = _path("@ME@", None, "@SIS@", "sibling")
        assert describe_relationship(path, indiv) == "sister"

    def test_sibling_unknown_sex(self):
        indiv = {"@ME@": _i(), "@SIB@": _i("")}
        path = _path("@ME@", None, "@SIB@", "sibling")
        assert describe_relationship(path, indiv) == "sibling"

    def test_husband(self):
        indiv = {"@WIFE@": _i("F"), "@HUSB@": _i("M")}
        path = _path("@WIFE@", None, "@HUSB@", "spouse")
        assert describe_relationship(path, indiv) == "husband"

    def test_wife(self):
        indiv = {"@HUSB@": _i("M"), "@WIFE@": _i("F")}
        path = _path("@HUSB@", None, "@WIFE@", "spouse")
        assert describe_relationship(path, indiv) == "wife"


class TestUnclesAndAunts:
    def test_uncle(self):
        # Me → Dad (father) → Uncle (sibling)
        indiv = {"@ME@": _i(), "@DAD@": _i(), "@UNCLE@": _i("M")}
        path = _path("@ME@", None, "@DAD@", "father", "@UNCLE@", "sibling")
        assert describe_relationship(path, indiv) == "uncle"

    def test_aunt(self):
        indiv = {"@ME@": _i(), "@DAD@": _i(), "@AUNT@": _i("F")}
        path = _path("@ME@", None, "@DAD@", "father", "@AUNT@", "sibling")
        assert describe_relationship(path, indiv) == "aunt"

    def test_great_uncle(self):
        # Me → Dad → Grandpa → Great-uncle (sibling of grandpa)
        indiv = {"@ME@": _i(), "@D@": _i(), "@GP@": _i(), "@GU@": _i("M")}
        path = _path("@ME@", None, "@D@", "father", "@GP@", "father",
                     "@GU@", "sibling")
        assert describe_relationship(path, indiv) == "great-uncle"

    def test_great_aunt(self):
        indiv = {"@ME@": _i(), "@D@": _i(), "@GP@": _i(), "@GA@": _i("F")}
        path = _path("@ME@", None, "@D@", "father", "@GP@", "father",
                     "@GA@", "sibling")
        assert describe_relationship(path, indiv) == "great-aunt"


class TestNephewsAndNieces:
    def test_nephew(self):
        # Me → Sibling → Nephew (child)
        indiv = {"@ME@": _i(), "@SIB@": _i(), "@NEPHEW@": _i("M")}
        path = _path("@ME@", None, "@SIB@", "sibling", "@NEPHEW@", "child")
        assert describe_relationship(path, indiv) == "nephew"

    def test_niece(self):
        indiv = {"@ME@": _i(), "@SIB@": _i(), "@NIECE@": _i("F")}
        path = _path("@ME@", None, "@SIB@", "sibling", "@NIECE@", "child")
        assert describe_relationship(path, indiv) == "niece"


class TestCousins:
    def test_first_cousin_male(self):
        # Me → Dad (father) → Uncle (sibling) → Cousin (child)
        indiv = {"@ME@": _i(), "@D@": _i(), "@U@": _i(), "@C@": _i("M")}
        path = _path("@ME@", None, "@D@", "father", "@U@", "sibling",
                     "@C@", "child")
        assert describe_relationship(path, indiv) == "first cousin"

    def test_first_cousin_female(self):
        indiv = {"@ME@": _i(), "@D@": _i(), "@U@": _i(), "@C@": _i("F")}
        path = _path("@ME@", None, "@D@", "father", "@U@", "sibling",
                     "@C@", "child")
        assert describe_relationship(path, indiv) == "first cousin"

    def test_second_cousin(self):
        # Me → Dad → Grandpa → Sibling of Grandpa → Child → Second Cousin
        indiv = {k: _i() for k in ["@ME@", "@D@", "@GP@", "@GA@",
                                    "@AC@", "@C2@"]}
        path = _path("@ME@", None, "@D@", "father", "@GP@", "father",
                     "@GA@", "sibling", "@AC@", "child", "@C2@", "child")
        assert describe_relationship(path, indiv) == "second cousin"

    def test_first_cousin_once_removed_down(self):
        # Me → Dad → Uncle → Cousin → Cousin's child
        indiv = {k: _i() for k in ["@ME@", "@D@", "@U@", "@C@", "@CC@"]}
        path = _path("@ME@", None, "@D@", "father", "@U@", "sibling",
                     "@C@", "child", "@CC@", "child")
        assert describe_relationship(path, indiv) == "first cousin once removed"

    def test_first_cousin_once_removed_up(self):
        # Me → Dad → Grandpa → Uncle of grandpa's gen → Cousin of that uncle
        indiv = {k: _i() for k in ["@ME@", "@D@", "@GP@", "@GU@", "@C@"]}
        path = _path("@ME@", None, "@D@", "father", "@GP@", "father",
                     "@GU@", "sibling", "@C@", "child")
        assert describe_relationship(path, indiv) == "first cousin once removed"

    def test_second_cousin_once_removed(self):
        indiv = {k: _i() for k in ["@ME@", "@D@", "@GP@", "@GGA@",
                                    "@AC@", "@C2@", "@CC2@"]}
        path = _path("@ME@", None, "@D@", "father", "@GP@", "father",
                     "@GGA@", "sibling", "@AC@", "child", "@C2@", "child",
                     "@CC2@", "child")
        assert describe_relationship(path, indiv) == "second cousin once removed"


class TestInLawsAndStepRelations:
    def test_father_in_law(self):
        # Me → Spouse (spouse) → Father-in-law (father)
        indiv = {"@ME@": _i(), "@SP@": _i(), "@FIL@": _i("M")}
        path = _path("@ME@", None, "@SP@", "spouse", "@FIL@", "father")
        assert describe_relationship(path, indiv) == "father-in-law"

    def test_mother_in_law(self):
        indiv = {"@ME@": _i(), "@SP@": _i(), "@MIL@": _i("F")}
        path = _path("@ME@", None, "@SP@", "spouse", "@MIL@", "mother")
        assert describe_relationship(path, indiv) == "mother-in-law"

    def test_son_in_law(self):
        # Me → Child (child) → Child's spouse (spouse)
        indiv = {"@ME@": _i(), "@C@": _i(), "@SIL@": _i("M")}
        path = _path("@ME@", None, "@C@", "child", "@SIL@", "spouse")
        assert describe_relationship(path, indiv) == "son-in-law"

    def test_daughter_in_law(self):
        indiv = {"@ME@": _i(), "@C@": _i(), "@DIL@": _i("F")}
        path = _path("@ME@", None, "@C@", "child", "@DIL@", "spouse")
        assert describe_relationship(path, indiv) == "daughter-in-law"

    def test_brother_in_law(self):
        # Me → Spouse (spouse) → Sibling of spouse (sibling)
        indiv = {"@ME@": _i(), "@SP@": _i(), "@BIL@": _i("M")}
        path = _path("@ME@", None, "@SP@", "spouse", "@BIL@", "sibling")
        assert describe_relationship(path, indiv) == "brother-in-law"

    def test_sister_in_law(self):
        indiv = {"@ME@": _i(), "@SP@": _i(), "@SIL@": _i("F")}
        path = _path("@ME@", None, "@SP@", "spouse", "@SIL@", "sibling")
        assert describe_relationship(path, indiv) == "sister-in-law"

    def test_step_father(self):
        # Me → Dad (father) → Dad's new spouse who is M
        indiv = {"@ME@": _i(), "@DAD@": _i(), "@STEPDAD@": _i("M")}
        path = _path("@ME@", None, "@DAD@", "father", "@STEPDAD@", "spouse")
        result = describe_relationship(path, indiv)
        assert result == "step-father"

    def test_step_mother(self):
        # Me → Mom (mother) → Mom's new spouse who is F
        indiv = {"@ME@": _i(), "@MOM@": _i(), "@STEPMOM@": _i("F")}
        path = _path("@ME@", None, "@MOM@", "mother", "@STEPMOM@", "spouse")
        result = describe_relationship(path, indiv)
        assert result == "step-mother"


class TestAncestorDescendantOverride:
    """When ancestors/descendants dicts are provided, they override path classification."""

    def test_ancestors_dict_overrides_for_known_ancestor(self):
        # Path goes through spouse but target is a known ancestor
        indiv = {"@ME@": _i(), "@SP@": _i(), "@ANCP@": _i("M")}
        path = _path("@ME@", None, "@SP@", "spouse", "@ANCP@", "father")
        # Without override: father-in-law
        assert describe_relationship(path, indiv) == "father-in-law"
        # With ancestors override: father
        ancestors = {"@ANCP@": 1}
        assert describe_relationship(path, indiv, ancestors=ancestors) == "father"

    def test_descendants_dict_overrides(self):
        indiv = {"@ME@": _i(), "@C@": _i(), "@GC@": _i("M")}
        path = _path("@ME@", None, "@C@", "child", "@GC@", "child")
        # Without override already returns grandson
        descendants = {"@GC@": 2}
        result = describe_relationship(path, indiv, descendants=descendants)
        assert result == "grandson"


# ===========================================================================
# get_ancestor_depths / get_descendant_depths
# ===========================================================================

class TestGetAncestorDepths:
    def setup_method(self):
        # @ME@ → @DAD@ → @GRANDPA@
        self.indiv = {
            "@ME@":      _make_indi_full("@ME@", famc=["@F1@"]),
            "@DAD@":     _make_indi_full("@DAD@", "M", famc=["@F2@"], fams=["@F1@"]),
            "@MOM@":     _make_indi_full("@MOM@", "F", fams=["@F1@"]),
            "@GRANDPA@": _make_indi_full("@GRANDPA@", "M", fams=["@F2@"]),
        }
        self.fams = {
            "@F1@": _make_fam("@F1@", husb="@DAD@", wife="@MOM@",
                              chil=["@ME@"]),
            "@F2@": _make_fam("@F2@", husb="@GRANDPA@", chil=["@DAD@"]),
        }

    def test_father_at_depth_1(self):
        depths = get_ancestor_depths("@ME@", self.indiv, self.fams)
        assert depths.get("@DAD@") == 1

    def test_mother_at_depth_1(self):
        depths = get_ancestor_depths("@ME@", self.indiv, self.fams)
        assert depths.get("@MOM@") == 1

    def test_grandfather_at_depth_2(self):
        depths = get_ancestor_depths("@ME@", self.indiv, self.fams)
        assert depths.get("@GRANDPA@") == 2

    def test_start_not_in_result(self):
        depths = get_ancestor_depths("@ME@", self.indiv, self.fams)
        assert "@ME@" not in depths

    def test_empty_tree_returns_empty(self):
        indiv = {"@LONE@": _make_indi_full("@LONE@")}
        depths = get_ancestor_depths("@LONE@", indiv, {})
        assert depths == {}


class TestGetDescendantDepths:
    def setup_method(self):
        # @GRANDPA@ → @DAD@ → @ME@ → @CHILD@
        self.indiv = {
            "@GRANDPA@": _make_indi_full("@GRANDPA@", "M", fams=["@F1@"]),
            "@DAD@":     _make_indi_full("@DAD@", "M", famc=["@F1@"],
                                          fams=["@F2@"]),
            "@ME@":      _make_indi_full("@ME@", famc=["@F2@"], fams=["@F3@"]),
            "@CHILD@":   _make_indi_full("@CHILD@", "F", famc=["@F3@"]),
        }
        self.fams = {
            "@F1@": _make_fam("@F1@", husb="@GRANDPA@", chil=["@DAD@"]),
            "@F2@": _make_fam("@F2@", husb="@DAD@", chil=["@ME@"]),
            "@F3@": _make_fam("@F3@", husb="@ME@", chil=["@CHILD@"]),
        }

    def test_child_at_depth_1(self):
        depths = get_descendant_depths("@GRANDPA@", self.indiv, self.fams)
        assert depths.get("@DAD@") == 1

    def test_grandchild_at_depth_2(self):
        depths = get_descendant_depths("@GRANDPA@", self.indiv, self.fams)
        assert depths.get("@ME@") == 2

    def test_great_grandchild_at_depth_3(self):
        depths = get_descendant_depths("@GRANDPA@", self.indiv, self.fams)
        assert depths.get("@CHILD@") == 3

    def test_start_not_in_result(self):
        depths = get_descendant_depths("@GRANDPA@", self.indiv, self.fams)
        assert "@GRANDPA@" not in depths

    def test_leaf_node_returns_empty(self):
        depths = get_descendant_depths("@CHILD@", self.indiv, self.fams)
        assert depths == {}
