# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running from source

```bash
# GUI
python src/gedcom_dna_finder_gui.py
python src/gedcom_dna_finder_gui.py /path/to/tree.ged

# CLI
python src/gedcom_dna_finder_cli.py --help
python src/gedcom_dna_finder_cli.py tree.ged "Jane Doe"
python src/gedcom_dna_finder_cli.py tree.ged "Jane Doe" --top 5 --max-depth 80
python src/gedcom_dna_finder_cli.py tree.ged --list-tags _
python src/gedcom_dna_finder_cli.py tree.ged --list-flagged _
```

Only third part-party library dependency is customtkinter. 

## Building executables

```bash
dev/build.sh          # auto-detects macOS or Linux, dispatches to platform script
dev/build-mac.sh      # macOS: PyInstaller → notarized .app → zip
dev/build-linux.sh    # Linux: PyInstaller → zip
dev/build-pypi.sh     # PyPI wheel via hatchling
```

Windows builds use `dev/build.ps1`. Build scripts create `.venv` and install deps from `dev/requirements.txt` automatically. The Mac build prefers the Python.org universal2 build at `/Library/Frameworks/Python.framework/Versions/3.14/`, falling back to pyenv.

## Architecture

**Zero third-party runtime dependencies.** The entire tool uses only the Python standard library.

### Source layout

The canonical implementation lives in `src/`. The `gedcom_dna_finder/` package contains thin forwarding entry points for PyPI installation that delegate to `src/`.

```
src/
  gedcom_core.py            # GEDCOM parser + BFS engine (no GUI imports)
  gedcom_data_model.py      # Data layer: wraps core, adds JSON disk cache
  gedcom_dna_finder_gui.py  # Tkinter GUI application (DNAMatchFinderApp)
  gedcom_dna_finder_cli.py  # CLI interface
  gedcom_gui_appearance.py  # AppearanceMixin: theming, fonts, menus, keybindings
  gedcom_gui_dialogs.py     # DialogsMixin: pop-up windows
  gedcom_config.py          # ConfigManager: settings.json persistence
  gedcom_relationship.py    # BFS ancestor/descendant helpers + plain-English labels
  gedcom_theme.py           # Theme constants, OS dark-mode detection, Tooltip widget
  gedcom_strings.py         # All user-facing string constants (imported via wildcard)
  gedcom_markdown.py        # Markdown renderer for help/about dialogs

gedcom_dna_finder/
  __init__.py   # Version: __version__ and __release_date__ (single source of truth)
  cli.py        # Entry point → delegates to src/gedcom_dna_finder_cli.py
  gui.py        # Entry point → delegates to src/gedcom_dna_finder_gui.py
```

### Data flow

1. **Parsing** (`gedcom_core.build_model`): Two-pass GEDCOM parser. Pass 1 collects `_MTTAG` tag definitions; Pass 2 parses `INDI` and `FAM` records. Returns `individuals`, `families`, `tag_records` dicts plus an optional encoding warning.

2. **Caching** (`GedcomDataModel`): Parsed data serialized as JSON, keyed by MD5 of the absolute path, validated against mtime + DNA keyword/page marker settings + `_CACHE_VERSION`. Cache lives in the OS config dir under `cache/`.

3. **BFS search** (`gedcom_core`):
   - `bfs_find_dna_matches`: Standard BFS via `deque`, walks `neighbors()` edges (father/mother/sibling/spouse/child), returns `(distance, path)` tuples for DNA-flagged individuals.
   - `bfs_find_all_paths`: Phase 1 BFS finds shortest distance; Phase 2 A\* heap search finds up to `top_n` distinct paths within `shortest + 4` edges. Spouse-detour variants are filtered post-search.

4. **Relationship labeling** (`gedcom_relationship.describe_relationship`): Classifies a BFS path's edge sequence into ancestor, descendant, sibling, cousin (all degrees and removals), aunt/uncle, niece/nephew, in-law, or step- relations. Falls back to a possessive chain (e.g. "father's brother's son").

### GUI structure

`DNAMatchFinderApp` inherits from `DialogsMixin` and `AppearanceMixin`. All GUI state lives in `tk.StringVar`/`BooleanVar`/`IntVar` attributes. Long operations (file loading, BFS search) run in daemon threads and post results back via `root.after()`.

### DNA flag detection

Two formats recognized (both configurable via CLI flags or GUI fields):
- **AncestryDNA citations**: `2 PAGE AncestryDNA Match to ...` (configurable via `--page-marker`)
- **MyTreeTags / FTM custom facts**: `_MTTAG` pointer resolved against a tag definition whose `NAME` contains the keyword (configurable via `--tag-keyword`, default `DNA`)

### Settings persistence

`ConfigManager` reads/writes `settings.json` in the platform config dir:
- macOS: `~/Library/Application Support/gedcom-dna-finder/settings.json`
- Windows: `%APPDATA%/gedcom-dna-finder/settings.json`
- Linux: `$XDG_CONFIG_HOME/gedcom-dna-finder/settings.json`