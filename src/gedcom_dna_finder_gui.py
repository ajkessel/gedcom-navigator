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
from gedcom_strings import * # pylint: disable=unused-wildcard-import
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
from gedcom_theme import THEME_NAMES, get_flag_bg, ttk_colors
from gedcom_tooltip import Tooltip
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
    RESULTS_MIN_WIDTH = 420
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
        self.max_display = tk.IntVar(
            value=self._config.get_max_display(self.MAX_LIST_DISPLAY))
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
        self._results_reversed = False
        self._active_id = None
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
        self._hide_tooltips_pref = self._load_hide_tooltips_preference()
        self._apply_font_size(self._font_size_pref)
        self._apply_theme(self._theme_pref)
        Tooltip.enabled = not self._hide_tooltips_pref

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

    def _configure_tree_columns(self):
        """Size fixed Treeview columns from the current UI font metrics."""
        heading_font = tkfont.nametofont('TkDefaultFont')

        def _fit_heading(text, sample='', padding=34):
            text_w = max(heading_font.measure(text), heading_font.measure(sample))
            return text_w + padding

        name_w = max(240, _fit_heading(COL_NAME, padding=28))
        birth_w = _fit_heading(COL_BIRTH, '0000')
        death_w = _fit_heading(COL_DEATH, '0000')
        flagged_w = _fit_heading(COL_DNA)

        self.tree.column('name', width=name_w, minwidth=name_w,
                         anchor='w', stretch=True)
        self.tree.column('birth', width=birth_w, minwidth=birth_w,
                         anchor='w', stretch=False)
        self.tree.column('death', width=death_w, minwidth=death_w,
                         anchor='w', stretch=False)
        self.tree.column('flagged', width=flagged_w, minwidth=flagged_w,
                         anchor='center', stretch=False)

    # ---------------------------------------------------------- UI build
    def _build_ui(self):
        """Build the main application window and connect primary controls."""
        self._setup_menu()
        outer = ctk.CTkFrame(self.root, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=8, pady=8)

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

        # Main paned area.  Use the classic Tk paned window here because it
        # supports per-pane minsize constraints; ttk.PanedWindow only supports
        # relative weights.
        _pane_colors = ttk_colors(
            ctk.get_appearance_mode() == 'Dark', self._theme_pref)
        paned = tk.PanedWindow(
            outer,
            orient=tk.HORIZONTAL,
            bd=0,
            borderwidth=0,
            sashwidth=6,
            sashrelief='flat',
            opaqueresize=True,
            showhandle=False,
            background=_pane_colors['bg'],
        )
        self._paned = paned
        paned.pack(fill='both', expand=True, pady=(8, 0))

        # --- Left pane ---
        left = ctk.CTkFrame(paned, fg_color='transparent')

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
        self._configure_tree_columns()

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

        # Action controls — single row grid.  Column 4 is a flexible spacer
        # that absorbs surplus space; every other column sizes to its content.
        action_frame = ctk.CTkFrame(left, fg_color='transparent')
        self._action_frame = action_frame
        action_frame.pack(fill='x', pady=(6, 0))
        action_frame.grid_columnconfigure(4, weight=1)

        _top_n_label = ctk.CTkLabel(action_frame, text=LBL_TOP_N)
        _top_n_label.grid(row=0, column=0, sticky='w')
        self.top_n_spin = ttk.Spinbox(
            action_frame, from_=1, to=20, textvariable=self.top_n, width=4)
        self.top_n_spin.grid(row=0, column=1, padx=(2, 12))
        Tooltip(_top_n_label, TIP_TOP_N)
        Tooltip(self.top_n_spin, TIP_TOP_N)

        _max_depth_label = ctk.CTkLabel(action_frame, text=LBL_MAX_DEPTH)
        _max_depth_label.grid(row=0, column=2, sticky='w')
        self.max_depth_spin = ttk.Spinbox(
            action_frame, from_=1, to=200, textvariable=self.max_depth, width=5)
        self.max_depth_spin.grid(row=0, column=3, padx=(2, 0))
        Tooltip(_max_depth_label, TIP_MAX_DEPTH)
        Tooltip(self.max_depth_spin, TIP_MAX_DEPTH)

        self.set_home_btn = ctk.CTkButton(
            action_frame, text=BTN_SET_HOME, command=self._set_home_person)
        self.set_home_btn.grid(row=0, column=5, padx=(0, 6))
        Tooltip(self.set_home_btn, TIP_SET_HOME)
        self.show_person_btn = ctk.CTkButton(
            action_frame, text=BTN_SHOW_PERSON, command=self._show_person)
        self.show_person_btn.grid(row=0, column=6, padx=(0, 6))
        Tooltip(self.show_person_btn, TIP_SHOW_PERSON)
        self.find_matches_btn = ctk.CTkButton(
            action_frame, text=BTN_FIND_MATCHES, command=self._find_matches)
        self.find_matches_btn.grid(row=0, column=7)
        Tooltip(self.find_matches_btn, TIP_FIND_MATCHES)

        # --- Right pane ---
        right = ctk.CTkFrame(paned, fg_color='transparent')

        def _action_min_w():
            # padx totals per grid() call: spinbox1=14, spinbox2=2,
            # set_home=6, show_person=6, find_matches=0
            return (
                _top_n_label.winfo_reqwidth()
                + self.top_n_spin.winfo_reqwidth() + 14
                + _max_depth_label.winfo_reqwidth()
                + self.max_depth_spin.winfo_reqwidth() + 2
                + self.set_home_btn.winfo_reqwidth() + 6
                + self.show_person_btn.winfo_reqwidth() + 6
                + self.find_matches_btn.winfo_reqwidth()
            )

        def _tree_min_w():
            columns_w = sum(
                int(self.tree.column(col, 'minwidth'))
                for col in self.tree['columns']
            )
            scrollbar_w = max(ysb.winfo_reqwidth(), 16)
            return columns_w + scrollbar_w + 12

        def _left_min_w():
            return max(_tree_min_w(), _action_min_w())

        def _clamp(value, lower, upper):
            if upper < lower:
                return max(0, upper)
            return max(lower, min(value, upper))

        def _refresh_main_pane_layout(place_preferred_sash=False):
            try:
                left_min = _left_min_w()
                right_min = self.RESULTS_MIN_WIDTH
                paned.paneconfig(left, minsize=left_min)
                paned.paneconfig(right, minsize=right_min)
                if not place_preferred_sash:
                    return
                pane_w = paned.winfo_width()
                if pane_w <= 1:
                    self.root.after_idle(
                        lambda: _refresh_main_pane_layout(True))
                    return
                max_left = pane_w - right_min
                preferred = pane_w - self.RESULTS_PREFERRED_WIDTH
                target = _clamp(preferred, left_min, max_left)
                paned.sash_place(0, target, 0)
            except tk.TclError:
                pass

        left_min = _left_min_w()
        left.configure(width=left_min)
        right.configure(width=self.RESULTS_PREFERRED_WIDTH)
        paned.add(left, minsize=left_min, width=left_min, sticky='nsew')
        paned.add(
            right,
            minsize=self.RESULTS_MIN_WIDTH,
            width=self.RESULTS_PREFERRED_WIDTH,
            sticky='nsew',
        )
        try:
            paned.paneconfig(left, stretch='never')
            paned.paneconfig(right, stretch='always')
        except tk.TclError:
            pass
        self._refresh_main_pane_layout = _refresh_main_pane_layout
        self.root.after_idle(lambda: _refresh_main_pane_layout(True))

        results_header = ctk.CTkFrame(right, fg_color='transparent')
        results_header.pack(fill='x')
        self._results_header_var = tk.StringVar()
        self._results_header_label = ctk.CTkLabel(
            results_header,
            textvariable=self._results_header_var,
            anchor='center',
            font=ctk.CTkFont(size=self._mono_size, weight='bold'),
            fg_color='transparent',
            corner_radius=6,
        )
        self._results_header_label.pack(side='left', fill='x', expand=True, ipady=4)

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
        self._reverse_btn = ctk.CTkButton(status_bar, text=BTN_REVERSE, width=110,
                                          command=self._reverse_results, state='disabled')
        self._reverse_btn.grid(row=0, column=1, padx=(4, 4), pady=4)
        Tooltip(self._reverse_btn, TIP_REVERSE)
        self._copy_btn = ctk.CTkButton(status_bar, text=BTN_COPY, width=80,
                                       command=self._copy_results)
        self._copy_btn.grid(row=0, column=2, padx=(4, 8), pady=4)
        Tooltip(self._copy_btn, TIP_COPY)
        self._progress_bar = ctk.CTkProgressBar(status_bar, width=130)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=2, padx=(4, 8), pady=4)
        self._progress_bar.grid_remove()

        self._setup_keybindings()

    # ---------------------------------------------------------- Busy / progress
    def _show_progress(self, msg=None):
        """Reveal the animated progress bar and optionally set status text."""
        if msg:
            self.status_text.set(msg)
        self._copy_btn.grid_remove()
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
        self._copy_btn.grid()

    def _set_busy(self, busy):
        """Disable or re-enable the controls that trigger long operations."""
        self._busy = busy
        state = 'disabled' if busy else 'normal'
        self.find_matches_btn.configure(state=state)
        self._file_menu.entryconfigure(MENU_OPEN_GEDCOM, state=state)

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
            from_cache, encoding_warning, model_error = result
            if model_error:
                self.status_text.set(STATUS_LOAD_FAILED)
                messagebox.showerror(
                    ERR_PARSE_TITLE, ERR_PARSE_MSG.format(error=model_error))
                return
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
            def _do_refresh():
                try:
                    results = self._model.find_dna_matches(start_id, top_n, max_depth)
                    home_paths = None
                    home_id = self._home_person_id
                    if home_id and home_id != start_id and home_id in self.individuals:
                        home_paths, _ = bfs_find_all_paths(
                            start_id, home_id, self.individuals, self.families,
                            top_n=1, max_depth=max_depth,
                        )
                    self.root.after(0, lambda: self._render_results(
                        start_id, results, home_paths=home_paths))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            threading.Thread(target=_do_refresh, daemon=True).start()
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

        # Re-sort only when sort settings or underlying data change.
        # id(self.sorted_ids) changes whenever a new file is loaded.
        cache_key = (self._sort_col, self._sort_rev, id(self.sorted_ids))
        if getattr(self, '_pop_sort_key', None) != cache_key:
            self._pop_sorted = sorted(self.sorted_ids, key=_sort_key,
                                      reverse=self._sort_rev)
            self._pop_sort_key = cache_key
        display_ids = self._pop_sorted

        shown = 0
        total_matches = 0
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
            total_matches += 1
            if shown >= self.max_display.get():
                truncated = True
                continue
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
        if truncated and (query or flagged_only):
            self.status_text.set(STATUS_SHOWING_FIRST.format(
                max_display=self.max_display.get(), total_matches=total_matches,
                total=total, flagged=flagged_count))
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
        start_id = sel[0] if sel else self._active_id
        if not start_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
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
                home_paths = None
                home_id = self._home_person_id
                if home_id and home_id != start_id and home_id in self.individuals:
                    home_paths, _ = bfs_find_all_paths(
                        start_id, home_id, self.individuals, self.families,
                        top_n=1, max_depth=max_depth,
                    )
                self.root.after(0, lambda: _on_done(results, home_paths, None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.root.after(0, lambda: _on_done(None, None, e))

        def _on_done(results, home_paths, error):
            self._hide_progress()
            self._set_busy(False)
            if error:
                messagebox.showerror(ERR_PARSE_TITLE, str(error))
                return
            self._results_reversed = False
            self._reverse_btn.configure(text=BTN_REVERSE)
            self._last_result = {'type': 'dna_matches', 'start_id': start_id}
            self._render_results(start_id, results, home_paths=home_paths)

        threading.Thread(target=_do_search, daemon=True).start()

    @staticmethod
    def _reverse_path(path, individuals):
        """Return path reversed with edge labels recalculated for the new direction."""
        if len(path) <= 1:
            return list(path)
        n = len(path)
        result = [(path[n - 1][0], None)]
        for i in range(n - 2, -1, -1):
            orig_edge = path[i + 1][1]
            src_id = path[i][0]
            if orig_edge in ('father', 'mother'):
                rev_edge = 'child'
            elif orig_edge == 'child':
                sex = individuals.get(src_id, {}).get('sex', '')
                rev_edge = 'father' if sex == 'M' else ('mother' if sex == 'F' else 'father')
            else:
                rev_edge = orig_edge
            result.append((src_id, rev_edge))
        return result

    @staticmethod
    def _path_edge_prefix(edge, indent):
        """Return a fixed-width visual connector for an edge label."""
        label = EDGE_LABELS.get(edge, edge)
        label_width = max(len(value) for value in EDGE_LABELS.values())
        return f"{indent}──{label.center(label_width,"─")}──▶ "

    def _reverse_results(self):
        """Toggle reversed display of the current results."""
        if not self._last_result:
            return
        self._results_reversed = not self._results_reversed
        self._reverse_btn.configure(
            text=BTN_REVERSE_RESTORE if self._results_reversed else BTN_REVERSE)
        kind = self._last_result['type']
        if kind == 'dna_matches':
            self._render_results(
                self._last_result['start_id'],
                self._last_result.get('results', []),
                home_paths=self._last_result.get('home_paths'),
            )
        elif kind == 'path':
            self._render_path_results(
                self._last_result['start_id'],
                self._last_result['end_id'],
                self._last_result.get('paths', []),
                self._last_result.get('truncated', False),
            )

    def _render_results(self, start_id, results, home_paths=None):
        """Render DNA match search results and family context."""
        if self._last_result and self._last_result.get('type') == 'dna_matches':
            self._last_result['results'] = results
            self._last_result['home_paths'] = home_paths
        w = self.results
        tw = w._textbox
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        tw.update_idletasks()
        sep_width = max(tw.winfo_width() - 4, 100)
        is_dark = ctk.get_appearance_mode() == 'Dark'
        sep_color = '#DCE4EE' if is_dark else '#1a1a1a'

        tag_to_id = {}
        tw.tag_configure('person_link', foreground=self._link_color)
        tw.tag_bind('person_link', '<Enter>',
                    lambda *_: tw.config(cursor='hand2'))
        tw.tag_bind('person_link', '<Leave>',
                    lambda *_: tw.config(cursor=''))

        def _on_person_click(event):
            idx = tw.index(f'@{event.x},{event.y}')
            for t in tw.tag_names(idx):
                if t.startswith('pers_'):
                    iid = tag_to_id.get(t)
                    if iid:
                        self._navigate_to(iid)
                    break
        tw.tag_bind('person_link', '<Button-1>', _on_person_click)

        def nl(text='', bold=False):
            w.insert('end', text + '\n', ('bold',) if bold else ())

        def hr():
            sep = tk.Frame(tw, height=2, width=sep_width,
                           bg=sep_color, bd=0, relief='flat')
            tw.window_create('end', window=sep)
            tw.insert('end', '\n')

        def person(indi_id, prefix='', suffix='', bold=False):
            base = ('bold',) if bold else ()
            if prefix:
                w.insert('end', prefix, base)
            tag = f'pers_{indi_id.strip("@")}'
            tag_to_id[tag] = indi_id
            w.insert('end', describe(self.individuals[indi_id], show_id=self.show_ids.get()),
                     base + ('person_link', tag))
            #if suffix:
            #    w.insert('end', suffix, base)
            # TODO consider permanently removing code that shows "edges"
            w.insert('end', '\n')

        result_detail_indent = "   "
        result_edge_indent = "       "
        home_edge_indent = "    "

        start = self.individuals[start_id]
        name = self._display_name(start)
        b, d = start.get('birth_year'), start.get('death_year')
        if b and d:
            lifespan = f" ({b}–{d})"
        elif b:
            lifespan = f" (b. {b})"
        elif d:
            lifespan = f" (d. {d})"
        else:
            lifespan = ""
        self._results_header_var.set(name + lifespan)
        self._update_header_label_style()

        nl(RESULT_CLOSEST_MATCHES, bold=True)
        if start['dna_markers']:
            nl(RESULT_DNA_FLAGGED_NOTE)
            for m in start['dna_markers']:
                nl(f"    - {self._format_marker(m)}")
        nl()

        if not results:
            nl(RESULT_NO_DNA_FOUND)
        else:
            hr()
            if self._results_reversed:
                for rank, (dist, path) in enumerate(results, 1):
                    match_id = path[-1][0]
                    rev_path = self._reverse_path(path, self.individuals)
                    m_anc = get_ancestor_depths(match_id, self.individuals, self.families)
                    m_desc = get_descendant_depths(match_id, self.individuals, self.families)
                    rel = describe_relationship(
                        rev_path, self.individuals,
                        ancestors=m_anc, descendants=m_desc,
                        families=self.families)
                    person(match_id,
                           prefix=RESULT_RANK_PREFIX.format(rank=rank), bold=True)
                    nl(result_detail_indent +
                       RESULT_RELATIONSHIP.format(rel=rel))
                    nl(result_detail_indent + RESULT_PATH)
                    for i, (node_id, edge) in enumerate(rev_path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(RESULT_DNA_MARKERS)
                    for m in self.individuals[match_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()
            else:
                ancestors = get_ancestor_depths(
                    start_id, self.individuals, self.families)
                descendants = get_descendant_depths(
                    start_id, self.individuals, self.families)
                for rank, (dist, path) in enumerate(results, 1):
                    end_id = path[-1][0]
                    person(end_id,
                           prefix=RESULT_RANK_PREFIX.format(rank=rank),
                           suffix=RESULT_DISTANCE.format(dist=dist), bold=True)
                    rel = describe_relationship(
                        path, self.individuals,
                        ancestors=ancestors, descendants=descendants,
                        families=self.families)
                    nl(result_detail_indent +
                       RESULT_RELATIONSHIP.format(rel=rel))
                    nl(result_detail_indent + RESULT_PATH)
                    for i, (node_id, edge) in enumerate(path):
                        if i == 0:
                            person(node_id, prefix="     ")
                        else:
                            person(node_id, prefix=self._path_edge_prefix(
                                edge, result_edge_indent))
                    nl(RESULT_DNA_MARKERS)
                    for m in self.individuals[end_id]['dna_markers']:
                        nl(f"     - {self._format_marker(m)}")
                    hr()

        # Family section
        nl(FAM_SECTION, bold=True)
        family_found = False
        parents, siblings, spouses, children = self._get_family_members(start_id)

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
        if spouses:
            family_found = True
            nl(FAM_SPOUSES if len(spouses) > 1 else FAM_SPOUSE)
            for sid in spouses:
                person(sid, prefix="    ")
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
            if not home_paths:
                nl(RESULT_NO_HOME_PATH)
            else:
                raw_path = home_paths[0]
                if self._results_reversed:
                    disp_path = self._reverse_path(raw_path, self.individuals)
                    h_anc = get_ancestor_depths(home_id, self.individuals, self.families)
                    h_desc = get_descendant_depths(home_id, self.individuals, self.families)
                    rel = describe_relationship(
                        disp_path, self.individuals,
                        ancestors=h_anc, descendants=h_desc,
                        families=self.families)
                else:
                    disp_path = raw_path
                    ancestors = get_ancestor_depths(
                        start_id, self.individuals, self.families)
                    descendants = get_descendant_depths(
                        start_id, self.individuals, self.families)
                    rel = describe_relationship(
                        disp_path, self.individuals,
                        ancestors=ancestors, descendants=descendants,
                        families=self.families)
                nl(RESULT_RELATIONSHIP.format(rel=rel))
                nl(RESULT_PATH)
                for i, (node_id, edge) in enumerate(disp_path):
                    if i == 0:
                        person(node_id, prefix="  ")
                    else:
                        person(node_id, prefix=self._path_edge_prefix(
                            edge, home_edge_indent))
            nl()

        self._reverse_btn.configure(state='normal')
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
        self._results_header_var.set('')
        self._update_header_label_style()
        self.search_text.set('')
        self._last_result = None
        self._results_reversed = False
        self._reverse_btn.configure(state='disabled', text=BTN_REVERSE)
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
        """Select a person in the tree and refresh the results pane for them.

        If the right pane currently shows DNA matches, shows DNA matches for the
        new person.  If it shows a relationship path, finds the path from the new
        person to the same destination.
        """
        self._active_id = indi_id
        if not self.tree.exists(indi_id):
            self.search_text.set('')
            self.filter_text.set('')
            self.show_flagged_only.set(False)
            self._populate_tree()
        if self.tree.exists(indi_id):
            self.tree.selection_set(indi_id)
            self.tree.see(indi_id)
            self.tree.focus(indi_id)
        else:
            # Person exceeds max_display even with no filters; clear the stale
            # tree selection so action buttons fall back to _active_id.
            self.tree.selection_remove(*self.tree.selection())
        try:
            top_n = int(self.top_n.get())
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            return
        self._results_reversed = False
        self._reverse_btn.configure(text=BTN_REVERSE)

        kind = self._last_result.get('type') if self._last_result else None

        if kind == 'path':
            end_id = self._last_result.get('end_id', indi_id)
            self._last_result = {'type': 'path', 'start_id': indi_id, 'end_id': end_id}

            def _do_path():
                try:
                    paths, truncated = self._model.find_all_paths(
                        indi_id, end_id, top_n, max_depth)
                    self.root.after(0, lambda: self._render_path_results(
                        indi_id, end_id, paths, truncated))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            threading.Thread(target=_do_path, daemon=True).start()
        else:
            self._last_result = {'type': 'dna_matches', 'start_id': indi_id}

            def _do_dna():
                try:
                    results = bfs_find_dna_matches(
                        indi_id, self.individuals, self.families,
                        top_n=top_n, max_depth=max_depth,
                    )
                    home_paths = None
                    home_id = self._home_person_id
                    if home_id and home_id != indi_id and home_id in self.individuals:
                        home_paths, _ = bfs_find_all_paths(
                            indi_id, home_id, self.individuals, self.families,
                            top_n=1, max_depth=max_depth,
                        )
                    self.root.after(0, lambda: self._render_results(
                        indi_id, results, home_paths=home_paths))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            threading.Thread(target=_do_dna, daemon=True).start()

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
        """Return (parents, siblings, spouses, children) lists for an individual."""
        indi = self.individuals[indi_id]
        parents, siblings, spouses, children = [], [], [], []
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
            spouse_id = fam['wife'] if fam['husb'] == indi_id else fam['husb']
            if spouse_id and spouse_id in self.individuals:
                spouses.append(spouse_id)
            for child_id in fam['chil']:
                if child_id in self.individuals:
                    children.append(child_id)
        return parents, siblings, spouses, children


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
    # On macOS the window briefly appears at the default top-left position
    # before _fit_window_to_content centres it, so withdraw it first.
    # On Windows withdraw()/deiconify() causes the window to vanish; the
    # flash doesn't occur there, so skip it.
    if sys.platform == 'darwin':
        root.withdraw()
    app = DNAMatchFinderApp(root)
    if sys.platform == 'darwin':
        root.deiconify()

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
    else:
        if not (app._recent_files and os.path.isfile(app._recent_files[0])):
            root.after(100, app._browse)

    root.mainloop()


if __name__ == '__main__':
    main()
