# Changelog

## [0.4.0] - 2026-05-06
- Major rewrite
- Refactor code into smaller modules
- Removed vestigial "load" button

## [0.3.1] - 2026-05-05

- Various fixes to improve "look" on MacOS
- Added progress bars on loading

## [0.3.0] - 2026-05-05

### Added

- **Biography section in Show Person window** — a new `── Biography ──` section now appears at the top of every Show Person popup, showing Birth, Married (with spouse name, date, and place), Died, and Buried events extracted from the GEDCOM record. Falls back to "(no biographical information found)" when none of these events are recorded.
- **Name format preference** — a new "Name format" option in Preferences (Display section) lets the user choose between "First Last" (default) and "Last, First" display order. The choice persists across sessions and affects every name shown in the people list, results pane, Show Person window, and family sections. Requires no manual reload.
- **Adjustable fuzzy threshold in Preferences** — the fuzzy-search similarity cutoff (previously a hardcoded constant) is now a configurable spinbox in Preferences under "Search defaults", accepting values from 0.00 to 1.00. Lower values allow more matches; higher values are stricter. The value is persisted to `settings.json`.
- **`gedcom_strings.py` — localization-ready string module** — all English user-facing strings displayed by the GUI have been extracted into a new `src/gedcom_strings.py` file. To translate the application, copy the file and replace the string values; no changes to the main GUI code are required.

### Changed

- **GEDCOM data model: surname and given name parsed separately** — the individual record now stores `surname` and `given_name` fields in addition to the combined `name`, extracted from the standard GEDCOM `/Surname/` slash notation. These fields drive the new Last, First name order display.
- **GEDCOM data model: marriage date and place stored on families** — FAM records now capture `marr_date` and `marr_place` from their `MARR` sub-records. These fields are used by the Biography section to display full marriage details.
- **Cache version bumped to 3** — the on-disk parse cache schema has changed. Existing cache files are automatically detected as stale and silently replaced on next load; no manual cache clearing is needed.
- **Script filenames renamed to snake\_case** — `gedcom-dna-finder-cli.py`, `gedcom-dna-finder-gui.py`, `generate-icon.py`, and the two PyInstaller `.spec` files have been renamed to use underscores (`gedcom_dna_finder_cli.py`, `gedcom_dna_finder_gui.py`, `generate_icon.py`, `gedcom_dna_finder_cli.spec`, `gedcom_dna_finder_gui.spec`) for consistency with Python package conventions.
- **PyPI GUI entry point renamed** — the console-script entry point in `pyproject.toml` was updated from `gedcom-dna-finder-gui` to `gedcom_dna_finder_gui` to match the renamed launcher.
- **Build scripts updated** — all shell and PowerShell build scripts (`build.sh`, `build.ps1`, `build-linux.sh`, `build-mac.sh`, `build-mac-appstore.sh`, `build-pypi.sh`, `build-pypi.ps1`, `build-and-release.sh`) updated to reference the renamed files and standardized to consistent tab indentation.

## [0.2.9] - 2026-05-04

### Added

- **Clickable hyperlinks in markdown viewer** — links in the Help, Keyboard Shortcuts, License, and Privacy Policy windows are now active. Clicking a `[text](url)` link opens it in the system's default web browser. Previously the link text was styled in the link color but had no click behavior.

### Changed

- **License page** — added a link to the GitHub source repository.
- **Build process** — various changes to build process to get code in shape for App Store submission

## [0.2.8] - 2026-05-02

- Minor bump

## [0.2.7] - 2026-05-02

### Fixed

- **Mac App Store rejection (Guideline 2.5.1 — private API)** — the bundled Tk framework previously referenced `_NSWindowDidOrderOnScreenNotification`, a private AppKit API that causes App Store rejection. `build-mac.sh` now installs Homebrew's `tcl-tk` formula (Tk 9.x) before building, and when the pyenv Python path is taken it sets `CPPFLAGS`/`LDFLAGS`/`PKG_CONFIG_PATH` so that Python's `_tkinter` extension is compiled against Homebrew's Tk instead of the macOS system Tk 8.5.9 (which carries the offending symbol). `build-mac-appstore.sh` now runs a pre-submission check using `strings` against the bundled `Tk` binary and aborts with a clear error message if the private API symbol is found, preventing a non-compliant build from ever reaching Apple's review queue.

## [0.2.6] - 2026-05-01

### Added

