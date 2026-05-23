# Changelog

## [1.9.2] - 2026-05-23

### Added

- **Paths from Tree View** - you can now find the relationship paths from the person who is centered in the Tree View and any other person by clicking on the other person and selecting "Paths".
- **Internationalization (i18n)** — the GUI is now fully localized via GNU gettext. All user-facing strings pass through `gettext`/`_()`, the language can be selected in Preferences, and the choice is persisted across sessions. Shipping translations: German (de), Spanish (es), French (fr), and Hebrew (he). A `locales/` directory holds `.pot` template and per-language `.po` files; compiled `.mo` files are bundled into the release.
- **DeepL translation tooling** — `dev/translate-po-deepl.py` automates gettext `.pot`/`.po` translation via the DeepL API. It preserves Python format placeholders, UI shortcut tokens, and applies a genealogy-specific glossary. Shell and PowerShell wrappers (`translate-po-deepl.sh`, `translate-po-deepl.ps1`) are included.
- **Hebrew and Cyrillic fuzzy search aliases** — the parser generates Latin-script aliases for Hebrew and Cyrillic names at load time. Fuzzy search in both the GUI and CLI can match against these aliases while normal token search remains unchanged. Optional `cyrtranslit` and `hebrew` packages are used when available, with built-in fallback mappings.
- **Debug logging module** — `gedcom_debug.py` provides rotating-file exception logging activated by the `GEDCOM_NAVIGATOR_DEBUG` environment variable (or `GEDCOM_NAVIGATOR_DEBUG_LOG` to set a custom path). `log_exception()` and `log_exception_once()` helpers are called at all silent `except` sites throughout the codebase, so debugging field issues no longer requires a source build.
- **Centralized keyboard shortcut metadata** — `gedcom_shortcuts.py` defines `ShortcutSpec` named tuples for every main-window shortcut. `AppearanceMixin` now registers bindings by iterating `main_window_shortcuts()` rather than hard-coding each sequence, and tests can enumerate shortcuts without touching the GUI.
- **Cross-platform GUI smoke test workflow** — opt-in Tk/customtkinter smoke tests (`tests/test_gui_smoke.py`) can now run on Linux/WSL, Windows-from-WSL, and macOS via `scripts/test-gui.sh`, `scripts/wtest-gui.sh`, and `scripts/test-gui.ps1`. Failure artifacts are written under the ignored `test-artifacts/` directory.

### Changed

- **Display Pane mode selector** — the "Show Person" and "Find Matches" action buttons have been replaced by a segmented button (Profile / Matches / Paths) that switches the main results pane between the three display modes. Selecting a person in the list immediately refreshes the active mode. The preferred startup mode is saved in Preferences.
- **Person profile rendered in main results pane** — the profile view (formerly always a separate popup) is now rendered inline in the Display Pane. Clicking a person navigates to them and renders their biography, family summary, and path to the home person directly in the results area. The standalone Show Person window is still accessible and is used for the interactive family tree.
- **DNA settings moved out of main window** — the Tag Keyword, Page Marker, and Select Tag controls have been removed from the main window's top bar. They now live exclusively in Preferences, reducing visual clutter in the toolbar.
- **Preferences dialog is scrollable** — the Preferences window now uses a `CTkScrollableFrame`, so it stays usable on small displays even as new sections are added. The Language selector appears as a new section.
- **`gedcom_strings.py` now uses gettext** — all string constants are wrapped with `_()`. Dynamic strings whose content depends on the platform (modifier key labels, menu items with shortcut hints) have been converted to accessor functions (`get_menu_how_to_use()`, `get_tip_find()`, etc.) so they are re-evaluated at call time with the active locale.
- **Kinship signature improvements** — `_edge_kinship_signature()` (renamed from `_path_kinship_signature()`) adds three new simplification passes (steps 1.2, 1.3, and 1.6) that canonicalize roundabout paths through parent/child and sibling hops, improving deduplication of genealogically equivalent routes.
- **Tooltip text tracking** — `Tooltip` now stores the text per-widget in a `WeakKeyDictionary` so `update_text()` keeps the stored value in sync, and tests can retrieve current tooltip text without instantiating the underlying CTkToolTip.
- **`wstart.sh` script** — new helper `scripts/wstart.sh` launches the GUI from WSL using the Windows Python interpreter, mirroring how the released Windows build runs.
- **`conftest.py` simplified** — the custom `tmp_path` fixture that worked around Windows ACL issues has been removed now that the CI environment handles this correctly.

