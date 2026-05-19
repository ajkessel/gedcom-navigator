# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Always use venv/scripts/python instead of python3 for running scripts.

# Project Structure
The source code is located in the `src/` directory.

# Instructions
When performing imports or analyzing the codebase, please ensure that `src/` is treated as a root directory for relative imports.

## Running from source

```bash
# GUI
python src/gedcom_navigator_gui.py
python src/gedcom_navigator_gui.py /path/to/tree.ged

# CLI
python src/gedcom_navigator_cli.py --help
python src/gedcom_navigator_cli.py tree.ged "Jane Doe"
python src/gedcom_navigator_cli.py tree.ged "Jane Doe" --top 5 --max-depth 80
python src/gedcom_navigator_cli.py tree.ged --list-tags _
python src/gedcom_navigator_cli.py tree.ged --list-flagged _
```

Third-party runtime dependencies (see `dev/requirements.txt`): `customtkinter`, `CTkToolTip`, `pillow`, plus platform-specific extras (`pyobjc-framework-Cocoa` and `certifi` on macOS, `pywin32-ctypes` on Windows).

## Building executables

```bash
dev/build.sh          # auto-detects macOS or Linux, dispatches to platform script
dev/build-mac.sh      # macOS: PyInstaller → notarized .app → zip
dev/build-linux.sh    # Linux: PyInstaller → zip
dev/build-pypi.sh     # PyPI wheel via hatchling
```

Windows builds use `dev/build.ps1`. Build scripts create `.venv` and install deps from `dev/requirements-dev.txt` automatically. The Mac build prefers the Python.org universal2 build at `/Library/Frameworks/Python.framework/Versions/3.14/`, falling back to pyenv.

## Architecture

### Source layout

The canonical implementation lives in `src/`. The `gedcom_navigator/` package contains thin forwarding entry points for PyPI installation that delegate to `src/`.

```
src/
  gedcom_core.py            # Compatibility facade: re-exports parser, display, search symbols
  gedcom_parser.py          # Two-pass GEDCOM parser, encoding detection, ZIP extraction
  gedcom_search.py          # BFS/A* graph traversal (bfs_find_dna_matches, bfs_find_all_paths)
  gedcom_display.py         # Formatting helpers: describe(), lifespan()
  gedcom_data_model.py      # Data layer: wraps parser, adds JSON disk cache
  gedcom_relationship.py    # BFS ancestor/descendant helpers + plain-English labels
  gedcom_name_search.py     # ID, token, and fuzzy name matching (shared by CLI and GUI)
  gedcom_family_tree.py     # Pure helpers for building/laying out immediate-family graphs
  gedcom_graph_export.py    # SVG and PNG export for relationship graph canvases
  gedcom_update.py          # GitHub release check for newer versions
  gedcom_navigator_gui.py  # customtkinter GUI application (GedcomNavigatorApp)
  gedcom_navigator_cli.py  # CLI interface
  gedcom_gui_appearance.py  # AppearanceMixin: theming, fonts, menus, keybindings
  gedcom_gui_background.py  # BackgroundTaskMixin: worker threads, busy state, progress dialogs
  gedcom_gui_dialogs.py     # DialogsMixin: pop-up windows
  gedcom_gui_results.py     # ResultsMixin: result rendering, path reversal, person navigation
  gedcom_gui_search.py      # SearchMixin: file loading, person-list filtering, DNA-match search
  gedcom_config.py          # ConfigManager: settings.json persistence
  gedcom_platform.py        # Platform integration hooks (Windows AppUserModelID, etc.)
  gedcom_theme.py           # Theme constants, OS dark-mode detection
  gedcom_tooltip.py         # Tooltip widget (wraps CTkToolTip, supports bold first line)
  gedcom_zoom.py            # Shared zoom keyboard/mouse shortcut helpers
  gedcom_strings.py         # All user-facing string constants (imported via wildcard)
  gedcom_markdown.py        # Markdown renderer for help/about dialogs

gedcom_navigator/
  __init__.py   # Version: __version__ and __release_date__ (single source of truth)
  cli.py        # Entry point → delegates to src/gedcom_navigator_cli.py
  gui.py        # Entry point → delegates to src/gedcom_navigator_gui.py
```

### Data flow

1. **Parsing** (`gedcom_parser.build_model`): Two-pass GEDCOM parser. Pass 1 collects `_MTTAG` tag definitions; Pass 2 parses `INDI` and `FAM` records. Returns `individuals`, `families`, `tag_records` dicts plus an optional encoding warning. Also supports loading from ZIP archives.

2. **Caching** (`GedcomDataModel`): Parsed data serialized as JSON, keyed by MD5 of the absolute path, validated against mtime + DNA keyword/page marker settings + `_CACHE_VERSION`. Cache lives in the OS config dir under `cache/`.

3. **BFS search** (`gedcom_search`):
   - `bfs_find_dna_matches`: Standard BFS via `deque`, walks `neighbors()` edges (father/mother/sibling/spouse/child), returns `(distance, path)` tuples for DNA-flagged individuals.
   - `bfs_find_all_paths`: Phase 1 BFS finds shortest distance; Phase 2 A\* heap search finds up to `top_n` distinct paths within `shortest + 4` edges. Spouse-detour variants are filtered post-search.

4. **Relationship labeling** (`gedcom_relationship.describe_relationship`): Classifies a BFS path's edge sequence into ancestor, descendant, sibling, cousin (all degrees and removals), aunt/uncle, niece/nephew, in-law, or step- relations. Falls back to a possessive chain (e.g. "father's brother's son").

### GUI structure

`GedcomNavigatorApp` inherits from `DialogsMixin`, `AppearanceMixin`, `SearchMixin`, `ResultsMixin`, and `BackgroundTaskMixin`. All GUI state lives in `tk.StringVar`/`BooleanVar`/`IntVar` attributes. Long operations (file loading, BFS search) run in daemon threads via `BackgroundTaskMixin` and post results back via `root.after()`.

### DNA flag detection

Two formats recognized (both configurable via CLI flags or GUI fields):
- **AncestryDNA citations**: `2 PAGE AncestryDNA Match to ...` (configurable via `--page-marker`)
- **MyTreeTags / FTM custom facts**: `_MTTAG` pointer resolved against a tag definition whose `NAME` contains the keyword (configurable via `--tag-keyword`, default `DNA`)

### Settings persistence

`ConfigManager` reads/writes `settings.json` in the platform config dir:
- macOS: `~/Library/Application Support/gedcom-navigator/settings.json`
- Windows: `%APPDATA%/gedcom-navigator/settings.json`
- Linux: `$XDG_CONFIG_HOME/gedcom-navigator/settings.json`