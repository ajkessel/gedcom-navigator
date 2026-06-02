#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Hardened gettext (.pot/.po) translator using DeepL.

Features
- Prefers official `deepl` SDK if installed; falls back to `deep_translator.DeeplTranslator`.
- Preserves placeholders:
    * Python brace format: {count:,}, {name}, {total_matches:,}, etc.
    * printf-style: %(name)s, %d, %.2f, %%
- Preserves shortcut tokens: Ctrl+Shift+D, Alt+X, (F1), F2, etc.
- Applies a small genealogy/UI glossary for consistent terminology.
- Handles plural entries (msgid_plural) safely.
- Batch translation with conservative size limits.

Usage (Windows example)
  set DEEPL_AUTH_KEY=...your key...
  python translate_po_deepl.py --input gedcom_navigator.txt --outdir locales_out --langs de es fr he --prefer-official

Then validate:
  msgfmt --check locales_out/gedcom_navigator_de.po
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

import polib

# ---------------------------
# Placeholder & token handling
# ---------------------------

BRACE_RE = re.compile(r"\{[^{}]+\}")
PRINTF_RE = re.compile(
    r"%(?:\([^)]+\))?[#0\- +]?\d*(?:\.\d+)?[diouxXeEfFgGcrs%]"
)

SHORTCUT_RE_LIST = [
    re.compile(r"\bCtrl\+\w+(?:\+\w+)*\b", re.IGNORECASE),
    re.compile(r"\bAlt\+\w+(?:\+\w+)*\b", re.IGNORECASE),
    re.compile(r"\bShift\+\w+(?:\+\w+)*\b", re.IGNORECASE),
    re.compile(r"\(F\d+\)"),
    re.compile(r"\bF\d+\b"),
]

# Do-not-translate literals (product/tech identifiers)
DNT_LITERALS = [
    "GEDCOM",
    "GitHub",
    "JSON",
    "ZIP",
    "Ctrl",
    "Shift",
    "Alt",
]


def _mk_token(i: int) -> str:
    # Purely numeric content: translation engines translate words, not digit strings
    return f"⟦{i:04d}⟧"


# Matches any unrestored placeholder token in translated output
UNRESTORED_TOKEN_RE = re.compile(r"⟦\d{4}⟧")


@dataclass
class ProtectedText:
    text: str
    restores: List[Tuple[str, str]]  # (token, original)


def protect_patterns(text: str, patterns: List[re.Pattern], counter: List[int]) -> ProtectedText:
    restores: List[Tuple[str, str]] = []
    out = text

    for pat in patterns:
        while True:
            m = pat.search(out)
            if not m:
                break
            orig = m.group(0)
            tok = _mk_token(counter[0])
            counter[0] += 1
            restores.append((tok, orig))
            out = out[: m.start()] + tok + out[m.end() :]

    return ProtectedText(out, restores)


def restore_all(text: str, restores: List[Tuple[str, str]]) -> str:
    out = text
    for tok, orig in restores:
        out = out.replace(tok, orig)
    return out


# ---------------------------
# Glossary / terminology tuning (modern/concise)
# ---------------------------

