# Changelog

## [1.2.0] - 2026-05-15

### Added

- **Graphical relationship view** - relationship descriptions in DNA-match results, home-person paths, and relationship-path results are now clickable. Clicking a relationship opens a scrollable "Relationship Graph" window that lays out each person in the path by generation, labels the relationship edges, and highlights the start and end people. Visualizations can be copied to clipboard or saved to a file.
- **Copyable relationship graphs** - the relationship graph window includes a Copy button and keyboard shortcut support. On Windows the graph is copied as a bitmap; on other platforms the canvas is copied as PostScript where supported by Tk.
- **Common ancestor reporting** - relationship result sections now show the nearest common biological ancestor or ancestors when one can be found, with clickable ancestor names. In-law-only paths explicitly report that no common ancestor was found.
- **Data-model API for common ancestors** - `GedcomDataModel` now exposes `find_common_ancestors()`, backed by relationship helpers that rank the closest shared ancestors and preserve ties such as both parents of siblings or both grandparents of first cousins.
- **Dedicated source modules** - parsing, search/pathfinding, display formatting, GUI background work, GUI search/list handling, and GUI result rendering now live in separate modules: `gedcom_parser.py`, `gedcom_search.py`, `gedcom_display.py`, `gedcom_gui_background.py`, `gedcom_gui_search.py`, and `gedcom_gui_results.py`.
- **Repository agent guidance** - `AGENTS.md` now documents source-running commands, build commands, architecture, data flow, GUI structure, DNA flag detection, and settings storage for future maintenance work.

### Changed

- **Graph-aware relationship wording** - relationship classification now uses an indexed family lookup when family data is available, so biological shortcuts are only applied when the underlying family graph supports them.
- **Safer sibling and spouse compaction** - spouse-to-child detours, parent-child sibling equivalents, sibling-parent shortcuts, and repeated sibling hops are now validated against the family graph before being collapsed into simpler relationship terms.
- **Fewer false biological labels** - paths through marriage bridges, half-sibling parents, and a spouse's non-shared child now fall back to explicit possessive descriptions instead of being mislabeled as direct cousins, parents, nieces, or nephews.
- **Relationship search deduplication uses graph-aware labels** - alternate path discovery now prepares a reusable family lookup and uses it while deduplicating relationship labels, reducing incorrect merging of paths that look similar as edge sequences but differ biologically.
- **Relationship path headings simplified** - path result headers now show `Path #N:` and put the relationship wording on the clickable relationship line, avoiding duplicated label text.
- **Result rendering moved out of the main GUI class** - result-pane rendering, path reversal, graph display, person navigation from results, marker formatting, display-name formatting, and family summary helpers now live in `ResultsMixin`.
- **Search and load handling moved out of the main GUI class** - GEDCOM browsing/loading, ZIP extraction, settings-change debouncing, people-list filtering/sorting, fuzzy matching, and DNA-match search launching now live in `SearchMixin`.
- **Background task handling moved out of the main GUI class** - progress-bar animation, cancelable worker-thread orchestration, busy-state management, and slow-search popup handling now live in `BackgroundTaskMixin`.
- **Core module is now a compatibility facade** - `gedcom_core.py` now re-exports parser, search, and display helpers from their focused modules so existing callers can continue importing the old names while the implementation is easier to maintain.
- **Help text updated for graphs** - the user help now mentions graphical relationship visualization and notes that wider relationship searches can take longer on large trees.
- **Line-ending normalization tightened** - `.gitattributes` now uses LF for most files while preserving CRLF for PowerShell scripts.
- **Test cache/temp directories localized** - `pytest.ini` now points pytest cache and temporary files at workspace-local `.pytest_cache` paths.
- **Release metadata updated** - the package version is now `1.2.0` with release date `2026-05-15`.

### Fixed

