"""Tests for gedcom_data_model.py — caching layer and BFS wrapper."""
import time

import pytest

from gedcom_data_model import GedcomDataModel


# ---------------------------------------------------------------------------
# GEDCOM fixture content
# ---------------------------------------------------------------------------

# cspell: disable
SIMPLE_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Alice /Smith/
1 SEX F
1 BIRT
2 DATE 1975
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 BIRT
2 DATE 1970
1 FAMS @F1@
0 @I3@ INDI
1 NAME Carol /Smith/
1 SEX F
1 FAMC @F1@
1 _MTTAG @T1@
0 @T1@ _MTTAG
1 NAME DNA Test Tag
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 CHIL @I3@
0 TRLR
"""
# cspell: enable

def _write_ged(tmp_path, content="", filename="tree.ged"):
    p = tmp_path / filename
    p.write_text(content or SIMPLE_GED, encoding="utf-8")
    return str(p)


# ===========================================================================
# Initialization
# ===========================================================================

class TestInit:
    def test_starts_empty(self):
        mdl = GedcomDataModel()
        assert mdl.individuals == {}
        assert mdl.families == {}
        assert mdl.tag_records == {}
        assert mdl.married_name_index == {}


# ===========================================================================
# load — fresh parse
# ===========================================================================

class TestLoad:
    def test_fresh_parse_returns_false_from_cache(self, tmp_path):
        mdl = GedcomDataModel()
        p = _write_ged(tmp_path)
        from_cache, warn, error = mdl.load(p, "DNA", "AncestryDNA",
                                            str(tmp_path / "cache"))
        assert from_cache is False
        assert warn is None
        assert error is None

    def test_individuals_populated_after_load(self, tmp_path):
        mdl = GedcomDataModel()
        p = _write_ged(tmp_path)
        mdl.load(p, "DNA", "AncestryDNA", str(tmp_path / "cache"))
        assert "@I1@" in mdl.individuals
        assert "@I2@" in mdl.individuals
        assert "@I3@" in mdl.individuals

    def test_families_populated_after_load(self, tmp_path):
        mdl = GedcomDataModel()
        p = _write_ged(tmp_path)
        mdl.load(p, "DNA", "AncestryDNA", str(tmp_path / "cache"))
        assert "@F1@" in mdl.families

    def test_clean_file_no_encoding_warning(self, tmp_path):
        mdl = GedcomDataModel()
        p = _write_ged(tmp_path)
        _, warn, error = mdl.load(p, "DNA", "AncestryDNA", str(tmp_path / "cache"))
        assert warn is None
        assert error is None

    def test_married_name_index_built_after_load(self, tmp_path):
        mdl = GedcomDataModel()
        p = _write_ged(tmp_path)
        mdl.load(p, "DNA", "AncestryDNA", str(tmp_path / "cache"))
        assert mdl.married_name_index == {"@I1@": ["Alice Jones"]}

    def test_invalid_file_returns_model_error(self, tmp_path):
        mdl = GedcomDataModel()
        p = _write_ged(tmp_path, "0 HEAD\n0 TRLR\n")
        from_cache, warn, error = mdl.load(
            p, "DNA", "AncestryDNA", str(tmp_path / "cache"))
        assert from_cache is False
        assert warn is None
        assert error is not None
        assert "No individual records" in error
        assert mdl.married_name_index == {}


# ===========================================================================
# Cache hit
# ===========================================================================

class TestCacheHit:
    def test_second_load_from_cache(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl1 = GedcomDataModel()
        mdl1.load(p, "DNA", "AncestryDNA", cache_dir)

        mdl2 = GedcomDataModel()
        from_cache, _, error = mdl2.load(p, "DNA", "AncestryDNA", cache_dir)
        assert from_cache is True
        assert error is None

    def test_cache_hit_returns_no_encoding_warning(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)
        _, warn, error = GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)
        assert warn is None
        assert error is None

    def test_cache_hit_preserves_individuals(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        assert "@I1@" in mdl.individuals

    def test_cache_hit_rebuilds_married_name_index(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)

        mdl = GedcomDataModel()
        from_cache, _, error = mdl.load(p, "DNA", "AncestryDNA", cache_dir)

        assert from_cache is True
        assert error is None
        assert mdl.married_name_index == {"@I1@": ["Alice Jones"]}


# ===========================================================================
# Cache invalidation
# ===========================================================================

class TestCacheInvalidation:
    def test_changed_dna_keyword_invalidates_cache(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)
        from_cache, _, _ = GedcomDataModel().load(p, "DIFFERENT", "AncestryDNA",
                                                   cache_dir)
        assert from_cache is False

    def test_changed_page_marker_invalidates_cache(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)
        from_cache, _, _ = GedcomDataModel().load(p, "DNA", "OtherMarker",
                                                   cache_dir)
        assert from_cache is False

    def test_file_mtime_change_invalidates_cache(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        GedcomDataModel().load(p, "DNA", "AncestryDNA", cache_dir)
        # Touch the file to change mtime
        time.sleep(0.05)
        Path_p = __import__("pathlib").Path(p)
        Path_p.write_text(SIMPLE_GED, encoding="utf-8")
        from_cache, _, _ = GedcomDataModel().load(p, "DNA", "AncestryDNA",
                                                   cache_dir)
        assert from_cache is False

    def test_corrupted_cache_falls_back_to_parse(self, tmp_path):
        from gedcom_data_model import GedcomDataModel as GDM
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        p = _write_ged(tmp_path)
        # Pre-place a corrupted cache file
        import hashlib, os as _os
        key = _os.path.normcase(_os.path.abspath(p)).encode()
        fname = hashlib.md5(key).hexdigest() + ".json"
        (cache_dir / fname).write_text("not json", encoding="utf-8")
        mdl = GDM()
        from_cache, _, error = mdl.load(p, "DNA", "AncestryDNA", str(cache_dir))
        assert from_cache is False
        assert error is None
        assert "@I1@" in mdl.individuals


# ===========================================================================
# clear_cache
# ===========================================================================

class TestClearCache:
    def test_clears_json_files(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "a.json").write_text("{}")
        (cache_dir / "b.json").write_text("{}")
        mdl = GedcomDataModel()
        deleted = mdl.clear_cache(str(cache_dir))
        assert deleted == 2
        assert list(cache_dir.glob("*.json")) == []

    def test_non_json_files_untouched(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "a.json").write_text("{}")
        (cache_dir / "keep.txt").write_text("data")
        mdl = GedcomDataModel()
        mdl.clear_cache(str(cache_dir))
        assert (cache_dir / "keep.txt").exists()

    def test_nonexistent_dir_returns_zero(self, tmp_path):
        mdl = GedcomDataModel()
        count = mdl.clear_cache(str(tmp_path / "no_such_dir"))
        assert count == 0

    def test_returns_correct_count(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        for i in range(5):
            (cache_dir / f"{i}.json").write_text("{}")
        mdl = GedcomDataModel()
        assert mdl.clear_cache(str(cache_dir)) == 5


# ===========================================================================
# find_dna_matches / find_all_paths (integration with loaded data)
# ===========================================================================

class TestBfsIntegration:
    def setup_method(self):
        pass

    def test_find_dna_matches_returns_dna_individual(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        results = mdl.find_dna_matches("@I1@", top_n=5, max_depth=50)
        # @I3@ has the DNA marker; it's a child (distance 1 from @I1@)
        ids = [path[-1][0] for _, path in results]
        assert "@I3@" in ids

    def test_find_dna_matches_empty_for_unknown_start(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        assert mdl.find_dna_matches("@NOBODY@", top_n=5, max_depth=50) == []

    @pytest.mark.parametrize(
        ("top_n", "max_depth"),
        [(0, 50), (-1, 50), (5, 0), (5, -1), ("abc", 50)],
    )
    def test_find_dna_matches_rejects_non_positive_limits(
            self, tmp_path, top_n, max_depth):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        with pytest.raises(ValueError):
            mdl.find_dna_matches("@I1@", top_n=top_n, max_depth=max_depth)

    def test_find_all_paths_between_individuals(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        paths, _ = mdl.find_all_paths("@I1@", "@I3@", top_n=5, max_depth=50)
        assert len(paths) >= 1
        assert paths[0][-1][0] == "@I3@"

    def test_find_all_paths_same_person(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        paths, _ = mdl.find_all_paths("@I1@", "@I1@", top_n=5, max_depth=50)
        assert len(paths) == 1
        assert paths[0][0][0] == "@I1@"

    @pytest.mark.parametrize(
        ("top_n", "max_depth"),
        [(0, 50), (-1, 50), (5, 0), (5, -1), ("abc", 50)],
    )
    def test_find_all_paths_rejects_non_positive_limits(
            self, tmp_path, top_n, max_depth):
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)
        with pytest.raises(ValueError):
            mdl.find_all_paths("@I1@", "@I3@",
                               top_n=top_n, max_depth=max_depth)

    def test_find_common_ancestors_between_siblings(self, tmp_path):
        ged = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @DAD@ INDI
1 NAME Dad /Smith/
1 SEX M
1 FAMS @F1@
0 @MOM@ INDI
1 NAME Mom /Smith/
1 SEX F
1 FAMS @F1@
0 @A@ INDI
1 NAME Alice /Smith/
1 SEX F
1 FAMC @F1@
0 @B@ INDI
1 NAME Bob /Smith/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @DAD@
1 WIFE @MOM@
1 CHIL @A@
1 CHIL @B@
0 TRLR
"""
        cache_dir = str(tmp_path / "cache")
        p = _write_ged(tmp_path, ged)
        mdl = GedcomDataModel()
        mdl.load(p, "DNA", "AncestryDNA", cache_dir)

        assert mdl.find_common_ancestors("@A@", "@B@") == ["@DAD@", "@MOM@"]
