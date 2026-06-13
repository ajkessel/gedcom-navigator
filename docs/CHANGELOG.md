# Changelog

## [1.11.0]

### Added

- **Profile photos in PNG and SVG graph exports** — relationship-path and family-tree graphs exported via Copy Image or Save as PNG/SVG now include any visible profile photo thumbnails. Previously, canvas image items were silently skipped and left blank rectangles in exported files.
- **Numbered step badges on relationship-path nodes** — each person along the relationship path now carries a numbered badge (1, 2, 3 … N) so you can follow the chain at a glance without tracing connector lines. Badges survive PNG and SVG export.
- **Emphasized path spine** — the main relationship path is now visually distinct from the surrounding family context: off-path relatives and their edges are faded toward the background, while path edges gain a heavier line with a casing under-stroke and consistent source-to-target flow arrows. Path nodes get a strong accent outline.
- **Solid, consistently colored flow arrowheads** — spouse and sibling segments on the path now use a larger solid arrowhead in the accent color instead of a thin open chevron. Arrowheads appear in PNG and SVG exports.

### Fixed

- **Step badges draw above profile images** — the numbered badge was rendered before the profile image and thus painted over; each node's badge is now drawn last so it stays visible on nodes with photos.
- **Expand buttons lift off the path connector line instead of moving sideways** — when a sibling or spouse expand button was positioned on the side facing an adjacent path node, it landed in the short connector gap and hid the direction arrowhead. The button is now raised vertically off the connector line, keeping the arrow visible without displacing the button to an already-occupied side.

**Full Changelog**: https://github.com/ajkessel/gedcom-navigator/compare/v1.10.0...v1.11.0

## [1.10.0]

GEDCOM Navigator now finds DNA matches in family trees exported from any genealogy software, not just Ancestry.

Previously, DNA-match detection relied on Ancestry-specific data structures (_MTTAG custom tags and AncestryDNA Match source citations). Files exported from other programs — MyHeritage, Family Historian, Legacy Family Tree, RootsMagic, and others — were not recognized.

When your GEDCOM file was not exported by Ancestry, the app now scans the custom fields those programs use to record DNA relationships:

* Custom events and facts (EVEN/FACT records with a DNA-related TYPE, e.g. "DNA Match" or "MyHeritage DNA")
* Family Historian custom attributes (_ATTR)
* Reference number fields (REFN)
* Custom _DNA-style tags

The match keyword is configurable (default: "DNA"). When a custom event uses the generic TYPE value "Custom", the app uses the event's own text as the label — so a record like 1 FACT MyHeritage DNA / 2 TYPE Custom appears and matches as "MyHeritage DNA".

Notes (free-text NOTE fields) are excluded by default — they mention "DNA" too often to be useful for detection. You can enable note scanning with the new Scan note text for matches toggle in Preferences.

## New controls

* Select Tag browser — for non-Ancestry files, the tag browser now shows a catalog of the custom field types discovered in your GEDCOM. Columns are sortable by clicking any header, so you can quickly find and select the specific tag to match on.
Preferences: Scan note text for matches — opt in to include free-text NOTE fields in DNA detection.
* CLI: --detection-fields — controls which field categories are scanned (events/facts, custom attributes, reference numbers, etc.).
* CLI: --list-tags — now shows the full catalog of discovered custom field types for non-Ancestry files.

## Bug Fixes
* Full siblings display with a solid connector inside mixed half-sibling groups — when a sibling group with hidden parents included both full and half-siblings, the entire group's connector bar was drawn in the half-sibling dashed style, making full siblings appear to be half-siblings. Full-sibling groups within the bar now use the solid style; only the bridges between different family groups use the dashed style.
* Half-siblings with hidden parents are placed on their sibling's row — a half-sibling whose own parents are not visible was being placed as a disconnected component far from their sibling group. They are now correctly attached on the same row as their siblings.

**Full Changelog**: https://github.com/ajkessel/gedcom-navigator/compare/v1.9.18...v1.9.19

## [1.9.15]

### Changed

- **Family-tree layout rebuilt around explicit family units** — the family graph view's layout engine was rewritten from ~25 interacting repair passes to a single recursive block layout over GEDCOM-style family units (parents + their children). Spouses are always adjacent (chained for multiple marriages), each family's children group under their actual parents, sibling and ancestor blocks pack without overlap by construction, and the layout is ~400× faster on large graphs. Children now connect to a bus per family unit anchored at their own parent(s): a child of one remarried parent hangs from that parent alone rather than appearing as a child of the visible couple, so step-siblings are visually distinct and it is clear which child belongs to which parent. Overlapping buses on the same row are vertically staggered, and half-sibling groups whose shared parent is hidden merge into a single half-style ghost stub. Step-parents recorded in a child's GEDCOM family are excluded from the child's family unit, so a child of divorced biological parents connects to both of them with a biological-style bus (each non-adjacent parent gets its own drop line) instead of appearing as a step-child of a parent's later spouse.
- **Sibling connectors replaced by ghost-stub bars in family-tree graphs** — when parents are not visible, siblings were connected by horizontal lines indistinguishable from spouse double-rail lines. Siblings are now grouped by a short horizontal bar drawn above the node row with vertical drop lines to each sibling — the same visual language as the parents-visible bus, just without boxes. The stub lives in a distinct vertical zone so it cannot be confused with a spouse connection. Half-sibling groups use the split dashed-rail style; step-sibling groups use the dotted style.

