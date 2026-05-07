#!/usr/bin/env python3
"""
gedcom_dna_finder_gui.py

customtkinter GUI for finding the nearest DNA-flagged relative(s) to a target
person in a GEDCOM tree.

Workflow:
  1. Browse to your GEDCOM and click Load.
  2. Type in the search box to filter the people list.
  3. Select a person and click "Find Nearest DNA Matches"
     (or just double-click the row).
  4. The right pane shows the path from that person to the nearest
     DNA-flagged relative(s).

Two DNA-flag signals are detected (either is sufficient):
  - A source-citation PAGE line whose text contains "AncestryDNA Match"
  - An _MTTAG pointer to a tag-record whose NAME contains "DNA"
    (configurable from the UI)

Pure stdlib + customtkinter. Requires Python 3.8+.
"""

import tkinter.font as tkfont
import argparse
import difflib
import os
import re
import subprocess
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

from gedcom_data_model import GedcomDataModel
from gedcom_config import ConfigManager
# user-facing strings noqa: F401,F403 # pylint: disable=unused-wildcard-import,wildcard-import
from gedcom_strings import *
from gedcom_core import (
    bfs_find_dna_matches,
    bfs_find_all_paths,
    describe,
    extract_ged_from_zip,
)
from gedcom_relationship import (
    get_ancestor_depths,
    get_descendant_depths,
    describe_relationship,
)
from gedcom_theme import Tooltip, THEME_NAMES, get_flag_bg, get_link_color
from gedcom_gui_appearance import AppearanceMixin
from gedcom_gui_dialogs import DialogsMixin


def _open_url(url):
    # webbrowser.open() silently fails in PyInstaller .app bundles on macOS
    if sys.platform == 'darwin':
        subprocess.run(['/usr/bin/open', url], check=False)
    else:
        webbrowser.open(url)


def _read_version():
    _bases = []
    if getattr(sys, 'frozen', False):
        _bases.append(sys._MEIPASS)
    _bases.append(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), '..'))
    for _base in _bases:
        _path = os.path.join(_base, 'gedcom_dna_finder', '__init__.py')
        if os.path.isfile(_path):
            with open(_path, encoding='utf-8') as f:
                _src = f.read()
            _v = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', _src)
            _d = re.search(r'__release_date__\s*=\s*["\']([^"\']+)["\']', _src)
            if _v and _d:
                return _v.group(1), _d.group(1)
    return 'unknown', 'unknown'


__version__, __release_date__ = _read_version()


# ===========================================================================
# GUI
# ===========================================================================