- **False third-cousin style labels through marriage bridges** - relationship paths that cross a sibling-spouse-sibling marriage bridge are no longer collapsed into unsupported biological cousin terms.
- **Incorrect labels for a spouse's child from another relationship** - a sibling's spouse's non-shared child is now described as a possessive in-law chain, such as `sister-in-law's son`, rather than as a niece or nephew.
- **Incorrect labels for half-sibling parents** - a half-sibling's other parent is no longer treated as the selected person's own parent when the family graph does not support that shortcut.
- **Over-broad spouse detour stripping** - spouse-to-child simplification now requires evidence that both spouses are co-parents of the child being reached.
- **Over-broad sibling normalization** - sibling-equivalent shortcuts now require shared-family evidence before collapsing paths, avoiding biological labels that are not proven by the GEDCOM data.
- **Result graph sizing on varied displays** - graph windows size themselves to the generated content when possible and otherwise fit within the available virtual screen bounds.
- **Graph label readability** - graph node labels wrap based on measured font width, endpoint nodes are marked as START and END, and graph colors are derived from the active application theme for light/dark readability.

### Tests

- **Common ancestor tests** - data-model and relationship tests now cover shared parents, shared grandparents, and in-law-only paths with no biological common ancestor.
- **Graph-aware relationship tests** - relationship tests now cover marriage-bridge false positives, non-shared spouse children, shared spouse children, and half-sibling parent edge cases.

## [1.1.0] - 2026-05-14

### Added

- **Cancelable long-running searches** — DNA match searches and relationship path searches now run in a background worker with an animated progress indicator. Searches that are likely to take a while show a modal "Searching" window with a Cancel button, so the application remains responsive even on very large trees or high max-depth settings.
- **Cooperative cancellation in the search engine** — the shared BFS/pathfinding code now accepts a cancellation event and raises `SearchCancelled` when the user cancels a long search. This is used by the GUI and covered by tests.
- **Progress guidance for expensive searches** — slow-search popups now explain that reducing Max Depth can make searches faster.
- **Standalone tooltip module** — tooltip handling has moved into `gedcom_tooltip.py`, with richer multi-line tooltip formatting, bold first lines, global enable/disable support, improved screen-edge placement, and better macOS tooltip window behavior.
- **Target-person result header** — the results pane now shows a styled header with the selected person's display name and lifespan, making it easier to keep track of whose results are currently shown.
- **Fixed-width relationship connectors** — relationship paths now use a cleaner Unicode connector style with centered edge labels so every arrow and relationship description has the same visual width and names align vertically.
- **Validation errors for unusable GEDCOM files** — empty files, files without a `HEAD` record, and files without any `INDI` records now produce clear model errors instead of silently loading an empty tree.
- **Release/build metadata** — the package version is now `1.1.0` with release date `2026-05-14`, and the macOS bundle metadata declares `ITSAppUsesNonExemptEncryption: False`.
- **Repository housekeeping files** — `.gitattributes` now normalizes text handling, `.gitignore` now excludes local `.ged` files, `docs/TODO.md` captures future work, and the developer word list has been expanded for project-specific terms.

### Changed

- **More capable relationship path search** — alternate path discovery now searches a wider area around the shortest path, raises the exploration cap, oversamples candidate paths before filtering, deduplicates paths by relationship label, and sorts results so simpler relationship descriptions appear first.
- **Better discovery of compound in-law paths** — pathfinding now adds targeted spouse expansion from either endpoint and a marriage-bridge expansion for paths joined through spouses near both endpoints. This lets the application find longer compound relationships that the previous shortest-path-bounded search missed.
- **Redundant path filtering improved** — spouse detours and limited child-to-parent detours are now recognized as equivalent to shorter paths, reducing duplicate or unhelpful alternate routes.
- **Relationship labels are more concise when the family graph supports it** — when a path-specific possessive chain is technically valid but a shorter biological relationship is available, the app now prefers the more efficient label, such as `fourth cousin` instead of a long chain of in-law and ancestor terms.
- **Relationship classification handles more real-world edge cases** — sibling-equivalent patterns are normalized, cousin siblings can collapse to the same cousin term, direct in-law labels are preserved when appropriate, and spouse detours are stripped only when they represent a family-unit detour rather than a genuine lateral connection.
- **Relationship rendering owns layout, not translation strings** — `gedcom_strings.py` now keeps plain edge-label vocabulary while the GUI renderer owns arrows, indentation, and padding.
- **Relationship summaries now use family context throughout the GUI** — DNA match results, home-person paths, reverse-path views, and relationship-path dialogs all pass the family graph into `describe_relationship()` so concise biological terms can be chosen consistently.
- **Results pane text is cleaner** — result headings now use "Closest DNA Matches"; relationship and path labels are shorter; distance text was removed from the main result headers; horizontal separators divide results; and DNA marker/path sections are easier to scan.
- **Main window layout is more robust** — the app now uses a classic `tk.PanedWindow` with explicit pane minimums, a fixed minimum width for the results pane, recalculated people-list column widths, and pane refreshes after font/theme changes to avoid clipped controls and oversized left panes.
- **People-list columns size from font metrics** — Name, Birth, Death, and DNA columns now compute their widths from the active UI font and heading text, improving large-font and macOS layouts.
- **Default Max Depth reduced to 10** — the saved/default search depth now favors faster everyday searches, while tooltips explain that larger values such as 50 are useful for finding very distant relationships.
- **Search and DNA-setting changes are debounced** — search/filter/fuzzy changes, result-count/depth changes, and tag/page-marker changes are now delayed briefly before refreshing or reloading, reducing unnecessary recomputation while typing.
- **Busy state handling tightened** — while long operations are running, search and file-open controls are disabled and restored after completion or cancellation.
- **macOS menu behavior refined** — the About item now appears in the Apple menu on macOS, Preferences is registered with the standard macOS command hook, and the non-macOS Help/About menu layout is preserved separately.
- **Documentation updated for current behavior** — README and Help text now describe faster large-tree exploration, fuzzy matching, filtering by additional GEDCOM fields, relationship-path expectations, CTKToolTip as a GUI dependency, current source-install commands, and current download ordering.
- **Source launcher behavior improved** — `start.sh` now reuses an existing active virtual environment before creating or activating a local one, and installs `dev/requirements.txt` only when needed.
- **Build/release scripts cleaned up** — release scripting gained shellcheck-oriented comments and safer local/remote option handling, while the PyInstaller spec carries the new macOS encryption declaration.
- **PyPI entry-point wrappers documented** — the CLI and GUI wrapper `main()` functions now include docstrings clarifying their packaging role.

### Fixed

- **GUI freezes during distant searches** — CPU-heavy graph searches now periodically yield and can be canceled, avoiding a stuck UI when searching very large trees.
- **Blank or invalid GEDCOM loads** — the parser and data model now reject unusable inputs with an explanatory error and avoid writing/using empty cache entries.
- **CLI invalid-file handling** — the command-line tool now reports model errors and exits non-zero when parsing does not produce a usable family model.
- **Incorrect "step-" relationship labels** — biological ancestors reached through alternate or spouse-involved paths are no longer mislabeled as step-relatives when ancestor context is available.
- **Over-aggressive spouse stripping** — spouse-to-sibling paths are no longer collapsed into incorrect step-child style relationships; only spouse-to-child detours are treated as removable family-unit detours.
- **Verbose biological relationships** — long possessive descriptions are replaced by shorter valid biological terms when the family graph proves the relationship, while direct in-law labels such as `father-in-law` are not replaced by distant cousin terms.
- **Too few relationship paths after filtering** — pathfinding now oversamples before removing detours, so asking for multiple paths is less likely to return fewer results than requested only because duplicate variants were pruned.
- **Left pane/result pane sizing problems** — pane minimum sizes and sash placement were reworked to keep action controls, people-list columns, and the results pane visible across platforms and font sizes.
- **Tooltip display glitches** — tooltip windows now handle multi-line messages, typing in entry fields, display edges, macOS transient behavior, and redraw timing more reliably.
- **Preferences modality** — the Preferences window now grabs focus like the other dialogs, reducing accidental interaction with the main window while settings are open.
- **About window version display** — the About dialog now includes the current version and release date in its markdown preamble.

### Tests

- **Invalid model tests** — core and data-model tests now cover empty GEDCOM input, files without individuals, and data-model error propagation.
- **Cancellation tests** — BFS DNA-match and all-path search tests now verify that a set cancellation event stops the search.
- **Relationship edge-case tests** — the relationship suite now covers spouse/lateral edge cases, cousin-sibling normalization, concise biological relationship preference, and protection against replacing direct in-law labels with distant biological labels.
- **Test configuration update** — `pytest.ini` now sets a base temporary directory for test runs.

## [1.0.0] - 2026-05-10

### Architecture

- **Modular GUI refactor** — the monolithic `gedcom_dna_finder_gui.py` has been split into focused modules: `gedcom_gui_appearance.py` (theming, fonts, menus, keybindings), `gedcom_gui_dialogs.py` (pop-up windows), `gedcom_markdown.py` (markdown renderer), `gedcom_relationship.py` (BFS ancestor/descendant helpers and plain-English labels), and `gedcom_theme.py` (theme constants, OS dark-mode detection, Tooltip widget).
- **Comprehensive test suite** — a new `tests/` directory contains four test modules (`test_core.py`, `test_data_model.py`, `test_config.py`, `test_relationship.py`) with over 1,600 lines of pytest coverage for parsing, caching, configuration, and relationship labelling. Run via `pytest` or the included `run_tests.sh` / `run_tests.ps1` helpers.

### Added

- **OS dark/light mode detection** — the application now automatically detects the operating system's dark or light mode preference at startup and selects the appropriate default theme, eliminating the need for manual theme selection on first launch.
- **Multiple color themes** — the Preferences dialog now offers several built-in color themes. The chosen theme persists across sessions.
- **"Reverse Path" button** — a new "Reverse Path" button in the results pane recomputes all displayed relationship paths from the other person's perspective (e.g., switching from "your second cousin" to "their second cousin"). Clicking again restores the original direction. Available via keyboard shortcut as well.
- **Configurable max search results** — a "Max search results" spinbox controls how many DNA matches are displayed, independent of the BFS depth limit. The setting is exposed in both the action bar and Preferences and is persisted to `settings.json`.
- **Comprehensive tooltips** — every interactive control in the main window (Find, Filter, Top N, Max Depth, Max search results, all buttons, checkboxes, and text fields) now shows a descriptive tooltip on hover, including the relevant keyboard shortcut where one exists.
- **"File" and "Help" menus** — the single "Menu" button has been replaced with a proper platform-standard menu bar containing a "File" menu (Open, Open Recent, Preferences/Settings, Quit) and a "Help" menu (How to use, Keyboard Shortcuts, Privacy Policy, About). Keyboard shortcut labels appear next to each item, using ⌘ notation on macOS and Ctrl on Windows/Linux.
- **"Open Recent" submenu** — recent GEDCOM files are now accessible directly from File → Open Recent, mirroring standard application conventions.
- **Character encoding auto-detection** — the GEDCOM parser now probes common encodings (UTF-8, UTF-16, Latin-1, CP1252, and the encoding declared in the `CHAR` tag) before falling back to a permissive mode, eliminating parse errors on files produced by legacy genealogy software.

### Changed

- **"Load" button removed** — the file selection field now auto-loads the chosen GEDCOM file immediately, eliminating an extra click. The field still shows the path and can be edited or browsed.
- **Button labels shortened** — "Find Nearest DNA Matches" is now "Find Matches" and "Copy" is now "Copy Results" to better fit the action bar at all font sizes.
- **Relationship algorithm improvements** — several edge cases in `describe_relationship` are handled more accurately, including paths that cross multiple spouse edges and unusual ancestor/descendant combinations.
- **macOS polish** — tooltip rendering, window chrome, and menu behavior have been refined for macOS, including correct corner radii on tooltip windows and platform-appropriate keyboard shortcut notation throughout the UI.
- **Build system** — Windows PyInstaller build (`dev/build.ps1`) updated; all build scripts harmonized. `start.sh` and `start.ps1` convenience launchers added for running from source.

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
