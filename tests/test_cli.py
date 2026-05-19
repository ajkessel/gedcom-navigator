"""Tests for command-line argument validators."""

import argparse

import pytest

from gedcom_navigator_cli import find_target, positive_int, ratio_float


INDIVIDUALS = {
    "@I1@": {
        "name": "John Adam /Smith/",
        "alt_names": ["John Adam Smith"],
    },
    "@I2@": {
        "name": "Jane /Doe/",
        "alt_names": ["Jane Doe"],
    },
}


class TestPositiveInt:
    def test_accepts_positive_integer(self):
        assert positive_int("3") == 3

    @pytest.mark.parametrize("value", ["0", "-1", "abc"])
    def test_rejects_non_positive_or_invalid_values(self, value):
        with pytest.raises(argparse.ArgumentTypeError):
            positive_int(value)


class TestRatioFloat:
    @pytest.mark.parametrize("value", ["0", "0.6", "1"])
    def test_accepts_inclusive_ratio_range(self, value):
        assert ratio_float(value) == float(value)

    @pytest.mark.parametrize("value", ["-0.1", "1.1", "abc"])
    def test_rejects_values_outside_ratio_range(self, value):
        with pytest.raises(argparse.ArgumentTypeError):
            ratio_float(value)


class TestFindTarget:
    def test_delegates_token_matching_to_shared_service(self):
        assert find_target(INDIVIDUALS, "smith john") == [("@I1@", None)]

    def test_delegates_fuzzy_matching_to_shared_service(self):
        candidates = find_target(
            INDIVIDUALS, "Jon Smit", fuzzy=True, fuzzy_threshold=0.72)
        assert candidates[0][0] == "@I1@"
        assert candidates[0][1] is not None
