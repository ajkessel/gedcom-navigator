#!/usr/bin/env python3
"""
gedcom_transliteration.py

Cached Latin-script aliases for non-Latin GEDCOM names.
"""

import unicodedata

from gedcom_debug import log_exception_once


_CYRILLIC_LANGS = ('ru', 'ua', 'by', 'bg', 'sr', 'rs', 'me', 'mk', 'tj', 'mn')
_MAX_ALIASES_PER_NAME = 32

_CYRILLIC_MAP = {
    'А': 'A', 'а': 'a', 'Б': 'B', 'б': 'b', 'В': 'V', 'в': 'v',
    'Г': 'G', 'г': 'g', 'Д': 'D', 'д': 'd', 'Е': 'E', 'е': 'e',
    'Ё': 'Yo', 'ё': 'yo', 'Ж': 'Zh', 'ж': 'zh', 'З': 'Z', 'з': 'z',
    'И': 'I', 'и': 'i', 'Й': 'Y', 'й': 'y', 'К': 'K', 'к': 'k',
    'Л': 'L', 'л': 'l', 'М': 'M', 'м': 'm', 'Н': 'N', 'н': 'n',
    'О': 'O', 'о': 'o', 'П': 'P', 'п': 'p', 'Р': 'R', 'р': 'r',
    'С': 'S', 'с': 's', 'Т': 'T', 'т': 't', 'У': 'U', 'у': 'u',
    'Ф': 'F', 'ф': 'f', 'Х': 'Kh', 'х': 'kh', 'Ц': 'Ts', 'ц': 'ts',
    'Ч': 'Ch', 'ч': 'ch', 'Ш': 'Sh', 'ш': 'sh', 'Щ': 'Shch', 'щ': 'shch',
    'Ъ': '', 'ъ': '', 'Ы': 'Y', 'ы': 'y', 'Ь': '', 'ь': '',
    'Э': 'E', 'э': 'e', 'Ю': 'Yu', 'ю': 'yu', 'Я': 'Ya', 'я': 'ya',
    'Є': 'Ye', 'є': 'ye', 'І': 'I', 'і': 'i', 'Ї': 'Yi', 'ї': 'yi',
    'Ґ': 'G', 'ґ': 'g', 'Ў': 'U', 'ў': 'u',
    'Ј': 'J', 'ј': 'j', 'Љ': 'Lj', 'љ': 'lj', 'Њ': 'Nj', 'њ': 'nj',
    'Ћ': 'C', 'ћ': 'c', 'Ђ': 'Dj', 'ђ': 'dj', 'Џ': 'Dz', 'џ': 'dz',
    'Ѓ': 'Gj', 'ѓ': 'gj', 'Ѕ': 'Dz', 'ѕ': 'dz', 'Ќ': 'Kj', 'ќ': 'kj',
    'Ѐ': 'E', 'ѐ': 'e', 'Ѝ': 'I', 'ѝ': 'i',
}

_HEBREW_MAP = {
    'א': ('', 'a'), 'ב': ('b', 'v'), 'ג': ('g',), 'ד': ('d',),
    'ה': ('h', 'a'), 'ו': ('v', 'o', 'u'), 'ז': ('z',),
    'ח': ('ch', 'h'), 'ט': ('t',), 'י': ('y', 'i'), 'כ': ('k', 'ch'),
    'ך': ('k', 'ch'), 'ל': ('l',), 'מ': ('m',), 'ם': ('m',),
    'נ': ('n',), 'ן': ('n',), 'ס': ('s',), 'ע': ('', 'a'),
    'פ': ('p', 'f'), 'ף': ('p', 'f'), 'צ': ('tz', 'ts'), 'ץ': ('tz', 'ts'),
    'ק': ('k', 'q'), 'ר': ('r',), 'ש': ('sh', 's'), 'ת': ('t', 'th'),
    'װ': ('v',), 'ױ': ('oy',), 'ײ': ('ey', 'ay'), '׳': ("'",), '״': ('"',),
}


def _contains_cyrillic(text):
    """Return whether text contains at least one Cyrillic codepoint."""
    return any(
        '\u0400' <= char <= '\u052f'
        or '\u2de0' <= char <= '\u2dff'
        or '\ua640' <= char <= '\ua69f'
        for char in text
    )


def _contains_hebrew(text):
    """Return whether text contains at least one Hebrew codepoint."""
    return any('\u0590' <= char <= '\u05ff' for char in text)


def _ascii_fold(text):
    """Return text with combining marks removed and non-ASCII characters dropped."""
    decomposed = unicodedata.normalize('NFKD', text)
    folded = ''.join(
        char for char in decomposed
        if not unicodedata.combining(char) and ord(char) < 128
    )
    return _clean_alias(folded)