- **"Show IDs" preference** — a new "Show IDs" checkbox in Preferences (under a new "Display" section) controls whether raw GEDCOM ID codes are shown anywhere in the application. Off by default. When disabled: person IDs (e.g. `[@I123@]`) are omitted from every name link in the results pane, family sections, and relationship path results; `xref` codes are hidden from raw GEDCOM records in the Show Person window; tag ID codes (e.g. `@MT1@`) are removed from the tag definitions viewer; and the `(@ref@)` suffix is stripped from DNA marker descriptions. Toggling the setting and clicking OK immediately re-renders the current result. The preference is persisted to `settings.json` and restored on next launch.

### Fixed

- **DNA marker labels** — the internal label prefix for source-citation markers was shortened from `Source citation PAGE:` to `Source citation:`, and the label for resolved `_MTTAG` pointer markers was renamed from `_MTTAG:` to `Tag:`, for cleaner display in the results pane.

## [0.2.5] - 2026-05-01

### Added

- **Clickable person links in relationship path results** — every person name displayed in the "Relationship path" results pane is now a clickable blue underlined hyperlink. Clicking a name navigates to that person in the people list and runs "Find Nearest DNA Matches", consistent with name links elsewhere in the UI. The "Relationship path:" header and each "Path #N" line are rendered in bold for easier scanning.

### Improved

- **Relationship descriptions for spouse-crossing paths** — a new `segmented()` helper in `describe_relationship` splits a path at the first spouse crossing and describes each segment independently before falling back to the raw edge chain. Paths like `cousin → spouse → ancestor` now produce readable labels such as "first cousin once removed's wife's great-grandfather" instead of an opaque possessive chain.
- **Popup windows centered on parent** — the Tag definitions window and the Show Person window now open centered over the main application window instead of appearing at an arbitrary screen position.

## [0.2.2] - 2026-04-30

- Major refactor and rationalization of code
- Better data hygiene/privacy protection
- Eliminated some edge case bugs

### Added

- **Top N and Max Depth persist across sessions** — the "Top N" and "Max Depth" spinboxes in the action bar are now also exposed in the Preferences dialog under a new "Search defaults" section. Values saved there are written to `settings.json` and restored on the next launch, so users no longer need to re-enter their preferred search depth after restarting the application.
- **Clear Cache button in Preferences** — the Preferences dialog now includes a "Cache" section with a "Clear Cache…" button as an alternative to the existing Menu → Clear cache… entry, making it easier to find in the same place as other application settings.
- **Privacy Policy menu item** — a new "Privacy Policy" entry at the bottom of the Menu opens a formatted window explaining what data the application stores locally, confirming that it makes no network requests, and describing the cache and its contents.
- **PyPI packaging** — the project is now structured for distribution on PyPI as `gedcom-dna-finder`. A `pyproject.toml` with full metadata and entry points, a `gedcom_dna_finder/` Python package with `gedcom-dna-finder` (CLI) and `gedcom_dna_finder_gui` (GUI) console scripts, a `hatch_build.py` custom build hook that bundles `src/` scripts and assets into the wheel, and a `dev/build-pypi.ps1` build-and-upload script (supports `-TestPyPI` flag) are all included.

### Changed

- **People list: Birth and Death replace Years** — the single "Years" column in the people list has been replaced by separate "Birth" and "Death" columns, each showing only the respective year. Both columns are independently sortable by clicking the column heading.
- **People list: ID column removed** — the GEDCOM ID column has been removed from the people list to reduce visual clutter. IDs continue to appear in results, Show Person windows, and the name links throughout the interface.

### Fixed

- **Main window clipped on launch with Large font** — when the application was configured to use the Large font and restarted, the main window was sometimes rendered at a width too narrow to show all action-bar controls. A single `update_idletasks()` call was insufficient for Tk to finish propagating geometry across all widget nesting levels before the width check ran. The fix schedules an additional `_refit_windows` call via `after(0, …)` so the check runs inside the event loop after layout has fully settled.
- **Preferences window clipped with Large font** — the Preferences dialog used a hardcoded `420×360` pixel size set before any widgets were created, which was too small when the Large font was active. The dialog is now hidden on creation, all widgets are packed, `update_idletasks()` is called to compute the true required dimensions, and the window is then sized to fit and revealed — ensuring it is always the right size for the current font.

## [0.1.0] - 2026-04-29

### Added