### Fixed

- **Full siblings keep a solid connector inside mixed half-sibling groups** — when a sibling group with hidden parents included half-siblings, the whole group's ghost stub was drawn in the half-sibling dashed style, making full siblings look like half-siblings. Each hidden family's children now share a solid bar, and only the bridges between the family bars use the dashed half-sibling style.
- **Half-siblings with no visible parents are placed on their sibling's row in family-tree graphs** — a half-sibling whose own parents are all hidden belongs to a family unit no visible person shares, so the rewritten layout treated them as a disconnected component and dropped them to the centre row at the far right. The layout now attaches such units through the shared (hidden) parent, placing the half-siblings on the same row as their siblings.
- **Each spouse's ancestors stay on that spouse's side in family-tree graphs** — when both members of a couple had visible parents, one set of parents could be placed on the wrong side (e.g. the wife's parents left of the husband's), making the parent drop lines cross. Ancestor blocks are now placed strictly left-to-right following the couple's order, so connector lines to parents never cross.
- **Family-tree connector bus line no longer overlaps parent nodes at high display scaling** — at high DPI (e.g. Windows 300 % scaling), enlarged fonts make node heights grow, causing the horizontal bus line that connects parents to children to be placed inside the parent node boxes rather than below them. The bus-line midpoint now anchors to the actual parent node bottom rather than the couple's centre, keeping 44 design-unit clearance between the parent boxes and the bus regardless of DPI.
- **Find, filter, profile pane, and profile photo clear when loading a new file** — opening a different GEDCOM file now resets the Find and Filter fields, clears the results/profile pane text, and destroys any floating profile thumbnail so no stale content from the previous file is left visible.
- **Profile photo updates when switching persons in Pedigree and Descendants views** — selecting a new person while in Pedigree or Descendants sub-mode now replaces the profile thumbnail with the new person's photo rather than leaving the previous person's photo in place. Both text-report renderers now call `_place_profile_thumbnail` the same way the Bio renderer does.
- **Full-size image window no longer opens automatically on profile navigation** — a Windows Tkinter quirk caused the photo thumbnail's click handler to be invoked with no event argument during navigation, which (after a prior defensive fix) inadvertently opened the full-size image viewer. The handler now only opens the image when called with a real click event.
- **Profile photos remain above text on macOS** — the profile thumbnail is now layered over the outer textbox instead of inside Aqua's native text widget, preventing Matches-view text redraws from painting over the image. The thumbnail is repositioned and raised whenever either textbox layer is resized.

## [1.9.14] - 2026-06-05

### Added

- **PDF export for text views** — Results and Profile views can now be saved as searchable, paginated PDF reports. Each page includes a centered report type and person/lifespan heading plus a GEDCOM-Navigator page-number footer. PDF output preserves headings, bold text, link styling, Unicode text, and visible relationship connectors; logical lines move to the next page instead of being split when space is insufficient.
- **Optional photos in PDF reports** — the new Export Preferences section includes a default-off "Include photos" option. When enabled, a person's real local profile photo appears on the first PDF page only; missing images and generic placeholders are omitted.
- **Text-based Pedigree and Descendants views** — the Profile pane gains a Bio / Pedigree / Descendants sub-mode selector. Pedigree renders an Ahnentafel ancestor report (numbered by generation, e.g. "2. Robert Brown (father)", "4. William Brown (paternal grandfather)", "8. James Brown (paternal great-grandfather)") and Descendants renders a Henry-numbered descendant report (1, 1.1, 1.1.1 …) with each person's spouse listed below them. Both views are plain text, so copy-to-clipboard and save-as-PDF/TXT work for free. Person names are clickable links that navigate to that person's Bio. Keyboard shortcuts: **Ctrl+B** (Profile/Bio), **Ctrl+Shift+P** / **⌘⇧P** (Pedigree), **Ctrl+Shift+D** / **⌘⇧D** (Descendants).
- **Ordinal "great-" notation in Pedigree** — great-grandparents and beyond use compact ordinal labels ("2nd great-grandfather", "3rd great-grandfather") instead of repeating "great-". All gen-4+ ancestors also carry a paternal/maternal prefix so each entry states which side of the family it belongs to.
- **Walkthrough covers Pedigree and Descendants** — the guided tour includes a new step that highlights the Bio/Pedigree/Descendants selector and explains Ahnentafel numbering (including how to decode any slot number back to the subject) and Henry numbering.
- **In-app help updated** — HELP.md includes a new "Profile View" section describing the three sub-modes with a full Ahnentafel decoding table and worked example.

### Fixed

