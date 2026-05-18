#!/usr/bin/env python3
"""
gedcom_dna_finder_gui.py

customtkinter GUI for finding the nearest DNA-flagged relative(s) to a target
person in a GEDCOM tree.
"""

import argparse
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import customtkinter as ctk

from gedcom_data_model import GedcomDataModel
from gedcom_config import ConfigManager
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_gui_background import BackgroundTaskMixin
from gedcom_gui_search import SearchMixin
from gedcom_gui_results import ResultsMixin
from gedcom_platform import configure_process_identity
from gedcom_theme import THEME_NAMES, get_flag_bg, ttk_colors
from gedcom_tooltip import Tooltip
from gedcom_zoom import TextZoomController
from gedcom_gui_appearance import AppearanceMixin
from gedcom_gui_dialogs import DialogsMixin


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


# GUI
# ===========================================================================

class DNAMatchFinderApp(
    DialogsMixin,
    AppearanceMixin,
    SearchMixin,
    ResultsMixin,
    BackgroundTaskMixin,
):
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
            return 'Consolas'  # cspell: disable-line
        available = set(tkfont.families())
        for name in ('DejaVu Sans Mono', 'Liberation Mono', 'Courier New'):
            if name in available:
                return name
        return 'Courier'

    def __init__(self, root):
        """Initialize application state, preferences, data model, and widgets."""
        configure_process_identity()
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
        self.married_name_search = tk.BooleanVar(value=False)
        self.show_ids = tk.BooleanVar(value=self._config.get_show_ids())
        self._name_order = self._config.get_name_order()
        self._default_profile_view = self._config.get_profile_view_default()

        self.search_text.trace_add('write', self._on_search_change)
        self.filter_text.trace_add('write', self._on_search_change)
        self.show_flagged_only.trace_add('write', self._on_search_change)
        self.fuzzy_search.trace_add('write', self._on_search_change)
        self.married_name_search.trace_add('write', self._on_search_change)
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
        self._results_header_id = None
        self._busy = False
        self._sort_col = 'name'
        self._sort_rev = False

        self._recent_files = self._load_history()
        self._show_person_geometry = self._load_show_person_geometry()
        self._show_person_opened_this_session = False
        self._path_graph_geometry = None
        self._path_graph_opened_this_session = False

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
        self._search_popup = None
        self._search_popup_bar = None
        self._search_popup_anim_id = None
        self._background_cancel_event = None

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
            text_w = max(heading_font.measure(text),
                         heading_font.measure(sample))
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
        # ctk.CTkLabel(settings_group, text=FRAME_DNA_SETTINGS, anchor='w').pack(
        #    anchor='nw', padx=10, pady=(6, 2))
        settings_frame = ctk.CTkFrame(settings_group, fg_color='transparent')
        settings_frame.pack(fill='x', padx=8, pady=(6, 8))

        # Tag Keyword and Page Marker settings
        ctk.CTkLabel(settings_frame, text=LBL_TAG_KEYWORD).grid(
            row=0, column=0, sticky='w', padx=(0, 4))
        ctk.CTkEntry(settings_frame, textvariable=self.tag_keyword,
                     width=150).grid(row=0, column=1, padx=(0, 16))
        Tooltip(settings_frame.grid_slaves(
            row=0, column=1)[0], TIP_TAG_KEYWORD)
        ctk.CTkLabel(settings_frame, text=LBL_PAGE_MARKER).grid(
            row=0, column=2, sticky='w', padx=(0, 4))
        ctk.CTkEntry(settings_frame, textvariable=self.page_marker,
                     width=240).grid(row=0, column=3, padx=(0, 16))
        Tooltip(settings_frame.grid_slaves(
            row=0, column=3)[0], TIP_PAGE_MARKER)
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
        # Search mode checkboxes
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
        ctk.CTkCheckBox(
            search_frame, text=CHK_MARRIED_NAMES,
            variable=self.married_name_search, width=0,
        ).pack(side='left', padx=(8, 0))
        Tooltip(search_frame.winfo_children()[-1], TIP_MARRIED_NAMES)

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
        self.tree.bind(
            '<Home>', lambda *_: self._tree_jump('first') or 'break')
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
        _show_person_label = (BTN_SHOW_PERSON_TREE
                              if self._default_profile_view == 'tree'
                              else BTN_SHOW_PERSON)
        _show_person_tip = (TIP_SHOW_PERSON_TREE
                            if self._default_profile_view == 'tree'
                            else TIP_SHOW_PERSON)
        self.show_person_btn = ctk.CTkButton(
            action_frame, text=_show_person_label, command=self._show_person)
        self.show_person_btn.grid(row=0, column=6, padx=(0, 6))
        self._show_person_tooltip = Tooltip(self.show_person_btn, _show_person_tip)
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
        self._results_header_label.pack(
            side='left', fill='x', expand=True, ipady=4)
        self._results_header_label.bind(
            '<Button-3>', self._show_results_header_menu)
        self._results_header_label.bind(
            '<Control-Button-1>', self._show_results_header_menu)

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

        def _apply_results_zoom(size):
            self.results.configure(font=(self._mono_family, size))
            self.results._textbox.tag_configure(
                'bold', font=(self._mono_family, size, 'bold'))

        self._results_zoom = TextZoomController(
            self.results, self._mono_size, _apply_results_zoom)

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
        self._save_btn = ctk.CTkButton(status_bar, text=BTN_SAVE, width=80,
                                       command=self._save_results)
        self._save_btn.grid(row=0, column=2, padx=(4, 4), pady=4)
        Tooltip(self._save_btn, TIP_SAVE)
        self._copy_btn = ctk.CTkButton(status_bar, text=BTN_COPY, width=80,
                                       command=self._copy_results)
        self._copy_btn.grid(row=0, column=3, padx=(4, 8), pady=4)
        Tooltip(self._copy_btn, TIP_COPY)
        self._progress_bar = ctk.CTkProgressBar(status_bar, width=130)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=2, columnspan=2, padx=(4, 8), pady=4)
        self._progress_bar.grid_remove()

        self._setup_keybindings()

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