GLOSSARY: Dict[str, List[Tuple[str, str]]] = {
    "de": [
        ("Family Tree", "Stammbaum"),
        ("Tree View", "Stammbaumansicht"),
        ("Profile View", "Profilansicht"),
        ("Tree", "Stammbaum"),
        ("Profile", "Profil"),
        ("Home person", "Startperson"),
        ("Home Person", "Startperson"),
        ("Set Home", "Startperson festlegen"),
        ("Relationship", "Verwandtschaft"),
        ("Relationship path", "Verwandtschaftspfad"),
        ("Relationship Path", "Verwandtschaftspfad"),
        ("Common ancestor", "Gemeinsamer Vorfahr"),
        ("Common ancestors", "Gemeinsame Vorfahren"),
        ("Tagged", "Markiert"),
        ("Tags", "Tags"),
        ("Find", "Suchen"),
        ("Filter", "Filtern"),
        ("Results", "Ergebnisse"),
        ("Max Depth", "Max. Tiefe"),
        ("Fuzzy", "Ungefähre Suche"),
        ("Married", "Ehenamen"),
        ("Save", "Speichern"),
        ("Open", "Öffnen"),
        ("Close", "Schließen"),
        ("Copy", "Kopieren"),
    ],
    "es": [
        ("Family Tree", "Árbol genealógico"),
        ("Tree View", "Vista de árbol"),
        ("Profile View", "Vista de perfil"),
        ("Tree", "Árbol"),
        ("Profile", "Perfil"),
        ("Home person", "Persona principal"),
        ("Home Person", "Persona principal"),
        ("Set Home", "Establecer persona principal"),
        ("Relationship", "Parentesco"),
        ("Relationship path", "Ruta de parentesco"),
        ("Relationship Path", "Ruta de parentesco"),
        ("Common ancestor", "Antepasado común"),
        ("Common ancestors", "Antepasados comunes"),
        ("Tagged", "Etiquetado"),
        ("Tags", "Etiquetas"),
        ("Find", "Buscar"),
        ("Filter", "Filtrar"),
        ("Results", "Resultados"),
        ("Max Depth", "Profundidad máx."),
        ("Fuzzy", "Búsqueda aproximada"),
        ("Married", "Apellidos de casada"),
        ("Save", "Guardar"),
        ("Open", "Abrir"),
        ("Close", "Cerrar"),
        ("Copy", "Copiar"),
    ],
    "fr": [
        ("Family Tree", "Arbre généalogique"),
        ("Tree View", "Vue arborescente"),
        ("Profile View", "Vue du profil"),
        ("Tree", "Arbre"),
        ("Profile", "Profil"),
        ("Home person", "Personne de référence"),
        ("Home Person", "Personne de référence"),
        ("Set Home", "Définir la personne de référence"),
        ("Relationship", "Lien de parenté"),
        ("Relationship path", "Chemin de parenté"),
        ("Relationship Path", "Chemin de parenté"),
        ("Common ancestor", "Ancêtre commun"),
        ("Common ancestors", "Ancêtres communs"),
        ("Tagged", "Marqué"),
        ("Tags", "Tags"),
        ("Find", "Rechercher"),
        ("Filter", "Filtrer"),
        ("Results", "Résultats"),
        ("Max Depth", "Profondeur max."),
        ("Fuzzy", "Recherche approximative"),
        ("Married", "Noms d’épouse"),
        ("Save", "Enregistrer"),
        ("Open", "Ouvrir"),
        ("Close", "Fermer"),
        ("Copy", "Copier"),
    ],
    "he": [
        ("Family Tree", "עץ משפחה"),
        ("Tree View", "תצוגת עץ משפחה"),
        ("Profile View", "תצוגת פרופיל"),
        ("Tree", "עץ"),
        ("Profile", "פרופיל"),
        ("Home person", "אדם ראשי"),
        ("Home Person", "אדם ראשי"),
        ("Set Home", "הגדר אדם ראשי"),
        ("Relationship", "קשר משפחתי"),
        ("Relationship path", "מסלול קשר"),
        ("Relationship Path", "מסלול קשר"),
        ("Common ancestor", "אב קדמון משותף"),
        ("Common ancestors", "אבות קדמונים משותפים"),
        ("Tagged", "מתויג"),
        ("Tags", "תגים"),
        ("Find", "חפש"),
        ("Filter", "סנן"),
        ("Results", "תוצאות"),
        ("Max Depth", "עומק מרבי"),
        ("Fuzzy", "חיפוש מקורב"),
        ("Married", "שמות נישואין"),
        ("Save", "שמור"),
        ("Open", "פתח"),
        ("Close", "סגור"),
        ("Copy", "העתק"),
    ],
}


def apply_glossary_tokens(source: str, lang: str, counter: List[int]) -> ProtectedText:
    restores: List[Tuple[str, str]] = []
    out = source

    pairs = GLOSSARY.get(lang, [])
    pairs_sorted = sorted(pairs, key=lambda x: len(x[0]), reverse=True)

    for src_term, tgt_term in pairs_sorted:
        if src_term in out:
            tok = _mk_token(counter[0])
            counter[0] += 1
            out = out.replace(src_term, tok)
            restores.append((tok, tgt_term))

    return ProtectedText(out, restores)