- **Pedigree unknown ancestors skipped rather than shown as placeholders** — in list-format Ahnentafel reports, unknown ancestors are conventionally omitted entirely; the slot numbers of known ancestors remain correct because the BFS walk still assigns all slots internally.
- **Ctrl+Shift+P and Ctrl+Shift+D shortcuts now work on Windows and Linux** — the Tkinter binding sequences used a lowercase keysym (`<Control-Shift-p>`) which Tkinter never fires because Shift converts the keysym to uppercase; corrected to `<Control-Shift-P>` and `<Control-Shift-D>`.
- **Common ancestor correctly identifies direct ancestors** — when one person is a direct ancestor of the other (parent, grandparent, etc.), the "Common ancestor" field now names that person rather than climbing another generation to their own parents.
- **Common ancestor shows "Same person" for self-paths** — when the source and target of a path are the same person, the "Common ancestor" field now reads "Same person" instead of being absent.

### Changed

- **More readable Profile Facts & Events** — Residence, Education/Graduation, and Occupation are grouped into date-first timelines, with remaining GEDCOM facts collected under Other Facts & Events. Entries are ordered chronologically, undated records are clearly labeled, long notes and source details use indented continuation lines, and `https://` links remain clickable.
- **Cleaner source links in Facts & Events** — source citations ending in a labeled `URL: https://...` now hide the raw URL and make the readable `Source:` description the hyperlink instead. Link styling excludes indentation and recognizes exporter-added whitespace within URL query parameters.
- **Cleaner Preferences layout** — Preferences now uses a wider, aligned label-and-control grid so appearance, search, display, export, language, cache, and data-management options are easier to scan and less likely to clip. PDF/Text selection moved into its own Export section, PDF is now the default save format, and PDF appears before Text in the selector.
- **Full-size images can be dragged to pan** — zoomed profile and gallery images can now be repositioned by dragging with either mouse button.

## [1.9.13] - 2026-06-02

### Added

- **Remove all data** — new option to remove all locally stored data, including settings and cached images

### Changed

- **Streamlined results pane heading** — removed the redundant "Closest Tagged Matches" header (and the rule beneath it) from the search results so the closest-match list begins directly under the starting person's details.

### Fixed

- **Family-tree column placement no longer fails on edge cases** — `_nearest_unblocked_column` could raise on a `min()` over an empty sequence when accumulated floating-point error in the column math tipped every candidate's boundary distance a hair under `MIN_COLUMN_SPACING`. The layout now falls back to placing the box clear of the whole cluster instead.
- **Profile thumbnail stays in front** — the top-right profile photo thumbnail in the Profile View is now kept lifted above the text contents (on placement, on textbox `<Configure>`, and after redraws) so it no longer slips behind the profile text.
- **Gallery and image-preview windows reliably come to the front on Windows** — the Image Gallery and the full-size image preview used a bare `lift()` (gallery) or `lift()` + `focus_force()` (preview) to raise themselves, neither of which reliably foregrounds a window on Windows, where the OS blocks background windows from stealing focus. Both now use the shared `_raise_window` helper (already used by the path-graph and Profile View windows), which briefly toggles `-topmost` and retries after the window has rendered, so they consistently appear in front with keyboard focus.
- **Large full-size images no longer run off the bottom of the screen** — opening a tall image from the gallery centered the preview on its parent without accounting for the window manager's title bar and borders, so a near-full-height window's bottom (and its button row) could extend past the bottom of the screen. The preview is now clamped to the screen and, once realized, nudged up by any remaining decorated-bottom overflow so the whole window — including the Copy/Save controls — stays visible.

### Packaging

- **Improved Uninstall** — uninstalling from Windows offers to delete application data.
- **Sample tree now ships with images** — the bundled `samples/fictional_genealogy.ged` includes person images, and `samples/media` is now packaged into the executable so the sample profile photos and galleries render in distributed builds.
- **Sample tree now includes life events** — the synthetic sample generator adds a handful of timeline facts (education, occupation, residence, and a mid-life career change or relocation) to each person at life-stage-appropriate ages, so the Profile View's Facts & Events section is illustrated out of the box. Events are skipped for anyone too young or no longer living for them, and existing relationships are unchanged.

## [1.9.12] - 2026-06-01

### Added

- **Optional profile photo thumbnails** — Preferences now includes "Show Profile Image" for rendering local GEDCOM media as profile thumbnails in the Display Pane, Profile View window, path graphs, and family-tree graph nodes. The parser recognizes standard `OBJE` records, inline person-level `OBJE`, FTM `_PHOTO`, and primary-media markers, resolves only local filesystem paths, and uses generated sex-based fallback images when no usable local photo is available. Thumbnails preserve the full image instead of cropping faces, graph nodes use photo-forward card layouts when images are enabled, and clicking a real thumbnail opens a reusable full-image preview with Copy and Save buttons while clicking the rest of the graph node keeps opening the context menu.
- **Image Gallery** — The Profile View window also offers an image gallery for additional person-level images beyond the selected profile photo, available from the Gallery button or `Ctrl+G` / `⌘G`, with Escape to close the gallery and arrow buttons, an "x of y" position indicator, Left/Right and Home/End keyboard shortcuts for moving through full-size gallery images in the same preview window size, and the standard zoom shortcuts and zoom mouse actions in the full-size image window. The full-size preview widens small-image windows as needed so the button row remains visible. When a GEDCOM image path cannot be found locally, the app can prompt once per session for a replacement media folder, remember that folder for the current GEDCOM file, start the folder picker in the most likely media directory, and use the selected folder to resolve other exported media paths from a different filesystem.