class DNAMatchFinderApp(DialogsMixin, AppearanceMixin):
    """customtkinter application for browsing GEDCOM people and finding DNA matches."""

    MAX_LIST_DISPLAY = 2000
    FUZZY_THRESHOLD = 0.72
    MAX_RECENT = 10
    MAIN_PREFERRED_WIDTH = 1500
    MAIN_PREFERRED_HEIGHT = 760
    RESULTS_PREFERRED_WIDTH = 850
    _FONT_SIZES = {
        'small':  {'ui': 9,  'mono': 11},
        'medium': {'ui': 11, 'mono': 14},
        'large':  {'ui': 15, 'mono': 18},
    }
    _THEME_NAMES = THEME_NAMES

    @staticmethod
    def _pick_mono_family():
        if sys.platform == 'darwin':
            return 'Menlo'
        if sys.platform == 'win32':
            return 'Consolas'
        available = set(tkfont.families())
        for name in ('DejaVu Sans Mono', 'Liberation Mono', 'Courier New'):
            if name in available:
                return name
        return 'Courier'

    def __init__(self, root):
        """Initialize application state, preferences, data model, and widgets."""
        self._config = ConfigManager(ConfigManager.default_path())
        self._model = GedcomDataModel()

        self.root = root
        self.root.title(APP_TITLE)

        if sys.platform == 'win32':
            try:
                self.root.iconbitmap(
                    self._resource_path('icons/family_tree.ico'))
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        elif sys.platform != 'darwin':
            try:
                icon = tk.PhotoImage(
                    file=self._resource_path('icons/family_tree.png'))
                self.root.iconphoto(True, icon)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Data state
        self.individuals = {}
        self.families = {}
        self.tag_records = {}
        self.sorted_ids = []
        self._home_person_id = None

        # UI state variables
        self.gedcom_path = tk.StringVar()
        self.tag_keyword = tk.StringVar(value="DNA")
        self.page_marker = tk.StringVar(value="AncestryDNA Match")
        self.search_text = tk.StringVar()
        self.filter_text = tk.StringVar()
        self.show_flagged_only = tk.BooleanVar(value=False)
        self.top_n = tk.IntVar(value=self._config.get_top_n())
        self.max_depth = tk.IntVar(value=self._config.get_max_depth())
        self.fuzzy_threshold = tk.DoubleVar(
            value=self._config.get_fuzzy_threshold(self.FUZZY_THRESHOLD))
        self.status_text = tk.StringVar(value=STATUS_NO_FILE)
        self.fuzzy_search = tk.BooleanVar(value=False)
        self.show_ids = tk.BooleanVar(value=self._config.get_show_ids())
        self._name_order = self._config.get_name_order()

        self.search_text.trace_add('write', self._on_search_change)
        self.filter_text.trace_add('write', self._on_search_change)
        self.show_flagged_only.trace_add('write', self._on_search_change)
        self.fuzzy_search.trace_add('write', self._on_search_change)
        self._search_after_id = None

        self.top_n.trace_add('write', self._on_settings_change)
        self.max_depth.trace_add('write', self._on_settings_change)
        self.fuzzy_threshold.trace_add('write', self._on_search_change)
        self._settings_after_id = None

        self.tag_keyword.trace_add('write', self._on_dna_settings_change)
        self.page_marker.trace_add('write', self._on_dna_settings_change)
        self._dna_settings_after_id = None
        self._last_result = None
        self._busy = False
        self._sort_col = 'name'
        self._sort_rev = False

        self._recent_files = self._load_history()
        self._show_person_geometry = self._load_show_person_geometry()

        self._mono_family = self._pick_mono_family()
        self._mono_size = self._FONT_SIZES['medium']['mono']
        # tkfont.Font objects are used by render_markdown and tag introspection;
        # CTkTextbox requires tuple/CTkFont at creation time (see _build_ui).
        self._mono_font = tkfont.Font(
            family=self._mono_family, size=self._mono_size)
        self._mono_font_bold = tkfont.Font(
            family=self._mono_family, size=self._mono_size, weight='bold')
        self._link_color = '#0066cc'

        # Progress animation state
        self._progress_anim_id = None
        self._progress_anim_val = 0.0

        self._font_size_pref = self._load_font_preference()
        self._theme_pref = self._load_theme_preference()
        self._apply_font_size(self._font_size_pref)
        self._apply_theme(self._theme_pref)

        self._version = __version__
        self._release_date = __release_date__

        try:
            for _pkl in self._cache_dir().glob('*.pkl'):
                _pkl.unlink(missing_ok=True)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        self._build_ui()
        self._fit_window_to_content(
            self.root,
            min_w=800,
            min_h=500,
            preferred_w=self.MAIN_PREFERRED_WIDTH,
            preferred_h=self.MAIN_PREFERRED_HEIGHT,
            max_screen_ratio=0.92,
            center_on_root=False,
        )

        if self._recent_files and os.path.isfile(self._recent_files[0]):
            self.gedcom_path.set(self._recent_files[0])
            self.root.after(0, self._load_file)

    # ---------------------------------------------------------- UI build helpers
    def _section(self, parent, label=None):
        """Return a CTkFrame styled as a labelled section group."""
        outer = ctk.CTkFrame(parent, border_width=1)
        if label:
            ctk.CTkLabel(outer, text=label, anchor='w').pack(
                anchor='nw', padx=10, pady=(6, 2))
        inner = ctk.CTkFrame(outer, fg_color='transparent')
        inner.pack(fill='x', padx=8, pady=(0, 8))
        return inner

    # ---------------------------------------------------------- UI build
    def _build_ui(self):
        """Build the main application window and connect primary controls."""
        self._setup_menu()
        outer = ctk.CTkFrame(self.root, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=8, pady=8)

        # File row
        file_group = ctk.CTkFrame(outer, border_width=1)
        file_group.pack(fill='x')
        ctk.CTkLabel(file_group, text=FRAME_GEDCOM_FILE, anchor='w').pack(
            anchor='nw', padx=10, pady=(6, 2))
        file_frame = ctk.CTkFrame(file_group, fg_color='transparent')
        file_frame.pack(fill='x', padx=8, pady=(0, 8))

        self.path_combo = ctk.CTkComboBox(
            file_frame, variable=self.gedcom_path,
            values=self._recent_files,
            command=lambda *_: self._load_file(),
        )
        self.path_combo.pack(side='left', fill='x', expand=True, padx=(0, 4))
        self.browse_btn = ctk.CTkButton(
            file_frame, text=BTN_BROWSE, width=80, command=self._browse)
        self.browse_btn.pack(side='left', padx=2)
        Tooltip(self.browse_btn, TIP_BROWSE)

        # Settings row
        settings_group = ctk.CTkFrame(outer, border_width=1)
        settings_group.pack(fill='x', pady=(8, 0))
        ctk.CTkLabel(settings_group, text=FRAME_DNA_SETTINGS, anchor='w').pack(
            anchor='nw', padx=10, pady=(6, 2))
        settings_frame = ctk.CTkFrame(settings_group, fg_color='transparent')
        settings_frame.pack(fill='x', padx=8, pady=(0, 8))

        # Tag Keyword and Page Marker settings
        ctk.CTkLabel(settings_frame, text=LBL_TAG_KEYWORD).grid(
            row=0, column=0, sticky='w', padx=(0, 4))
        ctk.CTkEntry(settings_frame, textvariable=self.tag_keyword,
                     width=150).grid(row=0, column=1, padx=(0, 16))
        Tooltip(settings_frame.grid_slaves(row=0, column=1)[0], TIP_TAG_KEYWORD)
        ctk.CTkLabel(settings_frame, text=LBL_PAGE_MARKER).grid(
            row=0, column=2, sticky='w', padx=(0, 4))
        ctk.CTkEntry(settings_frame, textvariable=self.page_marker,
                     width=240).grid(row=0, column=3, padx=(0, 16))
        Tooltip(settings_frame.grid_slaves(row=0, column=3)[0], TIP_PAGE_MARKER)
        _select_tag_btn = ctk.CTkButton(
            settings_frame, text=BTN_SELECT_TAG, width=100, command=self._view_tags)
        _select_tag_btn.grid(row=0, column=4, padx=4)
        Tooltip(_select_tag_btn, TIP_SELECT_TAG)
        _find_path_btn = ctk.CTkButton(
            settings_frame, text=BTN_FIND_PATH, width=120, command=self._find_path)
        _find_path_btn.grid(row=0, column=5, padx=(12, 4))
        Tooltip(_find_path_btn, TIP_FIND_PATH)

        # Main paned area
        paned = ttk.PanedWindow(outer, orient='horizontal')
        paned.pack(fill='both', expand=True, pady=(8, 0))

        # --- Left pane ---
        left = ctk.CTkFrame(paned, fg_color='transparent')
        paned.add(left, weight=1)

        search_frame = ctk.CTkFrame(left, fg_color='transparent')
        search_frame.pack(fill='x')
        # Find: box
        ctk.CTkLabel(search_frame, text=LBL_FIND).pack(
            side='left', padx=(0, 4))
        self.search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.search_text)
        self.search_entry.pack(side='left', fill='x', expand=True)
        self.search_entry.bind(
            '<Return>', lambda *_: self._search_flush_and_jump())
        Tooltip(self.search_entry, TIP_FIND)
        # DNA-flagged only and fuzzy search checkboxes
        ctk.CTkCheckBox(
            search_frame, text=CHK_DNA_FLAGGED_ONLY,
            variable=self.show_flagged_only, width=0,
        ).pack(side='left', padx=(8, 0))
        Tooltip(search_frame.winfo_children()[-1], TIP_DNA_FLAGGED_ONLY)
        ctk.CTkCheckBox(
            search_frame, text=CHK_FUZZY,
            variable=self.fuzzy_search, width=0,
        ).pack(side='left', padx=(8, 0))
        Tooltip(search_frame.winfo_children()[-1], TIP_FUZZY)

        # Filter: box
        filter_frame = ctk.CTkFrame(left, fg_color='transparent')
        filter_frame.pack(fill='x', pady=(2, 0))
        ctk.CTkLabel(filter_frame, text=LBL_FILTER).pack(
            side='left', padx=(0, 4))
        self.filter_entry = ctk.CTkEntry(
            filter_frame, textvariable=self.filter_text)
        self.filter_entry.pack(side='left', fill='x', expand=True)
        self.filter_entry.bind('<Return>', lambda *_: self._kb_focus_list())
        Tooltip(self.filter_entry, TIP_FILTER)

        list_frame = ctk.CTkFrame(left, fg_color='transparent')
        list_frame.pack(fill='both', expand=True, pady=(4, 0))

        self.tree = ttk.Treeview(
            list_frame,
            columns=('name', 'birth', 'death', 'flagged'),
            show='headings',
            selectmode='browse',
        )
        self.tree.heading('name', text=COL_NAME,
                          command=lambda: self._sort_by('name'))
        self.tree.heading('birth', text=COL_BIRTH,
                          command=lambda: self._sort_by('birth'))
        self.tree.heading('death', text=COL_DEATH,
                          command=lambda: self._sort_by('death'))
        self.tree.heading('flagged', text=COL_DNA,
                          command=lambda: self._sort_by('flagged'))
        self.tree.column('name', width=240, anchor='w', stretch=True)
        self.tree.column('birth', width=55, anchor='w', stretch=False)
        self.tree.column('death', width=55, anchor='w', stretch=False)
        self.tree.column('flagged', width=50, anchor='center', stretch=False)

        ysb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        is_dark = ctk.get_appearance_mode() == 'Dark'
        self.tree.tag_configure('flagged_row', background=get_flag_bg(is_dark))

        self.tree.bind('<Double-1>', lambda *_: self._find_matches())
        self.tree.bind('<Return>', lambda *_: self._find_matches())
        self.tree.bind('<Key>', self._tree_type_ahead)
        self.tree.bind('<Home>', lambda *_: self._tree_jump('first') or 'break')
        self.tree.bind('<End>', lambda *_: self._tree_jump('last') or 'break')

        # Action controls
        action_frame = ctk.CTkFrame(left, fg_color='transparent')
        action_frame.pack(fill='x', pady=(6, 0))
        # Buttons are packed first (side='right') so they claim their full
        # width before the spinboxes. On Linux, larger font metrics can leave
        # set_home_btn with insufficient room when left-side widgets pack first.
        self.find_matches_btn = ctk.CTkButton(
            action_frame, text=BTN_FIND_MATCHES, command=self._find_matches)
        self.find_matches_btn.pack(side='right')
        self.show_person_btn = ctk.CTkButton(
            action_frame, text=BTN_SHOW_PERSON, command=self._show_person)
        self.show_person_btn.pack(side='right', padx=(0, 6))
        self.set_home_btn = ctk.CTkButton(
            action_frame, text=BTN_SET_HOME, command=self._set_home_person)
        self.set_home_btn.pack(side='right', padx=(0, 4))
        _top_n_label = ctk.CTkLabel(action_frame, text=LBL_TOP_N)
        _top_n_label.pack(side='left')
        self.top_n_spin = ttk.Spinbox(
            action_frame, from_=1, to=20, textvariable=self.top_n, width=4)
        self.top_n_spin.pack(side='left', padx=(2, 12))
        Tooltip(_top_n_label, TIP_TOP_N)
        Tooltip(self.top_n_spin, TIP_TOP_N)
        _max_depth_label = ctk.CTkLabel(action_frame, text=LBL_MAX_DEPTH)
        _max_depth_label.pack(side='left')
        self.max_depth_spin = ttk.Spinbox(
            action_frame, from_=1, to=200, textvariable=self.max_depth, width=5)
        self.max_depth_spin.pack(side='left', padx=(2, 12))
        Tooltip(_max_depth_label, TIP_MAX_DEPTH)
        Tooltip(self.max_depth_spin, TIP_MAX_DEPTH)

        # --- Right pane ---
        right = ctk.CTkFrame(paned, fg_color='transparent')
        paned.add(right, weight=3)

        results_header = ctk.CTkFrame(right, fg_color='transparent')
        results_header.pack(fill='x')
        ctk.CTkLabel(results_header, text=LBL_RESULTS).pack(side='left')
        ctk.CTkButton(results_header, text=BTN_COPY, width=60,
                      command=self._copy_results).pack(side='right')

        self.results = ctk.CTkTextbox(
            right,
            font=(self._mono_family, self._mono_size),
            wrap='word', height=10, width=self.RESULTS_PREFERRED_WIDTH,
            activate_scrollbars=True,
        )
        self.results.pack(fill='both', expand=True, pady=(4, 0))
        self.results._textbox.tag_configure(
            'bold', font=(self._mono_family, self._mono_size, 'bold'))
        self.results.configure(state='disabled')

        # Status bar
        status_bar = ctk.CTkFrame(outer, border_width=1)
        status_bar.pack(fill='x', pady=(8, 0))
        status_bar.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            status_bar, textvariable=self.status_text, anchor='w',
        ).grid(row=0, column=0, sticky='ew', padx=(8, 0), pady=4)
        self._progress_bar = ctk.CTkProgressBar(status_bar, width=130)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=1, padx=(4, 8), pady=4)
        self._progress_bar.grid_remove()

        self._setup_keybindings()

    # ---------------------------------------------------------- Busy / progress
    def _show_progress(self, msg=None):
        """Reveal the animated progress bar and optionally set status text."""
        if msg:
            self.status_text.set(msg)
        self._progress_bar.grid()
        self._progress_anim_val = 0.0
        if self._progress_anim_id is None:
            self._tick_progress()
        self.root.update_idletasks()

    def _tick_progress(self):
        """Advance the progress bar animation one step."""
        self._progress_anim_val = (self._progress_anim_val + 0.03) % 1.0
        self._progress_bar.set(self._progress_anim_val)
        self._progress_anim_id = self.root.after(50, self._tick_progress)

    def _hide_progress(self):
        """Stop and hide the progress bar."""
        if self._progress_anim_id is not None:
            self.root.after_cancel(self._progress_anim_id)
            self._progress_anim_id = None
        self._progress_bar.grid_remove()

    def _set_busy(self, busy):
        """Disable or re-enable the controls that trigger long operations."""
        self._busy = busy
        state = 'disabled' if busy else 'normal'
        for widget in (self.browse_btn, self.path_combo, self.find_matches_btn):
            widget.configure(state=state)

    # ---------------------------------------------------------- Handlers
    def _browse(self):
        """Prompt for a GEDCOM or ZIP file and load it when selected."""
        current = self.gedcom_path.get().strip()
        initialdir = os.path.dirname(current) if current else None
        path = filedialog.askopenfilename(
            title=DLG_SELECT_GEDCOM,
            filetypes=[("GEDCOM files", "*.ged *.gedcom *.zip"),
                       ("All files", "*.*")],
            initialdir=initialdir,
        )
        if path:
            self.gedcom_path.set(path)
            self._load_file()

    def _load_file(self):
        """Load the selected GEDCOM file into the model and refresh the UI."""
        if self._busy:
            return
        path = self.gedcom_path.get().strip()
        if not path:
            messagebox.showerror(ERR_NO_FILE_TITLE, ERR_NO_FILE_MSG)
            return
        if not os.path.isfile(path):
            messagebox.showerror(ERR_NOT_FOUND_TITLE,
                                 ERR_NOT_FOUND_MSG.format(path=path))
            return

        gedcom_path = path
        tmp_path = None
        if path.lower().endswith('.zip'):
            try:
                tmp_path, ged_name = extract_ged_from_zip(path)
                gedcom_path = tmp_path
                self.status_text.set(
                    STATUS_EXTRACTED_ZIP.format(name=ged_name))
            except Exception as e:  # pylint: disable=broad-exception-caught
                messagebox.showerror(
                    ERR_ZIP_TITLE, ERR_ZIP_MSG.format(error=e))
                return

        self._show_progress(STATUS_LOADING)
        self._set_busy(True)

        dna_keyword = self.tag_keyword.get()
        page_marker = self.page_marker.get()
        cache_dir = self._cache_dir()

        def _do_load():
            try:
                result = self._model.load(
                    gedcom_path,
                    dna_keyword=dna_keyword,
                    page_marker=page_marker,
                    cache_dir=cache_dir,
                )
                self.root.after(0, lambda: _on_done(result, None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.root.after(0, lambda: _on_done(None, e))

        def _on_done(result, error):
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            self._hide_progress()
            self._set_busy(False)
            if error:
                self.status_text.set(STATUS_LOAD_FAILED)
                messagebox.showerror(
                    ERR_PARSE_TITLE, ERR_PARSE_MSG.format(error=error))
                return
            from_cache, encoding_warning = result
            self.individuals = self._model.individuals
            self.families = self._model.families
            self.tag_records = self._model.tag_records
            if encoding_warning:
                messagebox.showwarning(ERR_ENCODING_TITLE, encoding_warning)
            self.sorted_ids = sorted(
                self.individuals.keys(),
                key=lambda iid: (self.individuals[iid]['name'].lower(), iid),
            )
            self._add_to_history(path)
            self._home_person_id = self._load_home_person(path)
            self._populate_tree()
            status = (STATUS_LOADED_CACHED.format(count=len(self.individuals))
                      if from_cache
                      else STATUS_LOADED.format(count=len(self.individuals)))
            self.status_text.set(status)

        threading.Thread(target=_do_load, daemon=True).start()

    def _on_settings_change(self, *_):
        """Debounce search depth and result count changes before rerendering."""
        if self._settings_after_id is not None:
            self.root.after_cancel(self._settings_after_id)
        self._settings_after_id = self.root.after(400, self._refresh_result)

    def _on_dna_settings_change(self, *_):
        """Debounce DNA marker setting changes before reloading data."""
        if self._dna_settings_after_id is not None:
            self.root.after_cancel(self._dna_settings_after_id)
        self._dna_settings_after_id = self.root.after(
            800, self._reload_if_loaded)

    def _reload_if_loaded(self):
        """Reload the active GEDCOM when DNA marker settings change."""
        self._dna_settings_after_id = None
        if self.individuals:
            self._load_file()

    def _refresh_result(self):
        """Recompute and redraw the most recent result view."""
        self._settings_after_id = None
        if not self._last_result or not self.individuals:
            return
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return
        kind = self._last_result['type']
        start_id = self._last_result['start_id']
        if kind == 'dna_matches':
            results = self._model.find_dna_matches(start_id, top_n, max_depth)
            self._render_results(start_id, results)
        elif kind == 'path':
            end_id = self._last_result['end_id']
            paths, truncated = self._model.find_all_paths(
                start_id, end_id, top_n, max_depth)
            self._render_path_results(start_id, end_id, paths, truncated)

    def _on_search_change(self, *_):
        """Debounce person-list filtering while the user types."""
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(150, self._populate_tree)

    def _search_flush_and_jump(self):
        """Apply pending search filters immediately and select the first row."""
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
            self._search_after_id = None
            self._populate_tree()
        self._tree_jump('first')

    def _populate_tree(self):
        """Populate the people list using current search, filter, and sort settings."""
        self._search_after_id = None
        prev_sel = self.tree.selection()
        prev_id = prev_sel[0] if prev_sel else None

        self.tree.delete(*self.tree.get_children())

        if not self.individuals:
            return

        query = self.search_text.get().strip().lower()
        query_tokens = query.split()
        filter_query = self.filter_text.get().strip().lower()
        flagged_only = self.show_flagged_only.get()
        flagged_count = sum(
            1 for i in self.individuals.values() if i['dna_markers'])

        _col_labels = {'name': COL_NAME, 'birth': COL_BIRTH,
                       'death': COL_DEATH, 'flagged': COL_DNA}
        for _col, _label in _col_labels.items():
            suffix = (
                ' ▼' if self._sort_rev else ' ▲') if _col == self._sort_col else ''
            self.tree.heading(_col, text=_label + suffix)

        def _sort_key(indi_id):
            indi = self.individuals[indi_id]
            name = self._display_name(indi).lower()
            if self._sort_col == 'birth':
                by = indi['birth_year']
                return (by is None, by or 0, name)
            if self._sort_col == 'death':
                dy = indi['death_year']
                return (dy is None, dy or 0, name)
            if self._sort_col == 'flagged':
                return (not bool(indi['dna_markers']), name)
            return (name, indi_id)

        display_ids = sorted(self.sorted_ids, key=_sort_key,
                             reverse=self._sort_rev)

        shown = 0
        truncated = False
        for indi_id in display_ids:
            indi = self.individuals[indi_id]
            if flagged_only and not indi['dna_markers']:
                continue
            if query_tokens:
                all_names = indi['alt_names'] or [indi['name']]
                id_lower = indi_id.lower()
                if self.fuzzy_search.get():
                    match = (
                        any(
                            all(self._fuzzy_token_matches(tok, name.lower().split())
                                for tok in query_tokens)
                            for name in all_names
                        )
                        or query in id_lower
                    )
                else:
                    match = (
                        any(
                            all(tok in name.lower() for tok in query_tokens)
                            for name in all_names
                        )
                        or query in id_lower
                    )
                if not match:
                    continue
            if filter_query:
                raw_text = ' '.join(v.lower() for _, _, _, v in indi['_raw'])
                if filter_query not in raw_text:
                    continue
            if shown >= self.MAX_LIST_DISPLAY:
                truncated = True
                break
            tags = ('flagged_row',) if indi['dna_markers'] else ()
            flagged_mark = '✓' if indi['dna_markers'] else ''
            self.tree.insert(
                '', 'end', iid=indi_id,
                values=(self._display_name(indi),
                        indi['birth_year'] or '',
                        indi['death_year'] or '',
                        flagged_mark),
                tags=tags,
            )
            shown += 1

        if prev_id and self.tree.exists(prev_id):
            self.tree.selection_set(prev_id)
            self.tree.see(prev_id)
        elif shown == 1 and (query or flagged_only):
            only = self.tree.get_children()[0]
            self.tree.selection_set(only)
            self.tree.see(only)

        total = len(self.individuals)
        if truncated:
            self.status_text.set(STATUS_SHOWING_FIRST.format(
                max_display=self.MAX_LIST_DISPLAY, total=total, flagged=flagged_count))
        elif query or flagged_only:
            self.status_text.set(STATUS_MATCHES.format(
                shown=shown, plural='es' if shown != 1 else '',
                total=total, flagged=flagged_count))
        else:
            self.status_text.set(STATUS_OVERVIEW.format(
                total=total, families=len(self.families), flagged=flagged_count))

    def _fuzzy_token_matches(self, token, name_words):
        """Return whether token fuzzily matches any word in a name."""
        try:
            threshold = float(self.fuzzy_threshold.get())
        except (tk.TclError, ValueError):
            threshold = self.FUZZY_THRESHOLD
        return any(
            difflib.SequenceMatcher(
                None, token, word).ratio() >= threshold
            for word in name_words
        )

    def _sort_by(self, col):
        """Toggle sorting for the people list by the requested column."""
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        self._populate_tree()

    def _find_matches(self):
        """Find and display nearest DNA-flagged matches for the selected person."""
        if self._busy:
            return
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        start_id = sel[0]
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(ERR_BAD_VAL_TITLE, ERR_BAD_VAL_TOP_N)
            return

        self._show_progress()
        self._set_busy(True)

        def _do_search():
            try:
                results = self._model.find_dna_matches(
                    start_id, top_n, max_depth)
                self.root.after(0, lambda: _on_done(results, None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.root.after(0, lambda: _on_done(None, e))

        def _on_done(results, error):
            self._hide_progress()
            self._set_busy(False)
            if error:
                messagebox.showerror(ERR_PARSE_TITLE, str(error))
                return
            self._last_result = {'type': 'dna_matches', 'start_id': start_id}
            self._render_results(start_id, results)

        threading.Thread(target=_do_search, daemon=True).start()

    def _render_results(self, start_id, results):
        """Render DNA match search results and family context."""
        w = self.results
        tw = w._textbox
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        tw.tag_configure('person_link')
        tw.tag_bind('person_link', '<Enter>',
                    lambda *_: tw.config(cursor='hand2'))
        tw.tag_bind('person_link', '<Leave>',
                    lambda *_: tw.config(cursor=''))

        def nl(text='', bold=False):
            w.insert('end', text + '\n', ('bold',) if bold else ())

        def hr():
            w.update_idletasks()
            tw = w._textbox
            pix_width = max(tw.winfo_width() - 4, 100)
            is_dark = ctk.get_appearance_mode() == 'Dark'
            sep_color = '#DCE4EE' if is_dark else '#1a1a1a'
            sep = tk.Frame(tw, height=2, width=pix_width,
                           bg=sep_color, bd=0, relief='flat')
            tw.window_create('end', window=sep)
            tw.insert('end', '\n')

        def person(indi_id, prefix='', suffix='', bold=False):
            base = ('bold',) if bold else ()
            if prefix:
                w.insert('end', prefix, base)
            tag = f'pers_{indi_id.strip("@")}'
            w.insert('end', describe(self.individuals[indi_id], show_id=self.show_ids.get()),
                     base + ('person_link', tag))
            tw.tag_configure(tag, foreground=self._link_color)
            tw.tag_bind(tag, '<Button-1>',
                        lambda _, iid=indi_id: self._navigate_to(iid))
            if suffix:
                w.insert('end', suffix, base)
            w.insert('end', '\n')

        start = self.individuals[start_id]
        person(start_id, prefix=RESULT_STARTING_FROM)
        if start['dna_markers']:
            nl(RESULT_DNA_FLAGGED_NOTE)
            for m in start['dna_markers']:
                nl(f"    - {self._format_marker(m)}")
        nl()

        if not results:
            nl(RESULT_NO_DNA_FOUND)
        else:
            ancestors = get_ancestor_depths(
                start_id, self.individuals, self.families)
            descendants = get_descendant_depths(
                start_id, self.individuals, self.families)
            hr()
            for rank, (dist, path) in enumerate(results, 1):
                end_id = path[-1][0]
                person(end_id,
                       prefix=RESULT_RANK_PREFIX.format(rank=rank),
                       suffix=RESULT_DISTANCE.format(dist=dist), bold=True)
                rel = describe_relationship(
                    path, self.individuals,
                    ancestors=ancestors, descendants=descendants)
                nl(RESULT_RELATIONSHIP.format(rel=rel))
                nl(RESULT_PATH)
                for i, (node_id, edge) in enumerate(path):
                    if i == 0:
                        person(node_id, prefix="     ")
                    else:
                        person(node_id, prefix=RESULT_EDGE.format(edge=edge))
                nl(RESULT_DNA_MARKERS)
                for m in self.individuals[end_id]['dna_markers']:
                    nl(f"     - {self._format_marker(m)}")
                hr()

        # Family section
        nl(FAM_SECTION, bold=True)
        family_found = False
        parents, siblings, children = self._get_family_members(start_id)

        if parents:
            family_found = True
            nl(FAM_PARENTS)
            for pid in parents:
                person(pid, prefix="    ")
        if siblings:
            family_found = True
            nl(FAM_SIBLINGS)
            for sib_id in siblings:
                person(sib_id, prefix="    ")
        if children:
            family_found = True
            nl(FAM_CHILDREN)
            for child_id in children:
                person(child_id, prefix="    ")
        if not family_found:
            nl(FAM_NO_INFO)
        nl()

        # Home person relationship
        home_id = self._home_person_id
        if home_id and home_id != start_id and home_id in self.individuals:
            hr()
            nl(RESULT_PATH_SECTION, bold=True)
            person(home_id, prefix=RESULT_HOME)
            try:
                max_depth = int(self.max_depth.get())
            except (tk.TclError, ValueError):
                max_depth = 50
            home_paths, _ = bfs_find_all_paths(
                start_id, home_id, self.individuals, self.families,
                top_n=1, max_depth=max_depth,
            )
            if not home_paths:
                nl(RESULT_NO_HOME_PATH)
            else:
                path = home_paths[0]
                ancestors = get_ancestor_depths(
                    start_id, self.individuals, self.families)
                descendants = get_descendant_depths(
                    start_id, self.individuals, self.families)
                rel = describe_relationship(
                    path, self.individuals,
                    ancestors=ancestors, descendants=descendants)
                dist = len(path) - 1
                nl(RESULT_HOME_REL.format(
                    rel=rel, dist=dist, plural='s' if dist != 1 else ''))
                nl(RESULT_HOME_PATH)
                for i, (node_id, edge) in enumerate(path):
                    if i == 0:
                        person(node_id, prefix="  ")
                    else:
                        person(node_id, prefix=RESULT_HOME_EDGE.format(edge=edge))
            nl()

        w.configure(state='disabled')

    def _copy_results(self):
        """Copy the current results text to the clipboard."""
        text = self.results.get('1.0', 'end').rstrip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _clear_results(self):
        """Clear result output and reset search focus."""
        self.results.configure(state='normal')
        self.results.delete('1.0', 'end')
        self.results.configure(state='disabled')
        self.search_text.set('')
        self._last_result = None
        self._kb_focus_search()

    def _format_marker(self, marker):
        """Strip the trailing (@ref@) from a DNA marker string when Show IDs is off."""
        if self.show_ids.get():
            return marker
        return re.sub(r'\s*\(@[^@]+@\)\s*$', '', marker)

    def _clear_person_tags(self, widget):
        """Remove generated person-link tags from a Text-like widget."""
        tw = getattr(widget, '_textbox', widget)
        for tag in tw.tag_names():
            if tag.startswith('pers_'):
                tw.tag_delete(tag)

    def _navigate_to(self, indi_id):
        """Select a person in the list and render their DNA match results."""
        if not self.tree.exists(indi_id):
            self.search_text.set('')
            self.filter_text.set('')
            self.show_flagged_only.set(False)
            self._populate_tree()
        if self.tree.exists(indi_id):
            self.tree.selection_set(indi_id)
            self.tree.see(indi_id)
            self.tree.focus(indi_id)
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return
        results = bfs_find_dna_matches(
            indi_id, self.individuals, self.families,
            top_n=top_n, max_depth=max_depth,
        )
        self._last_result = {'type': 'dna_matches', 'start_id': indi_id}
        self._render_results(indi_id, results)

    def _display_name(self, indi):
        """Return an individual's display name using the configured name order."""
        if self._name_order == 'last_first':
            surname = indi.get('surname', '')
            given = indi.get('given_name', '')
            if surname and given:
                return f"{surname}, {given}"
            if surname:
                return surname
        return indi['name'] or '(unknown)'

    def _get_family_members(self, indi_id):
        """Return (parents, siblings, children) lists for an individual."""
        indi = self.individuals[indi_id]
        parents, siblings, children = [], [], []
        for fam_id in indi['famc']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            for pid in (fam['husb'], fam['wife']):
                if pid and pid in self.individuals:
                    parents.append(pid)
            for sib_id in fam['chil']:
                if sib_id != indi_id and sib_id in self.individuals:
                    siblings.append(sib_id)
        for fam_id in indi['fams']:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            for child_id in fam['chil']:
                if child_id in self.individuals:
                    children.append(child_id)
        return parents, siblings, children


def main():
    """Parse command-line options, create the GUI, and start the event loop."""
    parser = argparse.ArgumentParser(
        description='GEDCOM DNA Finder GUI. '
                    'Optionally pass a GEDCOM file path to load it on startup.'
    )
    parser.add_argument(
        'gedcom', nargs='?', default=None,
        help='Optional path to a .ged file to load automatically on startup.'
    )
    args = parser.parse_args()

    root = ctk.CTk()
    app = DNAMatchFinderApp(root)

    if args.gedcom:
        path = os.path.abspath(os.path.expanduser(args.gedcom))
        app.gedcom_path.set(path)
        if os.path.isfile(path):
            root.after(50, app._load_file)
        else:
            root.after(
                50,
                lambda p=path: messagebox.showerror(
                    ERR_FILE_NOT_FOUND_TITLE,
                    ERR_GEDCOM_NOT_FOUND_MSG.format(path=p),
                ),
            )

    root.mainloop()


if __name__ == '__main__':
    main()