def _clean_alias(text):
    """Normalize alias spacing and punctuation for stable cache output."""
    cleaned = ' '.join(str(text).replace('/', ' ').split())
    return cleaned.strip(" \t\r\n'\"")


def _dedupe_aliases(aliases, originals):
    """Return aliases with duplicates and original names removed."""
    result = []
    seen = set()
    original_keys = {_clean_alias(name).casefold() for name in originals if name}
    for alias in aliases:
        cleaned = _clean_alias(alias)
        key = cleaned.casefold()
        if not cleaned or key in seen or key in original_keys:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _cyrtranslit_aliases(name):
    """Return aliases from cyrtranslit when it is installed."""
    try:
        import cyrtranslit  # pylint: disable=import-outside-toplevel
    except ImportError:
        return []

    supported = set(getattr(cyrtranslit, 'supported', lambda: _CYRILLIC_LANGS)())
    aliases = []
    for lang in _CYRILLIC_LANGS:
        if lang not in supported:
            continue
        try:
            aliases.append(cyrtranslit.to_latin(name, lang))
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception_once(
                f'cyrtranslit:{lang}',
                f"transliterating Cyrillic name with cyrtranslit lang={lang!r}",
            )
            continue
    return aliases


def _fallback_cyrillic_alias(name):
    """Return a built-in Cyrillic transliteration alias."""
    return ''.join(_CYRILLIC_MAP.get(char, char) for char in name)


def _normalize_hebrew(name):
    """Return Hebrew text normalized with the optional hebrew package when available."""
    try:
        from hebrew import Hebrew  # pylint: disable=import-outside-toplevel
    except ImportError:
        return unicodedata.normalize('NFKC', name)

    try:
        normalized = Hebrew(name).normalize()
        text_only = normalized.text_only()
        return getattr(text_only, 'string', text_only)
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception_once(
            'hebrew-normalize',
            "normalizing Hebrew name with optional hebrew package",
        )
        return unicodedata.normalize('NFKC', name)


def _hebrew_variants_for_word(word):
    """Return capped romanized variants for one Hebrew word."""
    variants = ['']
    for char in word:
        replacements = _HEBREW_MAP.get(char)
        if replacements is None:
            if unicodedata.combining(char):
                continue
            replacements = (char,)
        next_variants = []
        for prefix in variants:
            for replacement in replacements:
                next_variants.append(prefix + replacement)
                if len(next_variants) >= _MAX_ALIASES_PER_NAME:
                    break
            if len(next_variants) >= _MAX_ALIASES_PER_NAME:
                break
        variants = next_variants
    return [_clean_alias(variant) for variant in variants if _clean_alias(variant)]


def _fallback_hebrew_aliases(name):
    """Return built-in Hebrew romanization aliases."""
    normalized = _normalize_hebrew(name)
    words = []
    current = []
    for char in normalized:
        if _contains_hebrew(char):
            current.append(char)
        else:
            if current:
                words.append(''.join(current))
                current = []
            if char.isspace() or char in "-_/":
                words.append(' ')
            elif ord(char) < 128:
                words.append(char)
    if current:
        words.append(''.join(current))

    phrase_variants = ['']
    for token in words:
        token_variants = [' '] if token == ' ' else (
            _hebrew_variants_for_word(token)
            if _contains_hebrew(token)
            else [_clean_alias(token)]
        )
        next_variants = []
        for prefix in phrase_variants:
            for token_variant in token_variants:
                next_variants.append(prefix + token_variant)
                if len(next_variants) >= _MAX_ALIASES_PER_NAME:
                    break
            if len(next_variants) >= _MAX_ALIASES_PER_NAME:
                break
        phrase_variants = next_variants
    return phrase_variants


def transliterate_name(name):
    """Return cached search aliases for one GEDCOM name."""
    if not name:
        return []

    aliases = []
    if _contains_cyrillic(name):
        aliases.extend(_cyrtranslit_aliases(name))
        aliases.append(_fallback_cyrillic_alias(name))
    if _contains_hebrew(name):
        aliases.extend(_fallback_hebrew_aliases(name))

    folded = _ascii_fold(name)
    if folded and folded != _clean_alias(name):
        aliases.append(folded)

    aliases.extend(_ascii_fold(alias) for alias in list(aliases))
    return _dedupe_aliases(aliases, [name])


def transliterated_names_for_individual(indi):
    """Return all transliterated aliases for an individual record."""
    names = indi.get('alt_names') or [indi.get('name', '')]
    aliases = []
    for name in names:
        aliases.extend(transliterate_name(name))
    return _dedupe_aliases(aliases, names)


def add_transliterated_names(individuals):
    """Populate transliterated_names for every individual in-place."""
    for indi in individuals.values():
        indi['transliterated_names'] = transliterated_names_for_individual(indi)