- **Preferences dialog** — a new "Preferences…" entry at the top of the Menu opens a Preferences window with application settings. The first setting is **Font size**, with three choices: Small (9 pt), Medium (10 pt), and Large (13 pt UI / 12 pt monospace). Clicking a radio button applies the change immediately as a live preview; Cancel reverts to the previous size and OK saves the choice. The preference is persisted to `settings.json` and restored on next launch.
- **Themes** - a new option in Preferences for color schemes.
- **Universal font scaling** — changing the font size in Preferences updates every part of the application simultaneously: the people list, results pane, all open Show Person windows, the tag definitions viewer, and all other popup windows. The Treeview row height adjusts automatically to match the new font metrics.
- **Show Person window remembers position and size** — when the Show Person window is moved or resized, its geometry is saved to `settings.json`. The next time a Show Person window is opened it appears at the same location and with the same dimensions as when it was last closed. The position is saved with a short debounce so ordinary repositioning does not cause excessive disk writes.

### Improved

- **Windows resize automatically on font change** — after a font size change, all open windows (main window and any Toplevel popups) are measured against their minimum required size and expanded if the current geometry is too small to display all controls. The main window's minimum resizable width is also updated to reflect the new font. Windows never shrink automatically, preserving the user's chosen layout when switching to a smaller font.

## [0.0.9] - 2026-04-29

### Added

- **Family section in results pane** — whenever DNA match results are displayed, a new "Family" section now appears immediately before "Path to Home Person", listing the selected person's parents, siblings, and children with name, lifespan, and GEDCOM ID.
- **Family section in Show Person window** — the "Show Person" popup now opens with the same family summary (parents, siblings, children) at the top, above the raw GEDCOM record, under a "── GEDCOM Record ──" divider.
- **Sortable column headings** — clicking any column heading in the people list (Name, Years, DNA?, ID) sorts the list by that field. Clicking the same heading again reverses the order. The active sort column is indicated by ▲ (ascending) or ▼ (descending). Years sorts by birth year with unknown dates last; DNA? groups flagged rows together.
- **Clickable name links** — every person name displayed in the results pane and the Show Person window is rendered as a blue underlined hyperlink. Clicking a name in the results pane selects that person in the list (clearing search filters if needed) and runs "Find Nearest DNA Matches" for them. Clicking a name in the Show Person window navigates to that person within the same window rather than opening a new one. The cursor changes to a hand pointer on hover.

## [0.0.8] - 2026-04-28

### Added

- **Filter field** — a new "Filter:" text entry below the "Find:" box narrows the people list by searching the complete raw GEDCOM record for each person, not just the name. Type any text that appears in a GEDCOM entry — a location, source, event type, or any other field — to restrict results to only those individuals whose records contain that text. `Ctrl+I` jumps to the Filter box and selects all text.
- **Enter key moves focus to list** — pressing Enter in either the Find or Filter box immediately moves keyboard focus to the people list, so you can navigate straight to a result without reaching for the mouse.
- **Escape clears results** — the Escape key now triggers the same "clear results" action as `Ctrl+L`, providing a quick way to reset the results pane from anywhere in the window.

### Improved

- **Tab order** — Tab now follows a logical left-to-right, top-to-bottom sequence through the main controls: Find → Filter → people list → results pane → Top N → Max Depth → Set Home → Show Person → Find Nearest DNA Matches. Shift+Tab traverses the same chain in reverse. The vertical scrollbar on the people list is excluded from tab traversal.
- **Focus on list entry** — when focus moves to the people list (via Enter from a search box, `Ctrl+L`, or Tab), the first row is automatically selected if no row is already focused, so arrow-key navigation works immediately without an extra keypress.
- **Clear results behavior** — `Ctrl+L` (and Escape) now also clears the Find box and resets the last result state, then returns focus to the Find box for a clean start.

## [0.0.7] - 2026-04-28

### Added

