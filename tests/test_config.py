"""Tests for gedcom_config.py — typed settings persistence."""
import json
from pathlib import Path

import pytest

from gedcom_config import ConfigManager


def _mgr(tmp_path, filename="settings.json"):
    return ConfigManager(tmp_path / filename)


# ===========================================================================
# Generic load_value / save_value
# ===========================================================================

class TestLoadSaveValue:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.save_value("key", "hello")
        assert mgr.load_value("key") == "hello"

    def test_missing_key_returns_default(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.save_value("other", 1)
        assert mgr.load_value("missing", "fallback") == "fallback"

    def test_missing_file_returns_default(self, tmp_path):
        mgr = _mgr(tmp_path, "nonexistent.json")
        assert mgr.load_value("key", 99) == 99

    def test_corrupted_file_returns_default(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text("{ not valid json }", encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.load_value("key", "safe") == "safe"

    def test_save_preserves_other_keys(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.save_value("a", 1)
        mgr.save_value("b", 2)
        assert mgr.load_value("a") == 1
        assert mgr.load_value("b") == 2

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "settings.json"
        mgr = ConfigManager(nested)
        mgr.save_value("x", True)
        assert nested.exists()

    def test_overwrites_existing_key(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.save_value("k", "old")
        mgr.save_value("k", "new")
        assert mgr.load_value("k") == "new"


# ===========================================================================
# Recent files
# ===========================================================================

class TestRecentFiles:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        files = ["/a/b.ged", "/c/d.ged"]
        mgr.set_recent_files(files)
        assert mgr.get_recent_files() == files

    def test_filters_non_strings(self, tmp_path):
        mgr = _mgr(tmp_path)
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"recent_files": ["/a.ged", 42, None, "/b.ged"]}),
                     encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_recent_files() == ["/a.ged", "/b.ged"]

    def test_missing_returns_empty_list(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_recent_files() == []


# ===========================================================================
# Home person
# ===========================================================================

class TestHomePerson:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_home_person("/path/to/tree.ged", "@I42@")
        assert mgr.get_home_person("/path/to/tree.ged") == "@I42@"

    def test_different_paths_independent(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_home_person("/a.ged", "@I1@")
        mgr.set_home_person("/b.ged", "@I2@")
        assert mgr.get_home_person("/a.ged") == "@I1@"
        assert mgr.get_home_person("/b.ged") == "@I2@"

    def test_missing_path_returns_none(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_home_person("/no/such.ged") is None

    def test_unset_clears_home_person(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_home_person("/path/to/tree.ged", "@I42@")
        mgr.set_home_person("/path/to/tree.ged", None)
        assert mgr.get_home_person("/path/to/tree.ged") is None


# ===========================================================================
# Font preference
# ===========================================================================

class TestFontPreference:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_font_preference("large")
        assert mgr.get_font_preference(["small", "medium", "large"]) == "large"

    def test_invalid_falls_back_to_medium(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_font_preference("enormous")
        assert mgr.get_font_preference(["small", "medium", "large"]) == "medium"

    def test_missing_falls_back_to_medium(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_font_preference(["small", "medium", "large"]) == "medium"


# ===========================================================================
# Theme preference
# ===========================================================================

class TestThemePreference:
    THEMES = ["System", "Light", "Dark", "Blue", "Green"]

    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_theme_preference("Dark")
        assert mgr.get_theme_preference(self.THEMES) == "Dark"

    def test_invalid_falls_back_to_system(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_theme_preference("Neon")
        assert mgr.get_theme_preference(self.THEMES) == "System"

    def test_missing_falls_back_to_system(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_theme_preference(self.THEMES) == "System"


# ===========================================================================
# top_n / max_depth clamping
# ===========================================================================

class TestTopN:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_top_n(5)
        assert mgr.get_top_n() == 5

    def test_clamped_to_minimum_one(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_top_n(0)
        assert mgr.get_top_n() == 1

    def test_negative_clamped_to_one(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"top_n": -5}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_top_n() == 1

    def test_non_numeric_returns_default(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"top_n": "abc"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_top_n(default=3) == 3

    def test_missing_returns_default(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_top_n(default=7) == 7


class TestMaxDepth:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_max_depth(80)
        assert mgr.get_max_depth() == 80

    def test_zero_clamped_to_one(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_max_depth(0)
        assert mgr.get_max_depth() == 1

    def test_non_numeric_returns_default(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"max_depth": "deep"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_max_depth(default=50) == 50


# ===========================================================================
# Fuzzy threshold clamping
# ===========================================================================

class TestFuzzyThreshold:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_fuzzy_threshold(0.85)
        assert abs(mgr.get_fuzzy_threshold() - 0.85) < 1e-9

    def test_above_one_clamped(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"fuzzy_threshold": 1.5}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_fuzzy_threshold() == 1.0

    def test_below_zero_clamped(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"fuzzy_threshold": -0.1}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_fuzzy_threshold() == 0.0

    def test_non_numeric_returns_default(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"fuzzy_threshold": "high"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_fuzzy_threshold(default=0.72) == 0.72

    def test_boundary_exactly_zero(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_fuzzy_threshold(0.0)
        assert mgr.get_fuzzy_threshold() == 0.0

    def test_boundary_exactly_one(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_fuzzy_threshold(1.0)
        assert mgr.get_fuzzy_threshold() == 1.0


# ===========================================================================
# show_ids
# ===========================================================================

class TestShowIds:
    def test_default_is_false(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_show_ids() is False

    def test_set_true(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_show_ids(True)
        assert mgr.get_show_ids() is True

    def test_set_false(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_show_ids(True)
        mgr.set_show_ids(False)
        assert mgr.get_show_ids() is False

    def test_truthy_value_becomes_true(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"show_ids": 1}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_show_ids() is True


# ===========================================================================
# show_profile_image
# ===========================================================================

class TestShowProfileImage:
    def test_default_is_true(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_show_profile_image() is True

    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_show_profile_image(True)
        assert mgr.get_show_profile_image() is True
        mgr.set_show_profile_image(False)
        assert mgr.get_show_profile_image() is False


# ===========================================================================
# save_format
# ===========================================================================

class TestSaveFormat:
    def test_default_is_pdf(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_save_format() == "pdf"

    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_save_format("text")
        assert mgr.get_save_format() == "text"

    def test_invalid_falls_back_to_pdf(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"save_format": "html"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_save_format() == "pdf"


# ===========================================================================
# pdf_include_photos
# ===========================================================================

class TestPdfIncludePhotos:
    def test_default_is_false(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_pdf_include_photos() is False

    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_pdf_include_photos(True)
        assert mgr.get_pdf_include_photos() is True
        mgr.set_pdf_include_photos(False)
        assert mgr.get_pdf_include_photos() is False


# ===========================================================================
# media_parent_dirs
# ===========================================================================

class TestMediaParentDirs:
    def test_default_is_none(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_media_parent_dir("/tmp/tree.ged") is None

    def test_roundtrip_and_clear(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_media_parent_dir("/tmp/tree.ged", "/media/tree")
        assert mgr.get_media_parent_dir("/tmp/tree.ged") == "/media/tree"
        mgr.set_media_parent_dir("/tmp/tree.ged", None)
        assert mgr.get_media_parent_dir("/tmp/tree.ged") is None


# ===========================================================================
# name_order
# ===========================================================================

class TestNameOrder:
    def test_default_is_first_last(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_name_order() == "first_last"

    def test_set_last_first(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_name_order("last_first")
        assert mgr.get_name_order() == "last_first"

    def test_invalid_falls_back_to_first_last(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"name_order": "random"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_name_order() == "first_last"


# ===========================================================================
# default_display
# ===========================================================================

class TestDefaultDisplay:
    def test_default_is_profile(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_default_display() == "profile"

    def test_set_matches(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_default_display("matches")
        assert mgr.get_default_display() == "matches"

    def test_set_paths(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_default_display("paths")
        assert mgr.get_default_display() == "paths"

    def test_invalid_falls_back_to_profile(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"default_display": "tree"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_default_display() == "profile"


# ===========================================================================
# default_tree
# ===========================================================================

class TestDefaultTree:
    def test_default_is_tree(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_default_tree() == "tree"

    def test_set_pedigree(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_default_tree("pedigree")
        assert mgr.get_default_tree() == "pedigree"

    def test_set_descendant(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_default_tree("descendant")
        assert mgr.get_default_tree() == "descendant"

    def test_invalid_falls_back_to_tree(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"default_tree": "profile"}), encoding="utf-8")
        mgr = ConfigManager(p)
        assert mgr.get_default_tree() == "tree"


# ===========================================================================
# window_geometry (generic key/value pass-through)
# ===========================================================================

class TestWindowGeometry:
    def test_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        geom = {"width": 800, "height": 600, "x": 100, "y": 50}
        mgr.set_window_geometry("main_window", geom)
        assert mgr.get_window_geometry("main_window") == geom

    def test_missing_key_returns_none(self, tmp_path):
        mgr = _mgr(tmp_path)
        assert mgr.get_window_geometry("nonexistent") is None


# ===========================================================================
# Welcome window (first-run-per-version)
# ===========================================================================

class TestWelcomeSettings:
    def test_seen_version_default_is_none(self, tmp_path):
        assert _mgr(tmp_path).get_welcome_seen_version() is None

    def test_seen_version_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_welcome_seen_version("1.2.3")
        assert mgr.get_welcome_seen_version() == "1.2.3"

    def test_seen_version_non_string_falls_back_to_none(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"welcome_seen_version": 42}), encoding="utf-8")
        assert ConfigManager(p).get_welcome_seen_version() is None

    def test_show_on_startup_default_is_false(self, tmp_path):
        assert _mgr(tmp_path).get_show_welcome_on_startup() is False

    def test_show_on_startup_roundtrip(self, tmp_path):
        mgr = _mgr(tmp_path)
        mgr.set_show_welcome_on_startup(True)
        assert mgr.get_show_welcome_on_startup() is True
        mgr.set_show_welcome_on_startup(False)
        assert mgr.get_show_welcome_on_startup() is False


# ===========================================================================
# default_path
# ===========================================================================

class TestDefaultPath:
    def test_returns_a_path_object(self):
        p = ConfigManager.default_path()
        assert isinstance(p, Path)

    def test_filename_is_settings_json(self):
        p = ConfigManager.default_path()
        assert p.name == "settings.json"

    def test_parent_dir_contains_app_name(self):
        p = ConfigManager.default_path()
        assert "gedcom-navigator" in str(p)