## [1.9.11] - 2026-06-01

### Added

- **Profile view Facts & Events section** — Profile now renders additional individual GEDCOM facts and events from the raw record, including common entries such as occupation, residence, census, education, immigration, military, religion, probate, wills, generic `EVEN`/`FACT` records, notes, source page details, and clickable `https://` links. Profile sections now appear in this order: Biography, Family, Path to Home Person, Facts & Events, Tags, then the optional Full GEDCOM Record.
- **Unset the Home Person from the action bar** — when the current Home Person is selected in the people list, the "Set Home" button now changes to "Unset Home". Clicking it clears the Home Person (removing the path-to-home section and the saved `home_persons` entry for the file). The button label tracks the selection automatically, including after loading a file or unloading data, and the `Set Home` keyboard shortcut now toggles the same way. `ConfigManager.set_home_person` accepts `None` to clear the stored value.

### Fixed

- **Intermittent tooltip crash on Windows multi-monitor / DPI changes** — hovering a tooltip could occasionally raise `AttributeError: '_SizedToolTip' object has no attribute 'block_update_dimensions_event'`. The tooltip subclasses a plain Tk `Toplevel` but contains CustomTkinter widgets, which register the tooltip window with CustomTkinter's `ScalingTracker`; when its DPI-check loop detects a monitor scaling change (Windows only) it calls `block_update_dimensions_event()`/`unblock_update_dimensions_event()`, methods that exist only on `CTk`/`CTkToplevel`. `_SizedToolTip` now provides these methods as no-ops matching CustomTkinter's own implementation, so the tracker rescales the tooltip's inner widgets without crashing.
- **Family tree rendering for step, half, and multi-spouse families** — Tree View now draws visible sibling links as adjacent segments so full- and half-sibling styles do not overlap into misleading long lines. Parent-child connectors are grouped by the actual visible parent couple instead of any visible spouse, preventing step-parents from appearing as biological parents. Multi-spouse parent rows keep each spouse-family group visually distinct, child groups are re-centered under their parents after compaction, and leaf sibling outliers are pulled back next to their sibling group to avoid large empty spans.

## [1.9.10] - 2026-05-31

### Added

- **Biological, step, foster, and half-family display** — the parser now preserves GEDCOM parentage metadata (`PEDI`, adoption records, and common `_FREL`/`_MREL` tags) so Profile and graph views can distinguish biological, step, half, adopted, and foster relationships. Profiles label non-ordinary relatives while leaving ordinary relatives unqualified, and graph views use alternate line styles plus a compact legend for non-ordinary links, including the biological/default style for comparison.
- **Welcome window and interactive walkthrough** — a first-run Welcome window now greets new users with the in-app help guide, a "show next time" checkbox, and a **Walkthrough** button (also available any time from the Help menu). The walkthrough (`gedcom_walkthrough.py`) highlights each area of the main window in sequence with Back / Next / Skip navigation, using an amber "outline ring" drawn from borderless Toplevel strips so it never covers the highlighted control and needs no compositor transparency. It temporarily loads the bundled sample tree (`samples/fictional_genealogy.ged`) — unless a file is already open — to demonstrate the clickable names, relationship links, and graph node menu, then unloads it when the walkthrough ends. New `ConfigManager` settings persist whether the welcome window has been seen for the current version (`get/set_welcome_seen_version`) and whether to show it on every launch (`get/set_show_welcome_on_startup`).
- **BCE/CE and Julian/Gregorian dual dates** — the date parser now understands historical date styles. BCE years (`44 BC`, `44 BCE`, `44 B.C.E.`, case-insensitive, 1–4 digits) are parsed as negative years and rendered as e.g. `44 BC` in lifespans and people-list columns via a new `format_year()` helper. Julian/Gregorian dual years such as `10 JAN 1708/9` resolve to the New Style (later) calendar year. A new `extract_year()` returns a signed year (or `None`) and is used consistently across the people list, results pane, profile, and search dialogs.

### Changed
- **Jumping now highlights the selected person** — when you "Jump" in a graph view, the target person is centered in the display. To make it easier to find the person you selected, that person is also now highlighted.
- **Graph copy now reports failures instead of silently doing nothing** — `_copy_graph_canvas` now catches export/clipboard errors, logs the real exception, and shows a "Copy error" dialog (`ERR_COPY_GRAPH_TITLE` / `ERR_COPY_GRAPH_MSG`) with the actual cause, matching the existing graph-save error handling.