# ---------------------------
# Translator backends
# ---------------------------

class TranslatorBackend:
    def translate_batch(self, texts: List[str], target_lang: str) -> List[str]:
        raise NotImplementedError


class DeeplOfficialBackend(TranslatorBackend):
    def __init__(self, auth_key: str):
        import deepl  # official package
        self.client = deepl.DeepLClient(auth_key)

    def translate_batch(self, texts: List[str], target_lang: str) -> List[str]:
        res = self.client.translate_text(
            texts,
            target_lang=target_lang.upper(),
            preserve_formatting=True,
        )
        if isinstance(res, list):
            return [r.text for r in res]
        return [res.text]


class DeepTranslatorBackend(TranslatorBackend):
    def __init__(self, auth_key: str, use_free_api: bool = True):
        from deep_translator import DeeplTranslator
        self.DeeplTranslator = DeeplTranslator
        self.auth_key = auth_key
        self.use_free_api = use_free_api

    def translate_batch(self, texts: List[str], target_lang: str) -> List[str]:
        t = self.DeeplTranslator(
            source="auto",
            target=target_lang.lower(),
            api_key=self.auth_key,
            use_free_api=self.use_free_api,
        )
        return t.translate_batch(texts)


def pick_backend(auth_key: str, prefer_official: bool, use_free_api: bool) -> TranslatorBackend:
    if prefer_official:
        try:
            return DeeplOfficialBackend(auth_key)
        except Exception:
            return DeepTranslatorBackend(auth_key, use_free_api=use_free_api)

    try:
        return DeepTranslatorBackend(auth_key, use_free_api=use_free_api)
    except Exception:
        return DeeplOfficialBackend(auth_key)


# ---------------------------
# Chunking / batching
# ---------------------------

def chunk_texts(texts: List[str], max_chars: int, max_items: int) -> List[List[str]]:
    batches: List[List[str]] = []
    cur: List[str] = []
    cur_chars = 0

    for t in texts:
        tlen = len(t)
        if cur and (len(cur) >= max_items or cur_chars + tlen > max_chars):
            batches.append(cur)
            cur = []
            cur_chars = 0
        cur.append(t)
        cur_chars += tlen

    if cur:
        batches.append(cur)
    return batches


# ---------------------------
# Main PO translation logic
# ---------------------------

def should_translate_entry(e: polib.POEntry, overwrite: bool) -> bool:
    if not e.msgid.strip():
        return False
    if e.obsolete:
        return False
    if overwrite:
        return True
    if e.msgid_plural:
        return any(not v for v in e.msgstr_plural.values())
    return not bool(e.msgstr)


def protect_all(source: str, lang: str) -> Tuple[str, List[Tuple[str, str]]]:
    restores: List[Tuple[str, str]] = []
    counter = [0]  # shared mutable counter ensures unique numeric tokens per string

    g = apply_glossary_tokens(source, lang, counter)
    s = g.text
    restores.extend(g.restores)

    for lit in DNT_LITERALS:
        if lit in s:
            tok = _mk_token(counter[0])
            counter[0] += 1
            s = s.replace(lit, tok)
            restores.append((tok, lit))

    p1 = protect_patterns(s, [BRACE_RE], counter)
    s = p1.text
    restores.extend(p1.restores)

    p2 = protect_patterns(s, [PRINTF_RE], counter)
    s = p2.text
    restores.extend(p2.restores)

    p3 = protect_patterns(s, SHORTCUT_RE_LIST, counter)
    s = p3.text
    restores.extend(p3.restores)

    return s, restores