### Fixed

- **`Ctrl+L` / clear results removed** — the `_clear_results` action and its Escape/Ctrl+L shortcut have been removed. Clearing the results pane is now implicit in switching display modes.
- **`Ctrl+E` / tree view fixed** - the "tree view" keyboard shortcut was not working; now it is.

### Tests

- **Debug logging tests** — `tests/test_debug_logging.py` covers `debug_enabled()`, `configure_debug_logging()`, `log_exception()`, `log_exception_once()`, and the process-wide exception hooks.
- **Display Pane tests** — `tests/test_gui_display_pane.py` covers mode switching, result rendering for all three modes, and persistence of the selected mode across navigation.
- **Keyboard shortcut tests** — `tests/test_gui_keybindings.py` verifies that main-window shortcuts have no platform conflicts, shortcut help rows match the registered metadata, and action controls expose tooltips in the real GUI.
- **Person dialog tests** — `tests/test_gui_person_dialog.py` covers profile rendering, family tree navigation, and home-path display in the Display Pane.
- **Preferences sizing tests** — `tests/test_preferences_dialog_sizing.py` verifies that the Preferences window correctly sizes itself around the language selector at various window widths.
- **GUI dialog tests** — `tests/test_gui_dialogs.py` covers the Preferences, Tag picker, and person picker dialogs.
- **Transliteration tests** — `tests/test_transliteration.py` covers Hebrew and Cyrillic alias generation, cache preservation, fuzzy-only matching, and fallback Hebrew alias matching.
- **Extended results tests** — `tests/test_gui_results.py` extended with additional coverage for mode-aware reverse-button visibility and profile rendering.
- **Config tests** — `tests/test_config.py` extended with coverage for `get_default_display`/`set_default_display` and `get_language`/`set_language`.

## [1.9.1] - 2026-05-20

### Fixed