### Fixed

- **Copying and saving relationship graphs as images on macOS App Store builds** — copying a family tree, pedigree, or relationship-path graph to the clipboard (and saving it as PNG) silently did nothing in the sandboxed Mac App Store build. The bundled Pillow imaging extension failed to load because one of its support libraries (`libxcb`) referenced `libXau` by an absolute Homebrew path (`/usr/local/opt/...`) that the App Sandbox blocks from loading, even though a copy was bundled inside the app. The build now rewrites every bundled library's absolute Homebrew load path to a bundle-relative `@rpath` reference (`dev/fix-dylib-paths.sh`, run from `dev/build-mac.sh`), so the in-bundle copies load correctly under the sandbox. This was the underlying cause; the `copy_text_to_clipboard` NSPasteboard workaround added in 1.9.9 (which addressed a misdiagnosis) has been reverted, and plain-text copy again uses Tk's clipboard directly.
- **Tiny fonts on high-scaling Windows displays** — on Windows configured for a high display scale (e.g. 200–300%), the entire UI rendered at a fraction of its intended size. The DPI-detection patch now derives CustomTkinter's scaling from `GetDpiForWindow()` instead of `winfo_fpixels()`. `GetDpiForWindow` honours the process's DPI-awareness context — returning the true per-monitor DPI on a DPI-aware process (so widgets and fonts scale up to match) and 96 on a virtualised/unaware one (so the OS handles the stretch) — which fixes both the new "everything tiny at 300%" case and the original "everything huge at 175%" double-scaling case with a single rule. The scale clamp was also raised so 350%/400% displays are no longer under-scaled. (See `_patch_ctk_scaling_for_tkinter_dpi` in `gedcom_navigator_gui.py`.)
- **Mismatched control sizes at high scaling** — at high DPI the CustomTkinter widgets scaled but the classic Tk/ttk widgets did not, leaving the people list (`Treeview`), the Results/Max Depth spinboxes, and the menus rendered far too small next to everything else. The named Tk fonts and the tree row height / column widths are now pre-multiplied by the active widget scaling on Windows (`_ttk_dpi_scaling()` in `AppearanceMixin`), and a one-shot recheck re-syncs them if the per-window scaling settles late at startup or the window moves to a monitor at a different scale.
- **Bold person names and headers rendered tiny in the Profile and Matches views (and the person window)** — bold runs in the results pane (the `#1:`/`#2:` match rank-names, the `Biography`/`Family`/`Parents` section headers) are styled with a Text tag set directly on the underlying widget, which bypasses CustomTkinter's font scaling. On a high-DPI display they stayed at their unscaled size while the surrounding text scaled up, so they looked shrunken — most visibly in the Matches list. All such tag fonts now go through a shared `scaled_tag_font()` helper that multiplies the size by the widget scaling, so bold text tracks the body text at any scale. (No effect off high-DPI Windows, where the scaling factor is 1.0.)
- **Main window opening partly off-screen at high scaling** — the window-fitting logic mixed CustomTkinter "design" units with raw pixel measurements, so on a scaled display the main window could open larger than the screen with its edges (and bottom controls) clipped, sometimes behind the taskbar. `_fit_window_to_content` now does all sizing in design units, positions in physical pixels, and clamps to the desktop **work area** (`SystemParametersInfo(SPI_GETWORKAREA)`, taskbar excluded) so the window always opens fully on-screen; it can also shrink below its preferred minimum when a high-DPI panel offers little logical space.
- **Preferences radio buttons too small and clipped at high scaling** — the Preferences font-size and theme radio buttons used a classic ttk control whose indicator is a fixed size that cannot scale, and the dialog was too narrow to show every option. They are now `CTkRadioButton`s (which scale their indicator and label with the rest of the UI), and the Preferences window measures its content and widens to fit all radios in a row. macOS keeps its native radio buttons.

### Development