def translate_po(
    input_path: str,
    output_path: str,
    lang: str,
    backend: TranslatorBackend,
    overwrite: bool,
    mark_fuzzy: bool,
    batch_max_chars: int,
    batch_max_items: int,
) -> int:  # returns number of validation warnings
    po = polib.pofile(input_path)
    po.metadata["Language"] = lang

    # Each job is (entry, kind, protected_text, restores)
    jobs: List[Tuple[polib.POEntry, str, str, List[Tuple[str, str]]]] = []

    for e in po:
        if not should_translate_entry(e, overwrite=overwrite):
            continue

        if e.msgid_plural:
            s1, r1 = protect_all(e.msgid, lang)
            s2, r2 = protect_all(e.msgid_plural, lang)
            jobs.append((e, "singular", s1, r1))
            jobs.append((e, "plural", s2, r2))
        else:
            s, r = protect_all(e.msgid, lang)
            jobs.append((e, "single", s, r))

    if not jobs:
        po.save(output_path)
        return 0

    protected_texts = [j[2] for j in jobs]
    batches = chunk_texts(protected_texts, max_chars=batch_max_chars, max_items=batch_max_items)

    translated_all: List[str] = []
    idx = 0
    for b in batches:
        out = backend.translate_batch(b, target_lang=lang)
        if len(out) != len(b):
            raise RuntimeError("Translation backend returned unexpected batch size")
        translated_all.extend(out)
        idx += len(b)

    # Apply translations back
    warnings = 0
    for (entry, kind, ptxt, restores), raw in zip(jobs, translated_all):
        t = restore_all(raw, restores)

        # Detect tokens that DeepL mangled and restore_all couldn't match
        if UNRESTORED_TOKEN_RE.search(t):
            print(
                f"WARNING [{lang}]: unrestored token in translation of {entry.msgid!r}",
                file=sys.stderr,
            )
            print(f"  protected:  {ptxt!r}", file=sys.stderr)
            print(f"  raw output: {raw!r}", file=sys.stderr)
            print(f"  restored:   {t!r}", file=sys.stderr)
            warnings += 1

        if kind == "single":
            entry.msgstr = t

        elif kind == "singular":
            if not entry.msgstr_plural:
                entry.msgstr_plural = {0: "", 1: ""}
            entry.msgstr_plural[0] = t

        elif kind == "plural":
            if not entry.msgstr_plural:
                entry.msgstr_plural = {0: "", 1: ""}
            for k in sorted(entry.msgstr_plural.keys()):
                if k != 0:
                    entry.msgstr_plural[k] = t

        if mark_fuzzy and ("fuzzy" not in entry.flags):
            entry.flags.append("fuzzy")

    po.save(output_path)
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to .pot or .po (your canonical template)")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--langs", nargs="+", required=True, help="Language codes, e.g. de es fr he")
    ap.add_argument("--auth-env", default="DEEPL_AUTH_KEY", help="Env var holding DeepL API key")
    ap.add_argument("--prefer-official", action="store_true", help="Prefer official `deepl` SDK if installed")
    ap.add_argument("--use-free-api", action="store_true", help="If using deep_translator, use free endpoint")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing msgstr values")
    ap.add_argument("--no-fuzzy", action="store_true", help="Do not mark machine translations as fuzzy")
    ap.add_argument("--batch-max-chars", type=int, default=12000, help="Conservative per-request char budget")
    ap.add_argument("--batch-max-items", type=int, default=40, help="Max segments per batch")

    args = ap.parse_args()

    auth_key = os.getenv(args.auth_env)
    if not auth_key:
        print(f"ERROR: DeepL auth key not found in env var {args.auth_env}", file=sys.stderr)
        return 2

    os.makedirs(args.outdir, exist_ok=True)

    backend = pick_backend(auth_key, prefer_official=args.prefer_official, use_free_api=args.use_free_api)

    total_warnings = 0
    for lang in args.langs:
        out_path = os.path.join(args.outdir, f"gedcom_navigator_{lang}.po")
        w = translate_po(
            input_path=args.input,
            output_path=out_path,
            lang=lang,
            backend=backend,
            overwrite=args.overwrite,
            mark_fuzzy=not args.no_fuzzy,
            batch_max_chars=args.batch_max_chars,
            batch_max_items=args.batch_max_items,
        )
        if w:
            print(f"Wrote {out_path} ({w} translation warning(s))")
        else:
            print(f"Wrote {out_path}")
        total_warnings += w

    if total_warnings:
        print(
            f"ERROR: {total_warnings} translation(s) contain unrestored placeholder tokens "
            f"— the output is likely corrupt. Re-run or inspect the WARNING lines above.",
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
