"""Tests for shared GEDCOM name and ID search helpers."""

from gedcom_name_search import find_candidates, individual_matches_query


INDIVIDUALS = {
    "@I1@": {
        "name": "John Adam /Smith/",
        "alt_names": ["John Adam Smith", "J. A. Smith"],
    },
    "@I2@": {
        "name": "Jane /Doe/",
        "alt_names": ["Jane Doe"],
    },
    "@I23@": {
        "name": "Alice /Jones/",
        "alt_names": ["Alice Jones"],
    },
    "@I4@": {
        "name": "משה /כהן/",
        "alt_names": ["משה כהן"],
        "transliterated_names": ["moshe kohen"],
    },
    "@I5@": {
        "name": "Fallback /Hebrew/",
        "alt_names": ["משה כהן"],
        "transliterated_names": ["msh khn"],
    },
}


class TestFindCandidates:
    def test_exact_id_with_at_signs(self):
        assert find_candidates(INDIVIDUALS, "@I23@") == [("@I23@", None)]

    def test_exact_id_without_at_signs(self):
        assert find_candidates(INDIVIDUALS, "I23") == [("@I23@", None)]

    def test_token_matching_is_order_independent(self):
        assert find_candidates(INDIVIDUALS, "smith john") == [("@I1@", None)]

    def test_id_substring_matching(self):
        assert find_candidates(INDIVIDUALS, "23") == [("@I23@", None)]

    def test_fuzzy_matching_adds_scored_candidates(self):
        candidates = find_candidates(
            INDIVIDUALS, "Jon Smit", fuzzy=True, fuzzy_threshold=0.72)
        assert candidates[0][0] == "@I1@"
        assert candidates[0][1] is not None

    def test_extra_names_are_opt_in(self):
        assert find_candidates(INDIVIDUALS, "jane jones") == []
        assert find_candidates(
            INDIVIDUALS,
            "jane jones",
            extra_names_by_id={"@I2@": ["Jane Jones"]},
        ) == [("@I2@", None)]

    def test_fuzzy_matching_uses_extra_names_when_provided(self):
        candidates = find_candidates(
            INDIVIDUALS,
            "Jane Jons",
            fuzzy=True,
            fuzzy_threshold=0.75,
            extra_names_by_id={"@I2@": ["Jane Jones"]},
        )
        assert candidates[0][0] == "@I2@"
        assert candidates[0][1] is not None

    def test_transliterated_names_are_fuzzy_only(self):
        assert find_candidates(INDIVIDUALS, "moshe kohen") == []

        candidates = find_candidates(
            INDIVIDUALS, "moshe kohen", fuzzy=True, fuzzy_threshold=0.9)

        assert candidates == [("@I4@", 1.0)]

    def test_fuzzy_matching_handles_hebrew_fallback_aliases(self):
        candidates = find_candidates(
            {"@I5@": INDIVIDUALS["@I5@"]},
            "moshe kohen",
            fuzzy=True,
            fuzzy_threshold=0.72,
        )

        assert candidates[0][0] == "@I5@"
        assert candidates[0][1] is not None


class TestIndividualMatchesQuery:
    def test_empty_query_matches_for_list_population(self):
        assert individual_matches_query("@I1@", INDIVIDUALS["@I1@"], "") == (
            True, None)

    def test_rejects_non_matching_query(self):
        assert individual_matches_query(
            "@I1@", INDIVIDUALS["@I1@"], "unrelated") == (False, None)

    def test_extra_names_are_used_when_provided(self):
        assert individual_matches_query(
            "@I2@",
            INDIVIDUALS["@I2@"],
            "jane jones",
            extra_names=["Jane Jones"],
        ) == (True, None)

    def test_transliterated_names_require_fuzzy_mode(self):
        assert individual_matches_query(
            "@I4@", INDIVIDUALS["@I4@"], "moshe kohen") == (False, None)

        matched, score = individual_matches_query(
            "@I4@", INDIVIDUALS["@I4@"], "moshe kohen",
            fuzzy=True, fuzzy_threshold=0.9)

        assert matched is True
        assert score == 1.0