- **Sandbox self-test gate in the App Store build** — a new `--self-test` mode (`src/gedcom_selftest.py`) runs headless runtime checks (import Pillow's native extension, render a canvas to PNG, load the macOS pasteboard bridge) and exits non-zero on failure. `dev/build-mac-appstore.sh` runs it against the freshly signed, sandboxed bundle and aborts the build/upload if it fails, so sandbox-only breakage (such as a library still referencing an absolute Homebrew path) can no longer reach Apple's review queue unnoticed.
- **Build/release script fixes** — `dev/build-and-release.sh` now passes the selected git branch through to `dev/build.sh -b` correctly and resolves the current release tag more reliably.

### Tests

- **Historical date parsing tests** — `tests/test_core.py` gains coverage for BCE years (1–4 digits, with and without periods, `BCE` spelling, case-insensitive), Julian/Gregorian dual-year resolution, BCE/CE-spanning lifespans, and end-to-end birth/death year extraction from GEDCOM date fields.
- **Welcome/walkthrough tests** — `tests/test_gui_smoke.py` and `tests/test_config.py` cover the welcome window, the walkthrough launch path, and the new welcome-related configuration accessors.
- **High-DPI scaling tests** — a new `tests/test_font_scaling.py` covers the `scaled_tag_font` helper (size scaling, weight handling, minimum size, error fallback); `tests/test_dpi_patch.py` was updated for the raised scale clamp and adds a 300%/288-DPI case; and `tests/test_gui_smoke.py` gains a GUI test that forces a non-1.0 widget scale and asserts the results pane's bold tag tracks it, guarding against an unscaled tag font being reintroduced.

## [1.9.9] - 2026-05-30

### Fixed

- **Copy to clipboard on macOS App Store builds** — copying a name, the results text, or graph debug JSON silently did nothing in the sandboxed Mac App Store build. Tk's clipboard relies on a lazy pasteboard-owner mechanism that does not reliably reach `NSPasteboard` when sandboxed. A new `copy_text_to_clipboard()` helper in `gedcom_platform.py` now writes straight to `NSPasteboard` via PyObjC on macOS (falling back to Tk's clipboard if PyObjC is unavailable or fails), and every copy path in the results pane and person window uses it.
- **Save permissions on macOS App Store builds** — the App Store entitlement for user-selected files was widened from read-only to read-write, so Save dialogs can now write the chosen file in the sandboxed build.
- **Middle initial display** — a middle initial is now shown in tree node labels only when the middle name actually begins with a letter, so stray punctuation is no longer rendered as an initial.

### Development

- **App Store screenshot automation hooks** — the person/tree detail window now exposes `_expand_open_descendant_tree`, `_set_open_tree_zoom`, and `_frame_open_descendant_top` hooks so `dev/generate-appstore-assets.py` can fully expand, zoom, and frame an open descendant tree synchronously while capturing screenshots. The hooks are inert during normal use and are cleared when the window switches to a profile view or closes.
- **README and build cleanup** — minor README link and wording fixes (including the App Store badge link), and macOS App Store build-script adjustments.

## [1.9.7] - 2026-05-29

### Added