- **Keyboard shortcuts** — twelve Ctrl-key shortcuts are now active throughout the application: Ctrl+F (jump to Search), Ctrl+D (toggle DNA-flagged filter), Ctrl+U (toggle Fuzzy search), Ctrl+O (Browse file), Ctrl+N (Find Nearest DNA Matches), Ctrl+S (Show Person), Ctrl+H (Set Home), Ctrl+P (Find Relationship Path), Ctrl+T (View tag definitions), Ctrl+C (Copy results), Ctrl+L (Clear results). Ctrl+C defers to the text widget's own copy behavior when the results pane has keyboard focus.
- **Button mnemonics** — the shortcut letter is underlined on seven buttons: Find (F), Copy (C), Clear (l), Show Person (S), Set Home (H), Find Nearest DNA Matches (N), and View tag definitions… (t).
- **Keyboard shortcuts help page** — a new "Keyboard shortcuts" entry in the Menu opens a formatted reference listing all shortcuts (`docs/KEYBOARD_SHORTCUTS.md`).
- **GEDCOM parse cache** — parsed GEDCOM data is now cached on disk as a binary pickle file (stored in the application's config directory under `cache/`). On subsequent opens the cache is loaded instead of re-parsing the file, making large GEDCOM files open almost instantly. The cache is invalidated automatically when the source file's modification time changes or when the Tag keyword or Page marker settings differ from the values used to build the cache.

## [0.0.6] - 2026-04-28

### Added

- **Compact ancestor/descendant labels** — `describe_relationship` now uses ordinal-prefixed "Nth-great" notation for deep ancestors and descendants. Ancestors four or more generations up are labelled "2nd-great-grandfather", "3rd-great-grandfather", etc. instead of "great-great-grandfather", "great-great-great-grandfather", and so on. The same convention applies to grandchildren and to great-aunts/uncles.
- **Smarter relationship descriptions for indirect paths** — when "Find Relationship Path" returns alternate routes that navigate through a spouse node to reach a niece, cousin, or similar relative, the function now recognizes the relationship correctly instead of falling back to a possessive chain like "brother's wife's daughter". Interior spouse edges (representing navigation within a family unit) are stripped before classification. A trailing sibling edge at the end of a descent path is also handled: the sibling of an Nth cousin once removed is still an Nth cousin once removed.
- **Auto-reopen last file on startup** — the application now automatically reopens the most recently loaded GEDCOM file when launched, provided the file still exists at its previous path.
- **Home person** — a new "Set Home" button in the action bar designates the selected person as the *home person* for the currently loaded GEDCOM file. The choice is persisted in the settings file and restored automatically when the same file is reopened. Whenever DNA match results are displayed, a "Path to Home Person" section is appended showing the relationship label and edge-by-edge path from the selected person to the home person.
- **Bold match headers** — the name-and-distance header line for each DNA match result (e.g. `#1: John Smith … (distance: 3 edges)`) is now rendered in bold, making it easier to scan multiple results at a glance.
- **Auto-sized initial window** — after building the UI, the application measures the minimum width Tk requires to display all controls and widens the window to that size if the default `1100 px` would clip any button. The minimum resizable width is updated to match.

### Fixed

- **Home person lost across sessions** — `_save_history` previously wrote `{"recent_files": […]}` as the entire settings file, silently erasing the `home_persons` map every time a file was opened. It now merges the updated list into the existing settings rather than replacing the file.

## [0.0.5] - 2026-04-27

### Added

- **Show Person window** — a new "Show Person" button (to the left of "Find Nearest DNA Matches") opens a popup displaying the complete raw GEDCOM record for the selected individual, with all fields and sub-records shown in standard GEDCOM line format.
- **Multi-path relationship finder** — the "Find Relationship Path" feature now pre-computes the biological ancestor and descendant sets for the starting person before labelling each discovered path.

### Fixed

- **Spurious "step-" labels on alternate paths** — when "Find Relationship Path" returned multiple routes to the same person, paths that reached a biological ancestor or descendant via an intermediate spouse edge (e.g. `me → mother → grandmother → grandfather`) were incorrectly labelled "step-grandfather" instead of "grandfather". The relationship labeller now checks whether the target is a known biological ancestor or descendant and uses the direct term regardless of which route the path took.

## [0.0.4] - 2026-04-27

### Added

- **ZIP file support** — both the CLI and GUI now accept `.zip` files as input. The first `.ged` or `.gedcom` entry found inside the archive (preferring top-level files over subdirectory entries) is extracted automatically and used for parsing.
- **Alternate name matching** — GEDCOM records can contain multiple `NAME` lines for the same individual (e.g., a birth name and a married name). All names are now collected and searched, so a query matching any of a person's recorded names will find them. Previously only the first `NAME` line was considered.
- **Fuzzy name search** — an optional fuzzy matching mode (CLI: `--fuzzy` / `--fuzzy-threshold`; GUI: "Fuzzy" checkbox) tolerates typos and spelling variants using `difflib.SequenceMatcher`. In the GUI the fuzzy filter also applies to the people list.

### Changed

- CLI `--help` and inline usage examples updated to document the new options.
- HELP.md and README.md updated to reflect ZIP support, fuzzy matching, and alternate name matching.
- GUI file browser now includes `*.zip` in the GEDCOM file filter.
- GUI status bar briefly shows the name of the `.ged` file extracted from a ZIP before loading completes.
