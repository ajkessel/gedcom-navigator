# GEDCOM Navigator Development Guide

Welcome to the GEDCOM Navigator project! This document provides an overview of the codebase, architecture, and development workflows to help you get started.

## Architecture Overview

The application is structured into several layers to separate data management, business logic, and user interface concerns.

1.  **Data Layer (`src/gedcom_data_model.py`)**: Centralizes GEDCOM loading, JSON caching, and search coordination. It is isolated from GUI concerns.
2.  **Parser Layer (`src/gedcom_parser.py`)**: Handles low-level GEDCOM parsing, character encoding detection, and archive (ZIP) extraction.
3.  **Search & Logic Layer (`src/gedcom_search.py`, `src/gedcom_relationship.py`)**: Implements graph traversal (BFS) and relationship narrative generation.
4.  **UI Layer**:
    *   **GUI (`src/gedcom_navigator_gui.py`)**: Built with [CustomTkinter](https://github.com/tomschimansky/customtkinter) for a modern, cross-platform look.
    *   **CLI (`src/gedcom_navigator_cli.py`)**: A command-line interface sharing the same core logic.
5.  **Build & Release (`dev/`)**: Contains platform-specific build scripts and PyInstaller configuration.

---

## Source Code Map

### Core Logic (`src/`)

| File                        | Description                                                                                  |
| :-------------------------- | :------------------------------------------------------------------------------------------- |
| `gedcom_parser.py`          | Detects encoding and parses raw GEDCOM into structured dictionaries.                         |
| `gedcom_data_model.py`      | The main `GedcomDataModel` class. Manages the lifecycle of loaded data and search results.   |
| `gedcom_search.py`          | Implements the Breadth-First Search (BFS) algorithm to find the shortest relationship paths. |
| `gedcom_relationship.py`    | Translates raw paths into human-readable relationship terms (e.g., "3rd cousin 1x removed"). |
| `gedcom_name_search.py`     | Token-based and fuzzy name searching logic.                                                  |
| `gedcom_config.py`          | Manages application configuration and persistent settings.                                   |
| `gedcom_strings.py`         | UI string constants wrapped with gettext for localization.                                   |
| `gedcom_i18n.py`            | Internationalization setup: `gettext` initialization, language detection, available-language enumeration. |
| `gedcom_transliteration.py` | Generates Latin-script aliases for Hebrew and Cyrillic names to support fuzzy search.        |
| `gedcom_shortcuts.py`       | Centralized keyboard shortcut metadata (`ShortcutSpec`) shared by the GUI and tests.         |
| `gedcom_debug.py`           | Debug-only exception logging activated by the `GEDCOM_NAVIGATOR_DEBUG` environment variable. |

### Localization (`locales/`)

Translation files are stored in `locales/<lang>/LC_MESSAGES/gedcom_navigator.po`. The `.pot` template is at `locales/gedcom_navigator.pot`. Compiled `.mo` files are generated at build time. The `dev/translate-po-deepl.py` script automates translation via the DeepL API.

Shipping translations: German (`de`), Spanish (`es`), French (`fr`), Hebrew (`he`).

### GUI Components (`src/`)

The GUI is modularized into several files prefixed with `gedcom_gui_`:

| File                              | Description                                                                      |
| :-------------------------------- | :------------------------------------------------------------------------------- |
| `gedcom_navigator_gui.py`         | The main window and application entry point.                                     |
| `gedcom_gui_background.py`        | Handles background worker threads to keep the UI responsive during searches.     |
| `gedcom_gui_search.py`            | The search sidebar and individual selection list.                                 |
| `gedcom_gui_results.py`           | The Display Pane: profile, DNA-match, and relationship-path result rendering.    |
| `gedcom_gui_dialogs.py`           | Common dialog boxes (Preferences, Tag/person pickers, path finder).              |
| `gedcom_gui_help_dialogs.py`      | Help, keyboard shortcuts, privacy policy, and About dialogs.                     |
| `gedcom_gui_person_dialog.py`     | Detailed profile and family-tree view for a single individual.                   |
| `gedcom_gui_graph_layout.py`      | Graph layout computation for relationship paths and family trees.                |
| `gedcom_gui_graph_common.py`      | Shared canvas helpers, click handling, and export used by both graph views.      |
| `gedcom_gui_path_graph.py`        | Relationship path graph canvas rendering.                                        |
| `gedcom_gui_family_tree_render.py`| Family tree canvas rendering in the Show Person window.                          |

---

## Key Concepts

### Data Model
Individuals and families are stored as dictionaries in `GedcomDataModel`.
- `individuals`: Keyed by INDI ID (e.g., `@I1@`).
- `families`: Keyed by FAM ID (e.g., `@F1@`).
- `tag_records`: Stores `_MTTAG` definitions used for DNA matching.

### Search Algorithm
The tool uses a Breadth-First Search (BFS) to find paths between individuals. The relationship graph treats the following as edges with equal weight:
- Parent ↔ Child
- Sibling ↔ Sibling
- Spouse ↔ Spouse

### Relationship Descriptions
`gedcom_relationship.py` contains the complex logic required to determine common ancestors and describe the relationship path in plain English. This is tested extensively in `tests/test_relationship.py`.

---

## Development Workflow

### Setup
1. Clone the repository.
2. Create a virtual environment: `python -m venv .venv`
3. Activate the environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/macOS: `source .venv/bin/activate`
4. Install dependencies: `pip install -r dev/requirements.txt`

### Running the Application
- **GUI**: `python src/gedcom_navigator_gui.py`
- **CLI**: `python src/gedcom_navigator_cli.py --help`

### Running Tests
The project uses `pytest`. Run all tests from the root directory:
```bash
pytest
```
Tests are organized by module (e.g., `tests/test_data_model.py`).

GUI smoke tests are opt-in because they create real Tk/customtkinter windows and
need a working display session:
```bash
python -m pytest -m gui tests/test_gui_smoke.py
scripts/test-gui.sh          # Linux / WSL Python
scripts/wtest-gui.sh         # Windows Python from WSL
scripts/test-gui.ps1         # Windows PowerShell
```
Run the same `python -m pytest -m gui tests/test_gui_smoke.py` command from the
macOS checkout before a release. GUI failure diagnostics are written under the
ignored `test-artifacts/` directory.

For a report-only coverage snapshot, run:
```bash
dev/run_coverage.sh
```
or on Windows:
```powershell
.\dev\run_coverage.ps1
```

### Caching
To speed up loading, the application caches parsed GEDCOM data in a `cache` directory (usually in the user's home folder). If you change the data model schema, you should increment `_CACHE_VERSION` in `src/gedcom_data_model.py` to invalidate old caches.

---

## Build System

The `dev/` directory contains everything needed to package the application:
- `build.sh` / `build.ps1`: Orchestrates the build process using PyInstaller.
- `gedcom_navigator_gui.spec`: PyInstaller configuration for the GUI.
- `gedcom_navigator_cli.spec`: PyInstaller configuration for the CLI.
- `build-and-release.sh`: custom script that will only work if your development environments are identical to mine. It builds the Linux version in the current environment (assumes WSL), Windows version via a locally installed PowerShell session, and the Mac version via ssh to a local host called `mac`. Assuming that is all successful, it uploads the latest release to github.
- `build-mac-appstore.sh`: custom script to build and submit the application to the App Store. Only works if you have all of the App Store infrastructure and keys available locally.

When adding new files to `src/`, ensure they are included in the `.spec` files if they are not automatically picked up by PyInstaller's analysis.