- **Open `.ged` files directly** — GEDCOM Navigator can now register as the default handler for `.ged` files on Windows, macOS, and Linux. Double-clicking a `.ged` file opens it in the app. A new `gedcom_file_association.py` module handles cross-platform registration (Windows ProgID, Linux `xdg-mime` / desktop entry, macOS Launch Services via the bundle's document types). On first launch the app offers to set itself as the default handler (`FILE_ASSOC_PROMPT_*` strings), remembering the version it last prompted for (`get/set_file_association_prompted_version` in `ConfigManager`) so it only asks again after an upgrade. Sandboxed builds (Mac App Store, Windows MSIX) declare the association via their manifest instead of writing it at runtime.
- **Age in the profile biography** — the biographical section of a person's profile now shows their age. For deceased people it shows the age at death (`BIO_AGE` / `BIO_AGE_AT_DEATH`). If the person would be older than 120 but has no death date, the application assumes they have passed awya.
- **New application icon** — the app ships with a redesigned icon across all platforms. Icon assets were renamed from `family_tree.*` to `gedcom_navigator.*` and the previous artwork is retained under `icons/old/`.

### Changed

- **MacOS cosmetic tweaks** — minor appearance refinements, and the Show Person window now grows if needed when recentering on a profile.
- **Synthetic GEDCOM generator overhauled** — `dev/generate_sample_gedcom.py` was substantially reworked to produce richer, more varied sample family structures. The App Store asset and GUI-test helper scripts moved from `scripts/` into `dev/`.

## [1.9.6] - 2026-05-28

### Added

- **Highlight button in graph view** — a new "Highlight" button allows you to add highlighting to as many people in your garphical tree as you want. This highlighting persists when you copy or save your tree, to make it easier to share specific information with others. 
- **Jump button in graph view** — a new "Jump" button (keyboard shortcut `Ctrl+J` / `⌘J`) appears between the Search and Save buttons in the tree, pedigree, and descendant graph view windows. It opens a person picker pre-filtered to only the individuals visible in the current graph, then pans the canvas to center the selected person without re-centering or re-rendering the graph. The picker includes the same Find/Filter/Fuzzy/Married/Tagged controls as the main Search picker.
- **Pedigree view** — the Show Person window now includes a Pedigree view that displays the full recorded ancestor tree for a person, laid out left-to-right by generation. All ancestor branches visible in the GEDCOM data are shown simultaneously, with right-angle connectors linking each person to their parents. The layout centers each person between their recorded parents and compacts the vertical spacing.
- **Descendant view** — a new Descendant view in the Show Person window shows all recorded descendants in an expandable top-down tree. Each expanded person shows their spouses and children; branches can be collapsed and expanded interactively.
- **View mode selector in Show Person window** — a segmented button (or radio group on smaller windows) lets you cycle between Tree View, Pedigree View, Descendant View, and Profile View. The preferred mode is persisted to settings and restored on next launch (`get_default_tree` / `set_default_tree` in `ConfigManager`). `Ctrl+T` cycles through all four modes.
- **Winget build script** — `dev/build-winget.ps1` automates generation of Windows Package Manager (Winget) manifests from templates in `dev/winget/`. It reads the current version from `gedcom_navigator/__init__.py`, computes the installer SHA-256, fills `{VERSION}`, `{VERSIONX}`, and `{INSTALLERSHA256}` placeholders, writes YAML manifests to `dist/`, and optionally commits and pushes them to a local clone of the `winget-pkgs` repository.
- **Tab-shaped expand/collapse buttons** — expansion buttons in the family tree canvas now render as rounded-edge tabs that visually attach to the node they control, with only the exposed outer corners rounded. Separate tab shapes are drawn for parent, child, sibling, and spouse categories.
- **Progress pulsing during large tree renders** — the family tree renderer now accepts a `progress_callback` argument and calls it periodically while drawing large trees, keeping the search popup progress bar alive during slow renders.

### Fixed

- **Copy name now includes GEDCOM ID** — if you have "show GEDCOM IDs" enabled, clicking on the name at the top of the profile and selecting "copy" will also include the GEDCOM ID.
- **Family tree window crash on Linux when tree is large** — `win.state("zoomed")` is a Windows-only Tk call; on Linux it raises `TclError: bad argument "zoomed"`. The tree-view window-sizing code now uses `win.attributes("-zoomed", True)` on non-Windows platforms (with a `geometry()` fallback for macOS, where `-zoomed` is also unsupported). Two sites were affected: the initial window placement in `_show_person_for` (which crashed), and `_maybe_grow_tree_win` (which silently failed to maximize after a user expansion).
- **Winget manifest generation extracted from main build script** — the Winget manifest generation code has been removed from `dev/build.ps1` and now lives exclusively in `dev/build-winget.ps1`, keeping the Windows build script focused on compilation and packaging.

### Changed

- **`draw_family_tree` is now a general-purpose graph renderer** — `FamilyTreeRenderMixin._draw_family_tree` accepts `graph_builder`, `layout_builder`, `expandable_categories`, `expansion_options_lookup`, `expanded_for_buttons`, `orientation`, `expand_all_categories_lookup`, and `progress_callback` parameters. This allows the pedigree and descendant views to share the same canvas-drawing infrastructure with the standard family tree.
- **Horizontal layout support for pedigree view** — the renderer detects `orientation='horizontal'` and adjusts node widths, fonts (with extra shrink at low zoom), and connector geometry to suit a left-to-right generational layout.
- **Keyboard shortcut documentation updated** — the Profile / Graph View Window shortcut table now reflects that `Ctrl+T` cycles through all four view modes (Tree, Pedigree, Descendant, Profile) and that `Ctrl+S`/`Ctrl+C` save or copy the current graph rather than only the profile or tree.
- **Development documentation expanded** — `docs/DEVELOPMENT.md` now lists all source modules with descriptions, adds `gedcom_gui_appearance.py` and `gedcom_gui_graph_render.py` to the GUI module table, corrects the dev-requirements filename (`requirements-dev.txt`), and documents the `gedcom_navigator/` PyPI shim package.

### Tests

- **Regression test for tree-view zoomed crash** — `tests/test_gui_smoke.py` gains `test_tree_view_opens_when_zoomed_attribute_raises`, which monkeypatches `wm_attributes` to raise `TclError` on `-zoomed` (simulating macOS/Linux Aqua Tk) and forces `_twants_max = True` via a tiny fake screen size, then asserts the tree-view window opens without error.
- **Pedigree graph builder tests** — `tests/test_gui_results.py` gains `test_pedigree_tree_graph_includes_all_recorded_parent_families`, `test_pedigree_tree_layout_centers_people_between_their_parents`, and `test_pedigree_tree_layout_keeps_deep_parent_pairs_adjacent` verifying the new pedigree graph builder and layout algorithm.
- **Pedigree renderer geometry tests** — `test_pedigree_font_extra_shrink_only_applies_below_normal_zoom`, `test_pedigree_parent_connectors_are_orthogonal`, and `test_pedigree_single_parent_connector_exits_horizontally` cover the horizontal-layout connector and font-shrink helpers.
- **Expansion button shape tests** — `test_expansion_button_tab_rounds_only_outer_edge` asserts the tab polygon rounding applies only to exposed corners.
- **Family tree layout tests** — `test_family_tree_spouse_pair_keeps_each_partner_family_siblings_grouped` and `test_family_tree_compacts_sibling_branch_with_children_as_block` extend sibling-layout coverage in `tests/test_gui_results.py`.
- **Person dialog view mode tests** — `tests/test_gui_person_dialog.py` gains `test_tree_initial_view_uses_configured_default_tree`, `test_button_bar_needed_width_includes_window_padding`, and `test_tree_search_recenters_only_when_person_selected`; `test_tree_context_profile_closes_window_and_shows_display_profile` is updated to `test_tree_context_profile_stays_in_person_window` reflecting the new in-window profile navigation behavior.
- **Config tests for default tree mode** — `tests/test_config.py` gains a `TestDefaultTree` class covering `get_default_tree` / `set_default_tree` for the `tree`, `pedigree`, and `descendant` values and the invalid-value fallback.
- **Dialog owner tests** — `tests/test_gui_dialogs.py` gains `test_valid_dialog_owner_prefers_live_owner_window` covering the `_valid_popup_owner` helper.

## [1.9.5] - 2026-05-26

### Added

- **App Store screenshot and preview generator** — `scripts/generate-appstore-assets.py` automates production of all Mac App Store screenshots (`screenshot_01_main.png` through `screenshot_05_tree.png`), an animated GIF (`screen_recording.gif`), and an H.264 App Preview video (`app_preview.mp4`). Captures are driven by AppKit's `NSThemeFrame` so no Screen Recording permission is required. A lightweight HTTP capture-coordination helper (`scripts/_capture_server.py`) synchronises the screenshot timing with live GUI state.
- **App Store screenshot assets** — generated screenshots and preview video are committed under `docs/screenshots/appstore/`.

### Fixed

- **Conflicting MacOS keyboard shortcuts** — `Cmd-H` (hide application) and `Cmd-M` (minimize window) are intercepted by macOS at the window-server level before Tkinter sees them. The Set Home and Toggle Married Names actions now use `Cmd-Shift-H` / `Cmd-Shift-M` on macOS. A new `_mod_shift_shortcut` helper in `gedcom_shortcuts.py` encodes this platform difference, and tooltip text for both actions is updated to display the correct platform-specific key sequence via `shortcut_by_action()`.
- **MacOS crash on save** — all `filedialog.asksaveasfilename` and `filedialog.askdirectory` calls now pass their `parent=` argument through a new `filedialog_parent()` helper in `gedcom_platform.py`. On macOS the helper returns `None`, preventing the dialog from being shown as an AppKit sheet (which triggers an assertion abort in PyInstaller builds). Affected save paths: save results, save graph PNG/SVG, save graph debug JSON, and save profile text.
- **Left-click on results header** — the results-pane header label now responds to left-click (`<Button-1>`) in addition to right-click, making the header context menu easier to discover.

### Tests

- **OS-reserved shortcut conflict tests** — `tests/test_gui_keybindings.py` gains four new tests: `test_no_macos_system_shortcut_conflicts` and `test_no_windows_system_shortcut_conflicts` verify no registered shortcut collides with OS-level sequences; `test_macos_cmd_h_and_cmd_m_use_shift` asserts the corrected Shift sequences on macOS; `test_windows_linux_use_standard_ctrl_for_h_and_m` verifies the non-macOS bindings are unchanged.
- **`filedialog_parent` enforcement test** — `tests/test_filedialog_parent.py` uses AST analysis to assert that every `filedialog.*` call in `src/` that passes `parent=` wraps the value in `filedialog_parent()`, preventing regressions of the macOS save-dialog crash.

## [1.9.4] - 2026-05-25

### Added

- **Fictional genealogy sample file** — `samples/fictional_genealogy.ged` contains 1,000 fictional people illustrating complicated family structures (multiple marriages, half-siblings, cousins, etc.). Released under the Unlicense. A generator script (`dev/generate_sample_gedcom.py`) and a `samples/README.md` are also included. The README now links to this file as a first option for users who want to try the app without uploading their own data.
- **Asynchronous home-path computation in profile view** — the relationship path to the home person is now computed in a background thread when rendering a person profile. A "Calculating path…" placeholder is shown immediately while the BFS runs, so navigating between people no longer blocks the UI. Results are posted back via `root.after()` and replace the placeholder once ready. Stale results (from a cancelled lookup) are discarded.
- **Home-path result cache** — computed home paths are cached by `(start_id, home_id, max_depth)` key and reused on repeat visits. The cache is invalidated automatically when a new GEDCOM file is loaded or the home person is changed.

### Fixed

- **Ghost expansion buttons in family tree** — collapse/expand toggle buttons no longer appear for categories that have no visible relatives. `_show_expansion_button` now receives the resolved `members` dict and returns `False` when the expanded category contains no real targets, eliminating phantom buttons on nodes with empty spouse, sibling, parent, or child groups.

### Tests

- **Home-path caching tests** — `test_home_path_data_uses_cache_for_revisited_person` verifies that a second call for the same person returns the cached result without re-running BFS.
- **Background home-path lookup tests** — `test_profile_home_path_render_starts_background_lookup` confirms the render method returns a loading placeholder and triggers the background worker; `test_stale_profile_home_path_result_is_ignored` confirms outdated results from cancelled lookups are discarded.
- **Loading message rendering test** — `test_home_path_section_renders_loading_message` in `test_gui_results.py` verifies the "Calculating path…" string is emitted when home-path data carries `loading: True`.
- **Expansion button visibility tests** — new `tests/test_gui_expansion_buttons.py` covers the two key cases: an expanded category with no members hides its button; an expanded category with at least one visible member keeps it.

## [1.9.3] - 2026-05-23
- Updated translations
- Fixed language selection preferences

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
