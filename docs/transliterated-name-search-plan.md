# Cached Hebrew and Cyrillic Phonetic Name Search

## Summary

Add cached English-letter aliases for Hebrew and Cyrillic names so users can find non-Latin GEDCOM names with an English keyboard when `Fuzzy` search is enabled. Keep normal search unchanged, preserve CLI behavior, and use optional libraries only as enhancement/normalization helpers.

## Key Changes

- Add `src/gedcom_transliteration.py` to generate `transliterated_names` for each individual from `alt_names`.
- Cyrillic:
  - Use `cyrtranslit` when importable.
  - Try a small set of likely language mappings, deduplicate outputs, and include a built-in Cyrillic fallback so packaged/CLI builds still work.
- Hebrew:
  - Use `hebrew` when importable for normalization/text cleanup.
  - Use an in-repo Hebrew-to-Latin romanization table for actual aliases.
  - Do not use or bundle `gimeltra`.
- Cache:
  - Add `transliterated_names: list[str]` to each individual record.
  - Generate aliases after a fresh parse and before JSON cache save.
  - Load aliases from cache on later runs.
  - Bump `GedcomDataModel._CACHE_VERSION`.
- Search:
  - Only fuzzy matching uses `transliterated_names`.
  - Normal token matching remains based on original `alt_names` and explicit extra names.
  - Existing married-name search remains opt-in and unchanged.
- Packaging/docs:
  - Add `cyrtranslit` and `hebrew` to GUI/build requirements used by PyInstaller.
  - Do not add them to base PyPI dependencies unless we explicitly want CLI installs to include transliteration libraries.
  - Document that aliases are generated locally, cached, approximate, and never written back to the GEDCOM.

## Public Interfaces

- Individual dictionaries gain:
  - `transliterated_names: list[str]`
- No new GUI toggle, shortcut, preference, or CLI option.
- Existing `--fuzzy` and GUI `Fuzzy` checkbox become the activation point for transliterated aliases.

## Test Plan

- Transliteration unit tests:
  - Hebrew names produce English-letter aliases after normalization.
  - Cyrillic names produce English-letter aliases with and without `cyrtranslit`.
  - ASCII-only names do not create duplicate aliases.
  - Existing Latin accented names still normalize safely where useful.
- Cache tests:
  - Fresh load generates `transliterated_names`.
  - Second load restores them from cache.
  - Cache-version bump invalidates old cache payloads.
- Search tests:
  - English query does not match Hebrew/Cyrillic aliases unless fuzzy is enabled.
  - Same query matches with fuzzy enabled.
  - Existing token, ID, fuzzy, and married-name tests still pass.
- Validation:
  - `& .\venv\Scripts\python.exe -m py_compile src/gedcom_transliteration.py src/gedcom_name_search.py src/gedcom_data_model.py`
  - `& .\venv\Scripts\python.exe -m pytest tests/test_name_search.py tests/test_data_model.py`

## Assumptions

- Packaged PyInstaller builds include `cyrtranslit` and `hebrew`, but not `gimeltra`.
- Hebrew transliteration is approximate, especially for unvowelled names.
- Alias generation is local-only and cache-only; display names stay in the original GEDCOM script.
