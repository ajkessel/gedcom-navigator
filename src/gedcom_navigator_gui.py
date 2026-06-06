#!/usr/bin/env python3
"""
gedcom_navigator_gui.py

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

from gedcom_config import ConfigManager
from gedcom_debug import (
    configure_debug_logging,
    debug_enabled,
    install_exception_hooks,
    log_exception,
    set_debug_enabled,
)
from gedcom_i18n import setup_i18n

# Initialize i18n at the top level before any other local imports.
# This ensures that constants in modules like gedcom_gui_search are translated.
_config = ConfigManager(ConfigManager.default_path())
setup_i18n(_config.get_language())

from gedcom_data_model import GedcomDataModel
from gedcom_media import ProfileMediaService
# gedcom_strings imports will happen after setup_i18n
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_gui_background import BackgroundTaskMixin
from gedcom_gui_search import SearchMixin
from gedcom_gui_results import ResultsMixin
from gedcom_platform import configure_process_identity
from gedcom_theme import THEME_NAMES, get_flag_bg, ttk_colors
from gedcom_tooltip import Tooltip
from gedcom_zoom import TextZoomController, scaled_tag_font
from gedcom_gui_appearance import AppearanceMixin
from gedcom_gui_dialogs import DialogsMixin
from gedcom_walkthrough import WalkthroughMixin


def _read_version():
    _bases = []
    if getattr(sys, 'frozen', False):
        _bases.append(sys._MEIPASS)
    _bases.append(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), '..'))
    for _base in _bases:
        _path = os.path.join(_base, 'gedcom_navigator', '__init__.py')
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

class GedcomNavigatorApp(
    DialogsMixin,
    AppearanceMixin,
    SearchMixin,
    ResultsMixin,
    BackgroundTaskMixin,
    WalkthroughMixin,
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
        'medium': {'ui': 13, 'mono': 14},
        'large':  {'ui': 15, 'mono': 18},
        'jumbo':  {'ui': 20, 'mono': 23},
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
        self._media_service = ProfileMediaService(self._cache_dir())

        self.root = root
        self.root.title(APP_TITLE)

        if sys.platform == 'win32':
            try:
                self.root.iconbitmap(
                    self._resource_path('icons/gedcom_navigator.ico'))
            except Exception:  # pylint: disable=broad-exception-caught
                log_exception("setting Windows window icon")
                pass
        elif sys.platform != 'darwin':
            try:
                icon = tk.PhotoImage(
                    file=self._resource_path('icons/gedcom_navigator.png'))
                self.root.iconphoto(True, icon)
            except Exception:  # pylint: disable=broad-exception-caught
                log_exception("setting Linux window icon")
                pass

        # Data state
        self.individuals = {}
        self.families = {}
        self.tag_records = {}
        self.media_records = {}
        self.sorted_ids = []
        self._home_person_id = None
        self._home_path_cache = {}
        self._profile_home_path_request_id = 0
        self._profile_home_path_pending_key = None
        self._profile_home_path_pending_request_id = None
        self._profile_home_path_cancel_event = None

        # UI state variables
        self.gedcom_path = tk.StringVar()
        self.tag_keyword = tk.StringVar(value=self._config.get_tag_keyword())
        self.page_marker = tk.StringVar(value=self._config.get_page_marker())
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
        self.show_full_gedcom = tk.BooleanVar(value=self._config.get_show_full_gedcom())
        self.show_profile_image = tk.BooleanVar(
            value=self._config.get_show_profile_image())
        self._name_order = self._config.get_name_order()
        self.display_mode = tk.StringVar(value=self._config.get_default_display())
        self.profile_sub_mode = tk.StringVar(value='bio')

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
        self._display_path_target_id = None
        self._suppress_display_refresh = False
        self._active_id = None
        self._results_header_id = None
        self._nav_history = []
        self._nav_forward = []
        self._busy = False
        self._sort_col = 'name'
        self._sort_rev = False

        self._recent_files = self._load_history()
        self._show_person_geometry = self._load_show_person_geometry()
        self._show_person_opened_this_session = False
        self._path_graph_geometry = None
        self._path_graph_opened_this_session = False
        self._path_graph_win = None
        self._path_graph_replace_fn = None
        self._secondary_win = None
        # Automation hooks set while a tree detail window is open (see
        # PersonDialogMixin._show_person_for); used by the App Store screenshot
        # generator to fully expand / zoom the open tree.
        self._expand_open_descendant_tree = None
        self._set_open_tree_zoom = None
        self._frame_open_descendant_top = None
        self._fit_open_tree = None
        # Automation hooks set while a relationship-graph window is open (see
        # PathGraphMixin._show_path_graph); used by the App Store screenshot
        # generator to fit the whole graph into the captured window.
        self._set_open_graph_zoom = None
        self._fit_open_graph = None

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
            log_exception("removing legacy pickle cache files")
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

        # On Windows the per-window DPI scaling may settle just after the first
        # font pass, and can change when the window moves between monitors of
        # different scale; re-sync ttk fonts once the window is mapped and on
        # subsequent configure events.  No-op when the factor is unchanged.
        if sys.platform == 'win32':
            self.root.after(0, self._recheck_ttk_scaling)
            self.root.bind('<Configure>', lambda _e: self._recheck_ttk_scaling(),
                           add='+')

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

    def _results_bold_font(self, size):
        """Bold mono font tuple for the results textbox, pre-scaled to match CTk.

        See gedcom_zoom.scaled_tag_font: the 'bold' tag is set directly on the
        inner tk.Text and bypasses CTk's widget scaling, so it must be scaled
        here to match the body at high DPI.
        """
        return scaled_tag_font(
            self.results, self._mono_family, size, weight='bold')

    def _configure_tree_columns(self):
        """Size fixed Treeview columns from the current UI font metrics."""
        heading_font = tkfont.nametofont('TkDefaultFont')
        # heading_font.measure() already reflects the DPI-scaled pixel size, but
        # the literal padding/min-width constants below do not, so scale them.
        scaling = self._ttk_dpi_scaling()

        def _fit_heading(text, sample='', padding=34):
            text_w = max(heading_font.measure(text),
                         heading_font.measure(sample))
            return text_w + round(padding * scaling)

        name_w = max(round(240 * scaling), _fit_heading(COL_NAME, padding=28))
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
        Tooltip(self.search_entry, get_tip_find())
        # Search mode checkboxes
        self._fuzzy_chk = ctk.CTkCheckBox(
            search_frame, text=CHK_FUZZY,
            variable=self.fuzzy_search, width=0,
        )
        self._fuzzy_chk.pack(side='left', padx=(8, 0))
        Tooltip(self._fuzzy_chk, get_tip_fuzzy())
        self._married_chk = ctk.CTkCheckBox(
            search_frame, text=CHK_MARRIED_NAMES,
            variable=self.married_name_search, width=0,
        )
        self._married_chk.pack(side='left', padx=(8, 0))
        Tooltip(self._married_chk, get_tip_married_names())

        # Filter: box
        filter_frame = ctk.CTkFrame(left, fg_color='transparent')
        filter_frame.pack(fill='x', pady=(2, 0))
        ctk.CTkLabel(filter_frame, text=LBL_FILTER).pack(
            side='left', padx=(0, 4))
        self.filter_entry = ctk.CTkEntry(
            filter_frame, textvariable=self.filter_text)
        self.filter_entry.pack(side='left', fill='x', expand=True)
        self.filter_entry.bind('<Return>', lambda *_: self._kb_focus_list())
        Tooltip(self.filter_entry, get_tip_filter())
        self._flagged_chk = ctk.CTkCheckBox(
            filter_frame, text=CHK_DNA_FLAGGED_ONLY,
            variable=self.show_flagged_only, width=0,
        )
        self._flagged_chk.pack(side='left', padx=(8, 0))
        Tooltip(self._flagged_chk, get_tip_dna_flagged_only())

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

        self.tree.bind('<<TreeviewSelect>>', self._on_tree_selection_change)
        self.tree.bind('<Double-1>', lambda *_: self._refresh_display_pane())
        self.tree.bind('<Return>', lambda *_: self._refresh_display_pane())
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
        Tooltip(self.set_home_btn, get_tip_set_home())

        # --- Right pane ---
        right = ctk.CTkFrame(paned, fg_color='transparent')

        def _action_min_w():
            # padx totals per grid() call: spinbox1=14, spinbox2=2,
            # set_home=6
            return (
                _top_n_label.winfo_reqwidth()
                + self.top_n_spin.winfo_reqwidth() + 14
                + _max_depth_label.winfo_reqwidth()
                + self.max_depth_spin.winfo_reqwidth() + 2
                + self.set_home_btn.winfo_reqwidth() + 6
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
        self._display_mode_labels = {
            'profile': DISPLAY_MODE_PROFILE,
            'matches': DISPLAY_MODE_MATCHES,
            'paths': DISPLAY_MODE_PATHS,
        }
        self._display_mode_tooltips = {
            'profile': get_tip_show_person(),
            'matches': get_tip_find_matches(),
            'paths': get_tip_find_path(),
        }
        self._display_mode_by_label = {
            label: mode for mode, label in self._display_mode_labels.items()
        }
        mode_values = [
            self._display_mode_labels['profile'],
            self._display_mode_labels['matches'],
            self._display_mode_labels['paths'],
        ]
        display_mode_frame = ctk.CTkFrame(results_header, fg_color='transparent')
        display_mode_frame.pack(side='right', padx=(8, 0))
        if hasattr(ctk, 'CTkSegmentedButton'):
            self._display_mode_selector = ctk.CTkSegmentedButton(
                display_mode_frame,
                values=mode_values,
                command=self._on_display_mode_selected,
            )
            self._display_mode_selector.pack(side='left')
            self._display_mode_selector.set(
                self._display_mode_labels[self.display_mode.get()])
            def _on_paths_btn_release(*_):
                if (self.display_mode.get() == 'paths'
                        and not self._path_prompt_cancelled_recently()
                        and not getattr(self, '_picker_open', False)):
                    self._find_path()
            for mode, label in self._display_mode_labels.items():
                button = self._display_mode_selector._buttons_dict.get(label)
                if button is not None:
                    Tooltip(button, self._display_mode_tooltips[mode])
                    if mode == 'paths':
                        for w in [button] + list(button.winfo_children()):
                            w.bind('<ButtonRelease-1>', _on_paths_btn_release, add='+')
        else:
            self._display_mode_selector = ctk.CTkFrame(
                display_mode_frame, fg_color='transparent')
            self._display_mode_selector.pack(side='left')
            self._display_mode_radio_var = tk.StringVar(
                value=self._display_mode_labels[self.display_mode.get()])
            for mode, value in self._display_mode_labels.items():
                radio = ctk.CTkRadioButton(
                    self._display_mode_selector,
                    text=value,
                    variable=self._display_mode_radio_var,
                    value=value,
                    command=lambda v=value: self._on_display_mode_selected(v),
                )
                radio.pack(side='left', padx=(0, 6))
                Tooltip(radio, self._display_mode_tooltips[mode])
        self.show_tree_btn = ctk.CTkButton(
            display_mode_frame,
            text=BTN_SHOW_PERSON_TREE,
            width=64,
            command=lambda: self._show_person(initial_view='tree'),
        )
        self.show_tree_btn.pack(side='left', padx=(8, 0))
        Tooltip(self.show_tree_btn, get_tip_show_person_tree())
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
            '<Button-1>', self._show_results_header_menu)
        self._results_header_label.bind(
            '<Button-3>', self._show_results_header_menu)
        self._results_header_label.bind(
            '<Control-Button-1>', self._show_results_header_menu)

        # Profile sub-mode selector (Bio / Pedigree / Descendants)
        _profile_sub_mode_labels = {
            'bio': PROFILE_SUBMODE_BIO,
            'pedigree': PROFILE_SUBMODE_PEDIGREE,
            'descendants': PROFILE_SUBMODE_DESCENDANTS,
        }
        _profile_sub_mode_tooltips = {
            'bio': get_tip_profile_bio(),
            'pedigree': get_tip_profile_pedigree(),
            'descendants': get_tip_profile_descendants(),
        }
        self._profile_sub_mode_labels = _profile_sub_mode_labels
        self._profile_sub_mode_by_label = {
            label: mode for mode, label in _profile_sub_mode_labels.items()
        }
        self._profile_sub_mode_frame = ctk.CTkFrame(right, fg_color='transparent')
        self._profile_sub_mode_frame.pack(fill='x', padx=8, pady=(2, 0))
        if hasattr(ctk, 'CTkSegmentedButton'):
            self._profile_sub_mode_selector = ctk.CTkSegmentedButton(
                self._profile_sub_mode_frame,
                values=[
                    _profile_sub_mode_labels['bio'],
                    _profile_sub_mode_labels['pedigree'],
                    _profile_sub_mode_labels['descendants'],
                ],
                command=self._on_profile_sub_mode_selected,
            )
            self._profile_sub_mode_selector.pack(side='right')
            self._profile_sub_mode_selector.set(_profile_sub_mode_labels['bio'])
            for _sub, _label in _profile_sub_mode_labels.items():
                _btn = self._profile_sub_mode_selector._buttons_dict.get(_label)
                if _btn is not None:
                    Tooltip(_btn, _profile_sub_mode_tooltips[_sub])
        else:
            self._profile_sub_mode_selector = ctk.CTkFrame(
                self._profile_sub_mode_frame, fg_color='transparent')
            self._profile_sub_mode_selector.pack(side='right')
            _profile_radio_var = tk.StringVar(value=_profile_sub_mode_labels['bio'])
            self._profile_sub_mode_radio_var = _profile_radio_var
            for _mode, _label in _profile_sub_mode_labels.items():
                _radio = ctk.CTkRadioButton(
                    self._profile_sub_mode_selector,
                    text=_label,
                    variable=_profile_radio_var,
                    value=_label,
                    command=lambda v=_label: self._on_profile_sub_mode_selected(v),
                )
                _radio.pack(side='left', padx=(0, 6))
                Tooltip(_radio, _profile_sub_mode_tooltips[_mode])
        if self.display_mode.get() != 'profile':
            self._profile_sub_mode_frame.pack_forget()

        self.results = ctk.CTkTextbox(
            right,
            font=(self._mono_family, self._mono_size),
            wrap='word', height=10, width=self.RESULTS_PREFERRED_WIDTH,
            activate_scrollbars=True,
        )
        self.results.pack(fill='both', expand=True, pady=(4, 0))
        self.results._textbox.tag_configure(
            'bold', font=self._results_bold_font(self._mono_size))
        self.results.configure(state='disabled')

        def _apply_results_zoom(size):
            self.results.configure(font=(self._mono_family, size))
            self.results._textbox.tag_configure(
                'bold', font=self._results_bold_font(size))

        self._results_zoom = TextZoomController(
            self.results, self._mono_size, _apply_results_zoom)

        # Display Pane footer
        status_bar = ctk.CTkFrame(right, border_width=1)
        status_bar.pack(fill='x', pady=(8, 0))
        status_bar.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            status_bar, textvariable=self.status_text, anchor='w',
        ).grid(row=0, column=0, sticky='ew', padx=(8, 0), pady=4)

        self._matches_settings_frame = ctk.CTkFrame(
            status_bar, fg_color='transparent')
        self._matches_settings_frame.grid(
            row=0, column=1, sticky='e', padx=(6, 4), pady=4)
        tag_keyword_label = ctk.CTkLabel(
            self._matches_settings_frame, text=LBL_TAG_KEYWORD)
        tag_keyword_label.grid(row=0, column=0, sticky='w', padx=(0, 4))
        tag_keyword_entry = ctk.CTkEntry(
            self._matches_settings_frame,
            textvariable=self.tag_keyword,
            width=110,
        )
        tag_keyword_entry.grid(row=0, column=1, padx=(0, 10))
        page_marker_label = ctk.CTkLabel(
            self._matches_settings_frame, text=LBL_PAGE_MARKER)
        page_marker_label.grid(row=0, column=2, sticky='w', padx=(0, 4))
        page_marker_entry = ctk.CTkEntry(
            self._matches_settings_frame,
            textvariable=self.page_marker,
            width=170,
        )
        page_marker_entry.grid(row=0, column=3, padx=(0, 10))
        select_tag_btn = ctk.CTkButton(
            self._matches_settings_frame,
            text=BTN_SELECT_TAG,
            width=92,
            command=self._view_tags,
        )
        select_tag_btn.grid(row=0, column=4)
        Tooltip(tag_keyword_label, TIP_TAG_KEYWORD)
        Tooltip(tag_keyword_entry, TIP_TAG_KEYWORD)
        Tooltip(page_marker_label, TIP_PAGE_MARKER)
        Tooltip(page_marker_entry, TIP_PAGE_MARKER)
        Tooltip(select_tag_btn, get_tip_select_tag())
        self._set_matches_settings_visible(self.display_mode.get() == 'matches')

        self._reverse_btn = ctk.CTkButton(status_bar, text=BTN_REVERSE, width=110,
                                          command=self._reverse_results, state='disabled')
        self._reverse_btn.grid(row=0, column=2, padx=(4, 4), pady=4)
        self._set_reverse_button_visible(self.display_mode.get() == 'paths')
        Tooltip(self._reverse_btn, get_tip_reverse())
        self._save_btn = ctk.CTkButton(status_bar, text=BTN_SAVE, width=80,
                                       command=self._save_results)
        self._save_btn.grid(row=0, column=3, padx=(4, 4), pady=4)
        Tooltip(self._save_btn, get_tip_save())
        self._copy_btn = ctk.CTkButton(status_bar, text=BTN_COPY, width=80,
                                       command=self._copy_results)
        self._copy_btn.grid(row=0, column=4, padx=(4, 4), pady=4)
        Tooltip(self._copy_btn, get_tip_copy())
        self._profile_gallery_btn = ctk.CTkButton(
            status_bar, text=BTN_PROFILE_GALLERY, width=90,
            command=self._show_current_profile_gallery)
        self._profile_gallery_btn.grid(row=0, column=5, padx=(4, 8), pady=4)
        self._profile_gallery_btn.grid_remove()
        Tooltip(self._profile_gallery_btn, get_tip_profile_gallery())
        if debug_enabled():
            self._copy_json_btn = ctk.CTkButton(
                status_bar, text='Copy JSON', width=90,
                command=self._copy_paths_json)
            Tooltip(self._copy_json_btn, get_tip_copy_json())
            self._copy_json_btn.grid(row=0, column=6, padx=(0, 8), pady=4)
        self._progress_bar = ctk.CTkProgressBar(status_bar, width=130)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=3, columnspan=2, padx=(4, 8), pady=4)
        self._progress_bar.grid_remove()

        self._setup_keybindings()
        self.root.after_idle(lambda: self._refresh_display_pane(prompt_for_path=False))

def _patch_ctk_scaling_for_tkinter_dpi():
    """Patch CTk's per-window DPI detection to use GetDpiForWindow().

    Windows presents two distinct DPI failure modes, and GetDpiForWindow()
    is the one API that resolves both because it honours the process's DPI
    awareness context:

    * DPI-virtualised (unaware) process — e.g. some 175% setups.  The OS
      presents a 96-DPI logical coordinate space to tkinter and silently
      stretches the rendered bitmap to physical size (1.75×).  CTk's own
      detection uses GetDpiForMonitor(), which ignores awareness and returns
      the real DPI (168), so CTk scales by 1.75× ON TOP of the OS stretch —
      net ~3×, widgets huge, windows overflow.  For an unaware process
      GetDpiForWindow() returns 96, so this patch yields scale 1.0 and lets
      the OS handle the physical stretch.

    * DPI-aware process at high scale — e.g. 300%.  The OS does NOT stretch;
      Tk paints onto a physical-pixel surface.  But winfo_fpixels('1i') still
      reports 96 here (confirmed on a 300% machine: GetDpiForWindow=288 yet
      winfo_fpixels=96), so scaling off winfo_fpixels leaves CTk at 1.0 and
      every font renders ~1/scale too small.  GetDpiForWindow() returns the
      true 288, so this patch yields scale 3.0 and fonts match the surface.

    winfo_fpixels('1i') is kept only as a fallback for Windows older than
    1607 (where GetDpiForWindow is unavailable).

    Must be called BEFORE ctk.CTk() so that the patch is in place when CTk
    registers the root window with ScalingTracker.add_window().
    """
    try:
        original = ctk.ScalingTracker.__dict__.get('get_window_dpi_scaling')
        if original is None:
            return   # not present in this CTk build — leave it alone

        orig_fn = original.__func__   # unwrap classmethod descriptor

        def _os_window_dpi(window) -> float:
            """Real render DPI honouring the process awareness context."""
            import ctypes  # pylint: disable=import-outside-toplevel
            hwnd = window.winfo_id()
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            if not dpi:
                raise OSError("GetDpiForWindow returned 0")
            return float(dpi)

        @classmethod
        def _winfo_consistent_scaling(cls, window) -> float:
            # Prefer GetDpiForWindow (awareness-correct on both virtualised and
            # DPI-aware processes); fall back to winfo_fpixels on old Windows.
            for source in (_os_window_dpi, lambda w: w.winfo_fpixels('1i')):
                try:
                    dpi = source(window)
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
                if dpi:
                    return round(max(0.75, min(4.0, dpi / 96.0)), 2)
            try:
                return float(orig_fn(cls, window))
            except Exception:  # pylint: disable=broad-exception-caught
                log_exception("falling back from original CTk DPI scaling")
                return 1.0

        ctk.ScalingTracker.get_window_dpi_scaling = _winfo_consistent_scaling
    except Exception:  # pylint: disable=broad-exception-caught
        log_exception("patching CTk DPI scaling")
        pass


def _print_dpi_diagnostics(root):
    """Print DPI, scaling, and font diagnostics to stderr."""
    import tkinter.font as _tkf
    lines = ['=== DPI/Scaling Diagnostics ===']

    try:
        dpi_fpix = root.winfo_fpixels('1i')
        lines.append(f'  winfo_fpixels("1i"):    {dpi_fpix:.2f}'
                     '  (96=100%, 120=125%, 144=150%, 192=200%)')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: winfo_fpixels")
        lines.append(f'  winfo_fpixels:          ERROR {e}')

    if sys.platform == 'win32':
        try:
            import ctypes
            lines.append(f'  GetDpiForSystem():      {ctypes.windll.user32.GetDpiForSystem()}')
        except Exception as e:  # pylint: disable=broad-exception-caught
            log_exception("printing DPI diagnostic: GetDpiForSystem")
            lines.append(f'  GetDpiForSystem():      ERROR {e}')
        try:
            import ctypes
            lines.append(f'  GetDpiForWindow(root):  {ctypes.windll.user32.GetDpiForWindow(root.winfo_id())}')
        except Exception as e:  # pylint: disable=broad-exception-caught
            log_exception("printing DPI diagnostic: GetDpiForWindow")
            lines.append(f'  GetDpiForWindow():      ERROR {e}')

    try:
        lines.append(f'  CTk widget scaling:     {ctk.ScalingTracker.get_widget_scaling(root)}')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: CTk widget scaling")
        lines.append(f'  CTk widget scaling:     ERROR {e}')
    try:
        lines.append(f'  CTk window scaling:     {ctk.ScalingTracker.get_window_scaling(root)}')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: CTk window scaling")
        lines.append(f'  CTk window scaling:     ERROR {e}')

    try:
        lines.append(f'  Screen (winfo):         {root.winfo_screenwidth()}x{root.winfo_screenheight()}')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: screen size")
        lines.append(f'  Screen:                 ERROR {e}')

    try:
        df = _tkf.nametofont('TkDefaultFont')
        lines.append(f'  TkDefaultFont:          size={df.cget("size")} (cget)  actual={df.actual("size")}')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: TkDefaultFont")
        lines.append(f'  TkDefaultFont:          ERROR {e}')

    try:
        cf = ctk.CTkFont()
        lines.append(f'  CTkFont (default):      family={cf.cget("family")!r}'
                     f'  size={cf.cget("size")} (cget)  actual={cf.actual("size")}')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: CTkFont")
        lines.append(f'  CTkFont:                ERROR {e}')

    try:
        lines.append(f'  CTk theme CTkFont:      {ctk.ThemeManager.theme.get("CTkFont", "N/A")}')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log_exception("printing DPI diagnostic: CTk theme font")
        lines.append(f'  CTk theme CTkFont:      ERROR {e}')

    lines.append('================================')
    print('\n'.join(lines), file=sys.stderr, flush=True)


def main():
    """Parse command-line options, create the GUI, and start the event loop."""
    parser = argparse.ArgumentParser(
        description='GEDCOM Navigator GUI. '
                    'Optionally pass a GEDCOM file path to load it on startup.'
    )
    parser.add_argument(
        'gedcom', nargs='?', default=None,
        help='Optional path to a .ged file to load automatically on startup.'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug diagnostics, including exception logging, and print '
             'DPI/scaling diagnostics to stderr.'
    )
    parser.add_argument(
        '--self-test', action='store_true',
        help='Run headless runtime self-checks (native imports, canvas->PNG, '
             'pasteboard) and exit non-zero on failure. Used by the build/CI '
             'pipeline to catch sandbox-only breakage.'
    )
    args = parser.parse_args()

    if args.self_test:
        from gedcom_selftest import run_self_test
        sys.exit(run_self_test())

    if args.debug:
        set_debug_enabled(True)
    if debug_enabled():
        configure_debug_logging()
        install_exception_hooks()

    # Patch CTk's per-window DPI detection BEFORE creating any window.
    # On some Windows environments the process is DPI-virtualised: tkinter
    # sees 96 DPI but CTk's GetDpiForWindow() returns the real DPI, causing
    # double-scaling.  The patch makes CTk use winfo_fpixels() instead, which
    # is always consistent with tkinter's coordinate space.
    # See _patch_ctk_scaling_for_tkinter_dpi() for the full explanation.
    if sys.platform == 'win32':
        _patch_ctk_scaling_for_tkinter_dpi()

    root = ctk.CTk()

    # Now that i18n is set up, we can safely import strings.
    # Note: We must import * here to make them available in the main scope
    # for existing code that expects them.
    from gedcom_strings import (
        APP_TITLE, ERR_FILE_NOT_FOUND_TITLE, ERR_GEDCOM_NOT_FOUND_MSG
    )

    if args.debug:
        _print_dpi_diagnostics(root)
    if debug_enabled():
        install_exception_hooks(root)

    # On macOS the window briefly appears at the default top-left position
    # before _fit_window_to_content centres it, so withdraw it first.
    # On Windows withdraw()/deiconify() causes the window to vanish; the
    # flash doesn't occur there, so skip it.
    if sys.platform == 'darwin':
        root.withdraw()
    app = GedcomNavigatorApp(root)
    app._debug = debug_enabled()
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
    # Register as a .ged handler and (once per version) offer to be the default.
    # Deferred so the main window paints first and any opened file loads first.
    root.after(600, app._maybe_init_file_association)

    # Show the welcome/walkthrough on a new version, then prompt to open a file
    # if none is loaded.  Routed through onboarding so the open dialog always
    # comes after the welcome window rather than before it.  _after_onboarding
    # is a no-op when a file is already loaded (e.g. a CLI path or recent file).
    root.after(700, app._start_onboarding)

    root.mainloop()


if __name__ == '__main__':
    main()
