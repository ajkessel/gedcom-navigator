# translate_po_deepl.py

Hardened gettext (.po/.pot) translation script using DeepL.

## Features
- Preserves placeholders: `{}`, `%()` formatting
- Preserves keyboard shortcuts (Ctrl+…, F1, etc.)
- Applies genealogy-aware terminology tuning
- Supports batch translation

## Requirements
```
pip install polib deepl
# optional fallback
pip install deep-translator
```

## Usage (Windows cmd)
```
set DEEPL_AUTH_KEY=your-key-here
python translate_po_deepl.py ^
  --input gedcom_navigator.txt ^
  --outdir locales_out ^
  --langs de es fr he ^
  --prefer-official
```

## Usage (PowerShell)
```
$env:DEEPL_AUTH_KEY="your-key-here"
python translate_po_deepl.py `
  --input gedcom_navigator.txt `
  --outdir locales_out `
  --langs de es fr he `
  --prefer-official
```

## Validate output
```
msgfmt --check locales_out\gedcom_navigator_de.po
```

## Notes
- Keep placeholders intact; do not post-edit them
- Consider reviewing fuzzy entries before shipping