- **Family tree sibling layout** - siblings of the center person are now kept contiguous after expanding branches. Unrelated same-row nodes (such as an uncle's children) can no longer split the center sibling group. New layout passes `enforce_sibling_adjacency`, `enforce_parent_child_alignment`, `enforce_child_alignment`, `compact_sibling_side_gaps`, and `compact_child_row_clusters` are applied in `layout_family_tree` to improve overall tree geometry.
- **PNG export bold text** - graph PNG exports now resolve the correct bold (and italic) font file from the system font directories on Windows, macOS, and Linux before falling back to faux-bold rendering. A new `_draw_pillow_text` helper applies a second offset pass when no styled font face can be found, so bold node labels are no longer silently rendered in the regular weight.
- **Family tree center node styling** - the center person node in the interactive family tree now uses a distinct bold font for the name and a highlighted fill color, with the name and lifespan detail rendered as separate text blocks at the correct vertical positions.
- **Graph button tag constant** - `GraphCommonMixin` now exposes `_GRAPH_BUTTON_TAGS` so family-tree and path-graph button tags are referenced from a single class-level tuple rather than scattered literals.
- **Start script robustness** - `scripts/start.ps1` and `scripts/start.sh` now change to the project root first, activates the venv before checking for Python, and improves the error message when Python is not found.

### Tests

- **Graph export tests** - new `tests/test_graph_export.py` covers font-file candidate ordering (Windows bold face preferred), SVG bold font-weight output, and faux-bold PNG rendering when no styled font face is available.
- **Family tree layout tests** - `tests/test_gui_results.py` extended with `test_family_tree_center_siblings_stay_contiguous_after_uncle_children` and additional sibling-adjacency layout cases.

## [1.9.0] - 2026-05-19

- Testing release before 2.0.0. Will focus on bug fixes and polish until 2.0.0.

### Added

- **Interactive family tree view** - the Show Person window now opens in an interactive canvas-based family tree by default, showing the selected person alongside their parents, siblings, spouses, and children. Nodes are expandable and clickable; clicking a person navigates to them in the main window. A Shift-click on the Show Person button switches to the raw GEDCOM profile view instead.
- **Back/Forward navigation** - navigation history is tracked across all person views. Dedicated keyboard shortcuts (Alt+Left/Right on Windows/Linux, Cmd+[/] on macOS) and browser-style back/forward controls allow retracing navigation steps across DNA match searches, relationship paths, and person detail jumps.
- **Married name search** - a new "Married names" checkbox in the search bar searches women under their husband's surname derived from GEDCOM family records, in addition to their recorded names. The derived names are indexed at load time without requiring extra GEDCOM `NAME` lines.
- **Jumbo font size** - a new "Jumbo" option in Preferences sets the UI to 20 pt and the results pane to 23 pt monospace for high-DPI or accessibility use.
- **Zoom in results pane** - the results pane now supports Ctrl+Plus/Minus/0 and Ctrl+scroll-wheel to zoom the text size independently of the global font setting.
- **Zoom module** - `gedcom_zoom.py` centralizes keyboard and mouse-wheel zoom shortcut binding (`bind_zoom_shortcuts`) and a `TextZoomController` class used by the results pane and documentation windows.
- **Tag collection in parser** - the parser now stores all `_MTTAG`-resolved tag names in `indi['tags']` in addition to DNA-flagged markers, making the full tag list available without a second parse pass.

### Changed

- **Application renamed** - the app is now GEDCOM Navigator across source entry points, package metadata, build scripts, PyInstaller specs, macOS bundle metadata, release artifact names, and documentation. The Python package directory has been renamed from `gedcom_dna_finder` to `gedcom_navigator`.
- **DNA flags applied at load time, not cached** - `apply_dna_flags()` in `gedcom_parser.py` re-populates `dna_markers` and `tags` from already-parsed raw records. The cache no longer stores the DNA keyword or page marker, so changing these settings no longer invalidates the cache (cache version bumped to 5). `GedcomDataModel.reflag()` re-applies flags in-place without touching the cache or re-reading the file.
- **DNA settings change is instant** - changing the Tag Keyword or Page Marker now calls `model.reflag()` and refreshes the people list in-place instead of reloading the entire GEDCOM file.
- **GUI refactored into additional focused modules** - `gedcom_gui_dialogs.py` has been trimmed to tag picker, person picker, path finder, and preferences dialogs. Person detail logic now lives in `gedcom_gui_person_dialog.py`; help and documentation dialogs in `gedcom_gui_help_dialogs.py`; shared graph canvas helpers in `gedcom_gui_graph_common.py`; relationship path graph rendering in `gedcom_gui_path_graph.py`; graph layout computation in `gedcom_gui_graph_layout.py`; and family tree canvas rendering in `gedcom_gui_family_tree_render.py`.
- **Family tree layout helpers extracted** - `gedcom_family_tree.py` provides pure functions for building a family graph from GEDCOM families, computing column/row layout for the tree canvas, and enumerating expandable relationship categories.
- **Window focus/raise helper** - `AppearanceMixin._raise_window()` brings a Toplevel to the front and gives it keyboard focus reliably on Windows (where `lift()` alone cannot steal focus from background windows) with a retry scheduled after 150 ms.
- **Font scaling corrected on Windows** - named fonts now use the negative-pixel size convention (`size=-abs(px)`) on Windows to stay in sync with CTkFont instances, eliminating inconsistent sizing in mixed Tk/CTk dialogs. All live CTkFont instances are walked and updated on font-size change, and the CTk theme default is updated so newly created fonts inherit the correct size.
- **Name search supports extra name aliases** - `individual_names()`, `token_match()`, `fuzzy_score()`, and `individual_matches_query()` in `gedcom_name_search.py` accept an `extra_names` keyword argument so callers can inject derived names (such as married names) without modifying the underlying individual record.
- **macOS build and runtime fixes** - multiple stability and compatibility fixes for macOS including tooltip rendering, window management, and build script hardening.

### Tests

- **DPI scaling patch tests** - `test_dpi_patch.py` verifies that the Windows DPI scaling patch replaces `ScalingTracker.get_window_dpi_scaling` and correctly maps common DPI values (96, 120, 144, 168, 192) to their expected scaling factors.
- **GUI refactor import tests** - `test_gui_refactor_imports.py` statically checks all GUI mixin split modules for unresolved global references, catching moved callback helpers whose imports were not migrated with them.
- **Name search extra-names tests** - `test_name_search.py` now covers token matching and fuzzy scoring with injected extra name aliases.
- **Extended GUI results tests** - `test_gui_results.py` has been substantially expanded to cover navigation, result rendering, and graph interaction.

## [1.3.0] - 2026-05-16

### Added

- **User-initiated update checks** - the Help menu now includes "Check for updates", which checks the latest GitHub release in a background thread and reports whether a newer version is available, the current release is up to date, or the check failed.
- **Update-check support module** - `gedcom_update.py` now handles GitHub release lookup, semantic-version parsing, update comparison, network errors, and unreadable release responses.
- **Shared name-search engine** - `gedcom_name_search.py` centralizes exact GEDCOM ID lookup, ID substring matching, order-independent token matching, and fuzzy candidate ranking for both the CLI and GUI.
- **Graph export helper module** - `gedcom_graph_export.py` now owns SVG and PNG rendering for relationship graph canvases, including Tk canvas shapes, text wrapping, dashed lines, arrowheads, and Pillow-backed PNG output.
- **Clickable graph people** - people shown inside relationship graph nodes can now be clicked to close the graph and navigate to that person in the main window.
- **PyPI GUI extra** - the package metadata now declares a `gui` optional dependency group for `customtkinter`, `CTkToolTip`, `pillow`, and macOS-only PyObjC Cocoa support.
- **Windows process identity helper** - Windows AppUserModelID setup now lives in `gedcom_platform.py` and is applied during GUI startup instead of being hidden inside configuration path lookup.

### Changed

- **Privacy policy updated for update checks** - the privacy policy now states that GEDCOM data remains local while documenting the optional GitHub request made only when the user chooses to check for updates.
- **Cache privacy wording expanded** - cache-clearing text and privacy documentation now clarify that cached GEDCOM data can include DNA marker details and raw record content, not just names and dates.
- **ZIP loading is more responsive** - ZIP extraction now streams large GEDCOM entries in chunks, enforces the uncompressed-size limit while copying, supports cancellation, deletes partial temp files on failure, and runs inside the existing background load path.
- **Search limits validated consistently** - CLI argument parsing, data-model wrappers, and BFS search functions now reject non-positive `top_n`, `max_depth`, and out-of-range fuzzy thresholds with clear errors.
- **GUI filtering and picker search share matching rules** - the main people list and relationship picker now use the same ID, token, and fuzzy matching behavior as the CLI.
- **Result refreshes use background workers** - refreshing DNA-match and relationship-path results after setting changes or navigation now uses the shared cancelable background-task flow instead of ad hoc worker threads or synchronous path searches.
- **Relationship classification structured internally** - relationship labeling now uses a `RelationshipClassification` data object so classified paths, in-law paths, spouse-anchored paths, and biological-label preferences are easier to handle consistently.
- **Graph save/copy code simplified** - result rendering now delegates SVG and PNG generation to `gedcom_graph_export.py`, reducing duplication inside `ResultsMixin`.
- **Keyboard shortcut help cleaned up** - keyboard shortcuts are now documented in a simpler Markdown table and the obsolete Alt-M menu shortcut has been removed from the shortcut rows.
- **Documentation and install guidance updated** - the README now distinguishes the standard-library CLI from the GUI extra, documents Pillow and PyObjC Cocoa needs, and shows the `gedcom-navigator[gui]` install form.
- **macOS build scripts hardened** - Mac build scripts now warn before destructive clean builds, detect a Tk framework symbol that can trigger App Store rejection, reuse the release version consistently during upload, and can auto-bump App Store build versions after prior submissions.
- **Release metadata updated** - the package version is now `1.3.0` with release date `2026-05-16`.

### Fixed

- **Graph tooltip reuse across result widgets** - relationship-link tooltips now verify that their underlying text widget still exists before being reused, avoiding stale tooltip state after result panes are rebuilt.
- **Graph window modality and shortcuts** - relationship graph windows now grab focus, support Escape to close, and keep copy/save shortcuts scoped to the graph dialog.
- **Navigation during busy work** - clicking a different person while a search or refresh is busy now does nothing instead of starting overlapping result work.
- **Name-order resorting** - changing name display order now clears the cached people-list sort key so the visible list is rebuilt with the new name ordering.
- **ZIP extraction memory pressure** - GEDCOM files inside ZIP archives are no longer read into memory all at once.
- **Update-check privacy mismatch** - documentation no longer claims the app never makes network requests now that manual update checking exists.

### Tests

- **Update-check tests** - tests now cover semantic-version parsing, version comparison, current/newer release results, and network-error handling.
- **Name-search tests** - tests now cover exact ID lookup, ID lookup without `@` delimiters, ID substring matching, order-independent token matching, and fuzzy candidate scoring.
- **CLI validation tests** - tests now cover positive integer parsing, fuzzy-threshold range validation, and CLI delegation to the shared search helpers.
- **Search-limit validation tests** - core search and data-model tests now cover rejection of non-positive search limits.
- **ZIP extraction tests** - tests now cover oversized archive entries and cancellation during ZIP extraction.
- **Relationship-classification tests** - tests now cover structured direct ancestor, descendant, in-law, and unclassifiable-path cases.

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

- **Modular GUI refactor** — the monolithic `gedcom_navigator_gui.py` has been split into focused modules: `gedcom_gui_appearance.py` (theming, fonts, menus, keybindings), `gedcom_gui_dialogs.py` (pop-up windows), `gedcom_markdown.py` (markdown renderer), `gedcom_relationship.py` (BFS ancestor/descendant helpers and plain-English labels), and `gedcom_theme.py` (theme constants, OS dark-mode detection, Tooltip widget).
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
- **Script filenames renamed to snake\_case** — `gedcom-navigator-cli.py`, `gedcom-navigator-gui.py`, `generate-icon.py`, and the two PyInstaller `.spec` files have been renamed to use underscores (`gedcom_navigator_cli.py`, `gedcom_navigator_gui.py`, `generate_icon.py`, `gedcom_navigator_cli.spec`, `gedcom_navigator_gui.spec`) for consistency with Python package conventions.
- **PyPI GUI entry point renamed** — the console-script entry point in `pyproject.toml` was updated from `gedcom-navigator-gui` to `gedcom_navigator_gui` to match the renamed launcher.
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
- **PyPI packaging** — the project is now structured for distribution on PyPI as `gedcom-navigator`. A `pyproject.toml` with full metadata and entry points, a `gedcom_navigator/` Python package with `gedcom-navigator` (CLI) and `gedcom_navigator_gui` (GUI) console scripts, a `hatch_build.py` custom build hook that bundles `src/` scripts and assets into the wheel, and a `dev/build-pypi.ps1` build-and-upload script (supports `-TestPyPI` flag) are all included.

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
### Improved

- **Tab order** — Tab now follows a logical left-to-right, top-to-bottom sequence through the main controls: Find → Filter → people list → results pane → Top N → Max Depth → Set Home → Show Person → Find Nearest DNA Matches. Shift+Tab traverses the same chain in reverse. The vertical scrollbar on the people list is excluded from tab traversal.
- **Focus on list entry** — when focus moves to the people list (via Enter from a search box or Tab), the first row is automatically selected if no row is already focused, so arrow-key navigation works immediately without an extra keypress.

## [0.0.7] - 2026-04-28

### Added

- **Keyboard shortcuts** — Ctrl-key shortcuts are now active throughout the application: Ctrl+F (jump to Search), Ctrl+D (toggle DNA-flagged filter), Ctrl+U (toggle Fuzzy search), Ctrl+O (Browse file), Ctrl+N (Find Nearest DNA Matches), Ctrl+S (Show Person), Ctrl+H (Set Home), Ctrl+P (Find Relationship Path), Ctrl+T (View tag definitions), and Ctrl+C (Copy results). Ctrl+C defers to the text widget's own copy behavior when the results pane has keyboard focus.
- **Button mnemonics** — the shortcut letter is underlined on six buttons: Find (F), Copy (C), Show Person (S), Set Home (H), Find Nearest DNA Matches (N), and View tag definitions… (t).
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
