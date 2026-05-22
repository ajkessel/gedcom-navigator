"""Tests for cached transliterated name aliases."""

from gedcom_transliteration import (
    add_transliterated_names,
    transliterate_name,
    transliterated_names_for_individual,
)


def test_cyrillic_name_gets_latin_alias():
    aliases = transliterate_name("Иван Петров")

    assert "Ivan Petrov" in aliases


def test_hebrew_name_gets_latin_aliases():
    aliases = transliterate_name("משה כהן")

    assert "msh khn" in aliases
    assert "moshe" not in aliases


def test_latin_diacritics_are_folded():
    assert transliterate_name("José Álvarez") == ["Jose Alvarez"]


def test_ascii_name_does_not_create_duplicate_alias():
    assert transliterate_name("John Smith") == []


def test_individual_aliases_are_deduplicated():
    indi = {
        "name": "Иван /Петров/",
        "alt_names": ["Иван Петров", "Ivan Petrov"],
    }

    aliases = transliterated_names_for_individual(indi)

    assert "Ivan Petrov" not in aliases
    assert len(aliases) == len(set(aliases))


def test_add_transliterated_names_mutates_individuals():
    individuals = {
        "@I1@": {"name": "Иван /Петров/", "alt_names": ["Иван Петров"]},
        "@I2@": {"name": "John /Smith/", "alt_names": ["John Smith"]},
    }

    add_transliterated_names(individuals)

    assert "Ivan Petrov" in individuals["@I1@"]["transliterated_names"]
    assert individuals["@I2@"]["transliterated_names"] == []
