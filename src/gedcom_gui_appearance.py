"""
gedcom_gui_appearance.py

AppearanceMixin — history/config, font, theme, keybindings, and menu methods
for GedcomNavigatorApp.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import sys
import customtkinter as ctk
from gedcom_strings import *  # noqa: F401,F403 # pylint: disable=unused-wildcard-import
from gedcom_theme import (
    CTK_THEME_MAP, ttk_colors, get_flag_bg, get_link_color,
)

# Tkinter modifier key name: Command on macOS, Control on Windows/Linux.
_MOD_KEY = 'Command' if sys.platform == 'darwin' else 'Control'

# Background tints injected into ThemeManager for the named Blue/Green themes.
# Each value is [light_color, dark_color]; only the mode-appropriate one shows.
_BG_TINTS = {
    'Blue': {
        'tooltip_bg_color':     ['#3C9FD0', '#3C9FD0'],
        'tooltip_text_color':     ['#EEEEEE', '#EEEEEE'],
        'CTk':         ['#EBF0FA', '#1A2535'],
        'CTkToplevel': ['#EBF0FA', '#1A2535'],
        'CTkFrame':    {'fg_color':     ['#E3EAF5', '#1F2D3D'],
                        'top_fg_color': ['#D8E1F0', '#243447'],
                        'border_color': ['#B9C7DF', '#324760']},
    },
    'Green': {
        'tooltip_bg_color':     ['#aaeeaa', '#aaeeaa'],
        'tooltip_text_color':     ['#333333', '#333333'],
        'CTk':         ['#EBF5EB', '#1D2B1D'],
        'CTkToplevel': ['#EBF5EB', '#1D2B1D'],
        'CTkFrame':    {'fg_color':     ['#E1EDE1', '#223122'],
                        'top_fg_color': ['#D5E6D5', '#263826'],
                        'border_color': ['#B8D2B8', '#344E34']},
    },
}


class AppearanceMixin:
    """Mixin providing appearance, history, keybinding, and menu methods."""

    @staticmethod
    def _raise_window(win):
        """Bring win to the front and give it keyboard focus.

        On Windows, briefly sets -topmost to overcome the OS restriction that
        prevents background windows from stealing focus via lift() alone.
        A second attempt is scheduled after 150 ms so that windows that are
        not yet fully rendered at the time of the first call still reliably
        come to the foreground.
        """
        win.deiconify()
        if sys.platform == 'win32':
            win.attributes('-topmost', True)
        win.lift()
        win.focus_force()

        def _retry_and_clear():
            try:
                if not win.winfo_exists():
                    return
                win.lift()
                win.focus_force()
                if sys.platform == 'win32':
                    def _clear():
                        try:
                            win.attributes('-topmost', False)
                        except tk.TclError:
                            pass
                    win.after(100, _clear)
            except tk.TclError:
                pass

        win.after(150, _retry_and_clear)

    # ---------------------------------------------------------- History / config
    def _cache_dir(self):
        """Return the directory used for GEDCOM parse caches."""
        return self._config._path.parent / 'cache'

    def _load_history(self):
        """Load the recently opened GEDCOM file list."""
        return self._config.get_recent_files()

    def _save_history(self, history):
        """Persist the recently opened GEDCOM file list."""
        self._config.set_recent_files(history)

    def _add_to_history(self, filepath):
        """Add filepath to the recent-file list and refresh the Open Recent menu."""
        history = [filepath] + [p for p in self._recent_files if p != filepath]
        history = history[:self.MAX_RECENT]
        self._recent_files = history
        self._config.set_recent_files(history)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        """Repopulate the Open Recent submenu from the five most recent files."""
        menu = self._recent_menu
        menu.delete(0, 'end')
        recents = self._recent_files[:5]
        if not recents:
            menu.add_command(label=MENU_NO_RECENT_FILES, state='disabled')
            return
        for path in recents:
            label = path if len(path) <= 60 else '…' + path[-57:]
            menu.add_command(
                label=label,
                command=lambda p=path: (
                    self.gedcom_path.set(p), self._load_file()),
            )

    def _clear_cache(self):
        """Confirm and remove cached GEDCOM parse files."""
        cache_dir = self._cache_dir()
        files = list(cache_dir.glob('*.json')) if cache_dir.exists() else []
        if not files:
            messagebox.showinfo(CACHE_EMPTY_TITLE, CACHE_EMPTY_MSG)
            return
        if messagebox.askyesno(
            CACHE_CLEAR_TITLE,
            CACHE_CLEAR_MSG.format(count=len(files)),
        ):
            deleted = self._model.clear_cache(cache_dir)
            messagebox.showinfo(
                CACHE_DONE_TITLE, CACHE_DONE_MSG.format(deleted=deleted))

    def _load_home_person(self, gedcom_path):
        """Load the saved home person ID for gedcom_path."""
        return self._config.get_home_person(gedcom_path)

    def _save_home_person(self, gedcom_path, indi_id):
        """Persist the home person ID for gedcom_path."""
        self._config.set_home_person(gedcom_path, indi_id)

    def _load_font_preference(self):
        """Load the saved UI font-size preference."""
        return self._config.get_font_preference(self._FONT_SIZES)

    def _save_font_preference(self, size_name):
        """Persist the UI font-size preference."""
        self._config.set_font_preference(size_name)

    def _update_header_label_style(self):
        """Apply or clear accent styling on the results header label."""
        if not (hasattr(self, '_results_header_label') and
                hasattr(self, '_results_header_var')):
            return
        if self._results_header_var.get():
            is_dark = ctk.get_appearance_mode() == 'Dark'
            tc = ttk_colors(is_dark, self._theme_pref)
            self._results_header_label.configure(
                fg_color=tc['select_bg'],
                text_color=tc['select_fg'],
            )
        else:
            self._results_header_label.configure(fg_color='transparent')

    def _apply_font_size(self, size_name):
        """Apply a named font-size preset to CTk, monospace, and ttk fonts."""
        sizes = self._FONT_SIZES[size_name]
        mono_sz = sizes['mono']
        ui_sz = sizes['ui']
        self._mono_size = mono_sz
        self._mono_font.configure(size=mono_sz)
        self._mono_font_bold.configure(size=mono_sz)

        for fname in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkSmallCaptionFont'):
            try:
                # CTkFont stores sizes as negative pixels (size=-abs(px)).  On
                # Windows with DPI virtualisation, Tk point sizes diverge from
                # CTkFont pixel sizes, making mixed dialogs inconsistent.  Use
                # the same negative-pixel convention so named fonts stay in sync.
                sz = -ui_sz if sys.platform == 'win32' else ui_sz
                tkfont.nametofont(fname).configure(size=sz)
            except tk.TclError:
                pass

        # Update the CTk theme default so that CTkFont() instances created later
        # (e.g. when a dialog is re-opened) inherit the new size.
        try:
            ctk.ThemeManager.theme["CTkFont"]["size"] = ui_sz
        except Exception:  # pylint: disable=broad-except
            pass

        # Walk the live widget tree and update every existing CTkFont so that
        # open windows update immediately.  The results-header override below
        # runs after this and stamps mono_sz onto that specific font.
        def _update_ctk_fonts(w):
            for child in w.winfo_children():
                try:
                    fnt = getattr(child, '_font', None)
                    if isinstance(fnt, ctk.CTkFont):
                        fnt.configure(size=ui_sz)
                except Exception:  # pylint: disable=broad-except
                    pass
                _update_ctk_fonts(child)

        try:
            _update_ctk_fonts(self.root)
        except Exception:  # pylint: disable=broad-except
            pass

        self._apply_styles()

        if hasattr(self, 'tree'):
            self._configure_tree_columns()

        if hasattr(self, 'results'):
            # CTkTextbox fonts are passed as tuples; update on size change.
            if hasattr(self, '_results_zoom'):
                self._results_zoom.set_base_size(mono_sz)
            else:
                self.results.configure(font=(self._mono_family, mono_sz))
                self.results._textbox.tag_configure(
                    'bold', font=(self._mono_family, mono_sz, 'bold'))
            if hasattr(self, '_results_header_label'):
                self._results_header_label.configure(
                    font=ctk.CTkFont(size=mono_sz, weight='bold'))
            self.root.after(0, self._refit_windows)

    def _fit_window_to_content(
        self,
        win,
        *,
        min_w=400,
        min_h=300,
        preferred_w=None,
        preferred_h=None,
        max_screen_ratio=0.9,
        center_on_root=True,
        preserve_position=False,
    ):
        """Size a window from requested content, clamped to the visible screen."""
        win.update_idletasks()
        self.root.update_idletasks()

        req_w = win.winfo_reqwidth()
        req_h = win.winfo_reqheight()
        target_w = max(req_w, preferred_w or 0, min_w)
        target_h = max(req_h, preferred_h or 0, min_h)

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        margin = 32
        max_w = max(min_w, min(
            int(screen_w * max_screen_ratio), screen_w - margin))
        max_h = max(min_h, min(
            int(screen_h * max_screen_ratio), screen_h - margin))
        w = min(target_w, max_w)
        h = min(target_h, max_h)

        win.minsize(min(min_w, max_w), min(min_h, max_h))

        if preserve_position:
            x = win.winfo_x()
            y = win.winfo_y()
        elif center_on_root and win is not self.root:
            root_x = self.root.winfo_x()
            root_y = self.root.winfo_y()
            root_w = self.root.winfo_width()
            root_h = self.root.winfo_height()
            x = root_x + (root_w - w) // 2
            y = root_y + (root_h - h) // 2
        else:
            x = (screen_w - w) // 2
            y = (screen_h - h) // 2

        x = max(0, min(x, screen_w - w))
        y = max(0, min(y, screen_h - h))
        win.geometry(f"{w}x{h}+{x}+{y}")

        if getattr(self, '_debug', False):
            import sys as _sys
            print(
                f'[debug] fit_window {win.title()!r}: '
                f'req={req_w}x{req_h}  preferred={preferred_w}x{preferred_h}  '
                f'min={min_w}x{min_h}  screen={screen_w}x{screen_h}  '
                f'max={max_w}x{max_h}  -> {w}x{h}',
                file=_sys.stderr, flush=True,
            )

        return w, h

    def _refit_windows(self):
        """Grow open windows as needed to fit the current font metrics."""
        if hasattr(self, '_refresh_main_pane_layout'):
            self._refresh_main_pane_layout()
        self._fit_window_to_content(
            self.root,
            min_w=1000,
            min_h=500,
            preferred_w=self.root.winfo_width(),
            preferred_h=self.root.winfo_height(),
            max_screen_ratio=0.92,
            center_on_root=False,
            preserve_position=True,
        )
        for win in self.root.winfo_children():
            if not isinstance(win, tk.Toplevel):
                continue
            try:
                if win.overrideredirect():
                    continue
            except tk.TclError:
                pass
            try:
                self._fit_window_to_content(
                    win,
                    preferred_w=win.winfo_width(),
                    preferred_h=win.winfo_height(),
                    preserve_position=True,
                )
            except tk.TclError:
                pass

    def _apply_styles(self):
        """Apply ttk styles for Treeview / Spinbox / PanedWindow to match the CTk theme."""
        style = ttk.Style()
        is_dark = ctk.get_appearance_mode() == 'Dark'
        t = ttk_colors(is_dark, getattr(self, '_theme_pref', None))

        try:
            style.theme_use('aqua' if sys.platform == 'darwin' else 'clam')
        except tk.TclError:
            pass

        bg, fg = t['bg'], t['fg']
        field_bg = t['field_bg']
        sel_bg, sel_fg = t['select_bg'], t['select_fg']
        hbg = t['heading_bg']
        tr = t['trough']

        # Setting font on the root ttk style ensures all ttk widgets (Spinbox,
        # Radiobutton, etc.) use TkDefaultFont, which _apply_font_size keeps in
        # sync with the user's font-size preference.  Without this, ttk widgets
        # fall through to the native system font (typically 9pt on Windows) and
        # appear smaller than CTk widgets in the same dialog.
        style.configure('.', background=bg, foreground=fg, font='TkDefaultFont')
        style.configure('TFrame', background=bg)
        style.configure('TLabelframe', background=bg, foreground=fg)
        style.configure('TLabelframe.Label', background=bg, foreground=fg)
        style.configure('TLabel', background=bg, foreground=fg)
        style.configure('TButton', background=sel_bg, foreground=sel_fg)
        style.map('TButton',
                  background=[('active', sel_bg), ('pressed', sel_bg)],
                  foreground=[('active', sel_fg), ('pressed', sel_fg)])
        style.configure('TEntry', fieldbackground=field_bg, foreground=fg,
                        selectbackground=sel_bg, selectforeground=sel_fg)
        style.configure('TCombobox', fieldbackground=field_bg, foreground=fg,
                        selectbackground=sel_bg, selectforeground=sel_fg,
                        background=bg, arrowcolor=fg)
        style.map('TCombobox',
                  fieldbackground=[('readonly', field_bg)],
                  selectbackground=[('readonly', sel_bg)],
                  foreground=[('readonly', fg)])
        style.configure('TSpinbox', fieldbackground=field_bg, foreground=fg,
                        background=bg, arrowcolor=fg,
                        selectbackground=sel_bg, selectforeground=sel_fg)
        style.configure('TCheckbutton', background=bg, foreground=fg)
        style.map('TCheckbutton', background=[('active', bg)])
        style.configure('TRadiobutton', background=bg, foreground=fg)
        style.map('TRadiobutton', background=[('active', bg)])
        style.configure('TScrollbar', background=bg, troughcolor=tr,
                        arrowcolor=fg, bordercolor=bg,
                        darkcolor=bg, lightcolor=bg)
        style.configure('TPanedwindow', background=bg)
        if hasattr(self, '_paned'):
            try:
                self._paned.configure(background=bg)
            except tk.TclError:
                pass
        style.configure('Treeview', background=field_bg, foreground=fg,
                        fieldbackground=field_bg)
        style.configure('Treeview.Heading', background=hbg, foreground=fg)
        style.map('Treeview',
                  background=[('selected', sel_bg)],
                  foreground=[('selected', sel_fg)])

        row_h = tkfont.nametofont('TkDefaultFont').metrics('linespace') + 6
        style.configure('Treeview', font='TkDefaultFont', rowheight=row_h)
        style.configure('Treeview.Heading', font='TkDefaultFont')

        if sys.platform == 'darwin':
            # The aqua theme's Treeview.Heading.cell is a native macOS element
            # that ignores padding. Override the layout to drop that element so
            # the standard border/padding elements (which respect padding) are
            # used instead, giving the heading more breathing room on macOS.
            try:
                style.layout('Treeview.Heading', [
                    ('Treeview.Heading.border', {'sticky': 'nswe', 'children': [
                        ('Treeview.Heading.padding', {'sticky': 'nswe', 'children': [
                            ('Treeview.Heading.image', {
                             'side': 'right', 'sticky': ''}),
                            ('Treeview.Heading.text', {'sticky': 'we'}),
                        ]}),
                    ]}),
                ])
                style.configure('Treeview.Heading',
                                padding=(8, 8), relief='raised')
            except tk.TclError:
                pass

    def _apply_window_background(self, win):
        """Apply the current CTk root/toplevel background to an existing window."""
        widget_key = 'CTkToplevel' if isinstance(
            win, ctk.CTkToplevel) else 'CTk'
        fg_color = ctk.ThemeManager.theme.get(widget_key, {}).get('fg_color')
        if fg_color is None:
            return
        try:
            win.configure(fg_color=fg_color)
        except (tk.TclError, ValueError):
            pass

    def _inject_theme_backgrounds(self, theme_name):
        """Overwrite ThemeManager background colors for Blue/Green named themes."""
        tint = _BG_TINTS.get(theme_name)
        if tint is None:
            return
        theme = ctk.ThemeManager.theme
        theme['CTkToplevel']['tooltip_bg_color'] = tint.get(
            'tooltip_bg_color', "#EEEEEE")
        theme['CTkToplevel']['tooltip_text_color'] = tint.get(
            'tooltip_text_color', "#222222")
        for widget, value in tint.items():
            if widget not in theme:
                continue
            if isinstance(value, dict):
                for prop, colors in value.items():
                    theme[widget][prop] = colors
            else:
                theme[widget]['fg_color'] = value

    def _apply_theme(self, theme_name):
        """Apply a named color theme to the application."""
        old_color_theme = CTK_THEME_MAP.get(
            self._theme_pref, ('system', 'blue'))[1]
        old_tinted = self._theme_pref in _BG_TINTS
        self._theme_pref = theme_name
        mode, color_theme = CTK_THEME_MAP.get(theme_name, ('system', 'blue'))
        ctk.set_default_color_theme(color_theme)
        # set_default_color_theme reloads the theme JSON, resetting
        # CTkFont["size"] back to 13.  Re-stamp our preference so that
        # CTkFont() instances created afterwards use the right size.
        try:
            ui_sz = self._FONT_SIZES.get(
                self._font_size_pref, self._FONT_SIZES['medium'])['ui']
            ctk.ThemeManager.theme["CTkFont"]["size"] = ui_sz
        except Exception:  # pylint: disable=broad-except
            pass
        self._inject_theme_backgrounds(theme_name)
        ctk.set_appearance_mode(mode)
        self._apply_window_background(self.root)
        for win in self.root.winfo_children():
            if not isinstance(win, tk.Toplevel):
                continue
            try:
                if win.overrideredirect():
                    continue
            except tk.TclError:
                pass
            self._apply_window_background(win)
        self._apply_styles()
        is_dark = ctk.get_appearance_mode() == 'Dark'
        self._link_color = get_link_color(is_dark, theme_name)
        if hasattr(self, 'tree'):
            self.tree.tag_configure(
                'flagged_row', background=get_flag_bg(is_dark))
        self._update_header_label_style()
        if not hasattr(self, 'results'):
            return
        # needs_rebuild = color_theme != old_color_theme or old_tinted != (
            # theme_name in _BG_TINTS)
        # if needs_rebuild:
        self.root.after(0, self._rebuild_ui_for_theme)
        # else:
            # self.root.after(0, self._refit_windows)

    def _rebuild_ui_for_theme(self):
        """Destroy and rebuild main-window widgets to apply a new colour theme."""
        # CTkEntry/CTkComboBox register write-traces on their textvariables that
        # survive Tkinter cascade-destroy (Python trace not removed, Tcl widget gone).
        # Clear every trace on the affected vars now; re-add our own below.
        # CTkCheckBox DOES properly remove its own trace in destroy(), so BooleanVars
        # (show_flagged_only, fuzzy_search, married_name_search) must NOT be listed
        # here — pre-removing their traces causes CTkCheckBox.destroy() to raise
        # TclError, which aborts the parent frame's cascade destroy and leaves a zombie
        # Tk widget that causes the main window to appear duplicated.
        _app_traces = [
            (self.search_text,  'write', self._on_search_change),
            (self.filter_text,  'write', self._on_search_change),
            (self.tag_keyword,  'write', self._on_dna_settings_change),
            (self.page_marker,  'write', self._on_dna_settings_change),
        ]
        for var, *_ in _app_traces:
            for mode, idx in list(var.trace_info()):
                try:
                    var.trace_remove(mode, idx)
                except tk.TclError:
                    pass

        for child in list(self.root.winfo_children()):
            if isinstance(child, tk.Toplevel):
                continue
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._build_ui()

        # Re-register application traces (_build_ui already re-added CTk's own traces).
        for var, mode, cb in _app_traces:
            var.trace_add(mode, cb)

        if self.individuals:
            self._populate_tree()
            self._refresh_result()
        self.root.after(0, self._refit_windows)

    def _apply_theme_to_window(self, win):
        """Update flagged-row tag colours in any Treeview inside a new window."""
        self._apply_window_background(win)
        is_dark = ctk.get_appearance_mode() == 'Dark'
        flag_bg = get_flag_bg(is_dark)
        self._update_flagged_rows(win, flag_bg)

    def _update_flagged_rows(self, widget, flag_bg):
        """Recursively update flagged_row tag background in all child Treeviews."""
        for child in widget.winfo_children():
            if isinstance(child, ttk.Treeview):
                child.tag_configure('flagged_row', background=flag_bg)
            try:
                self._update_flagged_rows(child, flag_bg)
            except tk.TclError:
                pass

    def _load_theme_preference(self):
        """Load the saved colour theme preference."""
        pref = self._config.get_theme_preference(self._THEME_NAMES)
        if pref not in self._THEME_NAMES:
            pref = 'System'
        return pref

    def _save_theme_preference(self, theme_name):
        """Persist the selected colour theme preference."""
        self._config.set_theme_preference(theme_name)

    def _load_hide_tooltips_preference(self):
        """Load the saved hide-tooltips preference."""
        return self._config.get_hide_tooltips()

    def _save_hide_tooltips_preference(self, value):
        """Persist the hide-tooltips preference."""
        self._config.set_hide_tooltips(value)

    def _load_show_person_geometry(self):
        """Load the saved geometry for the person detail window."""
        return self._config.get_window_geometry('show_person_geometry')

    def _persist_show_person_geometry(self, win):
        """Persist the current person detail window geometry."""
        try:
            if win.state() == 'zoomed':
                # On Windows, geometry() in zoomed state returns the full-screen
                # dimensions.  Persisting those would cause every subsequent small
                # tree to open at maximum size.  Skip — the pre-zoom geometry
                # already saved from the previous Configure event is correct.
                return
            geo = win.geometry()
            self._show_person_geometry = geo
            self._config.set_window_geometry('show_person_geometry', geo)
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error persisting profile geometry: {e}")

    def _set_home_person(self):
        """Save the selected person as the home person for the active GEDCOM."""
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        indi_id = sel[0] if sel else self._active_id
        if not indi_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        gedcom_path = self.gedcom_path.get().strip()
        if not gedcom_path:
            return
        self._home_person_id = indi_id
        self._save_home_person(gedcom_path, indi_id)
        name = self.individuals[indi_id]['name'] or indi_id
        self.status_text.set(STATUS_HOME_SET.format(name=name))

    # ---------------------------------------------------------- Keybindings
    def _setup_keybindings(self):
        """Register keyboard shortcuts and focus traversal for the main window."""
        def bind(seq, cmd):
            self.root.bind(seq, lambda *_: cmd() or 'break')

        bind('<Command-question>' if sys.platform ==
             'darwin' else '<F1>', self._show_how_to_use)
        bind(f'<{_MOD_KEY}-k>' if sys.platform ==
             'darwin' else '<F2>', self._show_keyboard_shortcuts)
        if sys.platform == 'win32':
            bind('<F3>', self._show_preferences)
        bind(f'<{_MOD_KEY}-f>', self._kb_focus_search)
        bind(f'<{_MOD_KEY}-i>', self._kb_focus_filter)
        bind(f'<{_MOD_KEY}-d>', lambda: self.show_flagged_only.set(
            not self.show_flagged_only.get()))
        bind(f'<{_MOD_KEY}-u>', lambda: self.fuzzy_search.set(
            not self.fuzzy_search.get()))
        bind(f'<{_MOD_KEY}-m>', lambda: self.married_name_search.set(
            not self.married_name_search.get()))
        bind(f'<{_MOD_KEY}-p>', lambda: self._set_display_mode('paths'))
        bind(f'<{_MOD_KEY}-t>', self._view_tags)
        bind(f'<{_MOD_KEY}-o>', self._browse)
        bind(f'<{_MOD_KEY}-h>', self._set_home_person)
        bind(f'<{_MOD_KEY}-e>', lambda: self._set_display_mode('profile'))
        bind(f'<{_MOD_KEY}-s>', self._save_results)
        bind(f'<{_MOD_KEY}-n>', lambda: self._set_display_mode('matches'))
        bind(f'<{_MOD_KEY}-r>', self._reverse_results)
        bind(f'<{_MOD_KEY}-l>', self._clear_results)
        bind('<Escape>', self._clear_results)
        back_seq = '<Command-Left>' if sys.platform == 'darwin' else '<Alt-Left>'
        bind(back_seq, self._navigate_back)
        fwd_seq = '<Command-Right>' if sys.platform == 'darwin' else '<Alt-Right>'
        bind(fwd_seq, self._navigate_forward)
        # Only invoke _copy_results when a Text widget isn't focused
        self.root.bind(f'<{_MOD_KEY}-c>', self._kb_copy)

        # Explicit tab chain via the internal tk widgets for CTk widgets:
        # tree → display mode → results_text → top_n_spin → max_depth_spin →
        # set_home_btn
        results_inner = self.results._textbox
        results_inner.configure(takefocus=True)
        mode_widgets = list(getattr(
            self._display_mode_selector, '_buttons_dict', {}).values())
        if not mode_widgets:
            try:
                mode_widgets = list(self._display_mode_selector.winfo_children())
            except tk.TclError:
                mode_widgets = []
        tab_chain = [
            self.tree, *mode_widgets, results_inner,
            self.top_n_spin, self.max_depth_spin,
            self.set_home_btn,
        ]
        show_tree_btn = getattr(self, 'show_tree_btn', None)
        if show_tree_btn is not None:
            tab_chain.insert(1 + len(mode_widgets), show_tree_btn)
        for i, w in enumerate(tab_chain):
            nxt = tab_chain[(i + 1) % len(tab_chain)]
            prv = tab_chain[(i - 1) % len(tab_chain)]
            try:
                w.bind('<Tab>', lambda *_, nw=nxt: nw.focus_set() or 'break')
                w.bind('<Shift-Tab>', lambda *_, pw=prv: pw.focus_set() or 'break')
            except NotImplementedError:
                continue

        r_inner = self.results._textbox
        r_inner.bind(
            '<Up>', lambda *_: self.results.yview_scroll(-1, 'units') or 'break')
        r_inner.bind(
            '<Down>', lambda *_: self.results.yview_scroll(1, 'units') or 'break')
        r_inner.bind(
            '<Prior>', lambda *_: self.results.yview_scroll(-1, 'pages') or 'break')
        r_inner.bind(
            '<Next>', lambda *_: self.results.yview_scroll(1, 'pages') or 'break')
        r_inner.bind(
            '<Home>', lambda *_: self.results.yview_moveto(0) or 'break')
        r_inner.bind(
            '<End>', lambda *_: self.results.yview_moveto(1) or 'break')

    def _open_app_menu(self):
        """Post the application menu at the top-left of the root window."""
        self.root.update_idletasks()
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        self._app_menu.tk_popup(x, y)

    def _kb_focus_search(self):
        """Focus and select the main search field."""
        self.search_entry.focus_set()
        self.search_entry.select_range(0, 'end')

    def _kb_focus_filter(self):
        """Focus and select the raw GEDCOM filter field."""
        self.filter_entry.focus_set()
        self.filter_entry.select_range(0, 'end')

    def _kb_focus_list(self):
        """Focus the people list and select the first row when needed."""
        self.tree.focus_set()
        if not self.tree.focus():
            children = self.tree.get_children()
            if children:
                self.tree.focus(children[0])
                self.tree.selection_set(children[0])

    def _tree_jump(self, end, tree=None):
        """Move selection to the first or last row of a tree widget."""
        t = tree or self.tree
        children = t.get_children()
        if not children:
            return
        item = children[0] if end == 'first' else children[-1]
        t.focus_set()
        t.focus(item)
        t.selection_set(item)
        t.see(item)

    def _tree_type_ahead(self, event, tree=None):
        """Select the first tree row whose name starts with the typed character."""
        char = event.char
        if not char or not char.isalnum():
            return
        t = tree or self.tree
        char_lower = char.lower()
        children = t.get_children()
        if not children:
            return
        for item in children:
            name = t.set(item, 'name')
            if name.lower().startswith(char_lower):
                t.focus_set()
                t.focus(item)
                t.selection_set(item)
                t.see(item)
                return 'break'

    def _kb_copy(self, *_):
        """Handle Ctrl-C by copying results unless a Text widget has focus."""
        if isinstance(self.root.focus_get(), tk.Text):
            return  # let the text widget handle its own copy
        self._copy_results()
        return 'break'

    # ---------------------------------------------------------- Menu
    def _setup_menu(self):
        """Build the application menu and connect menu commands."""
        # On Windows, popup menus use Win32's native system font by default,
        # ignoring TkMenuFont and appearing smaller than the menu bar cascade
        # labels (which Windows renders at physical DPI).  Passing an explicit
        # font object switches Tk to OwnerDraw mode so the configured UI size
        # is honoured.  The named-font reference means font-size preference
        # changes propagate automatically without rebuilding the menus.
        _popup_kw: dict = {}
        if sys.platform == 'win32':
            _popup_kw['font'] = tkfont.nametofont('TkMenuFont')

        menubar = tk.Menu(self.root)
        if sys.platform == 'darwin':
            apple_menu = tk.Menu(menubar, name='apple')
            menubar.add_cascade(menu=apple_menu)
            apple_menu.add_command(label='About', command=self._show_about)
            apple_menu.add_separator()
        self.root.config(menu=menubar)
        self._menubar = menubar

        file_menu = tk.Menu(menubar, tearoff=0, **_popup_kw)
        self._file_menu = file_menu
        menubar.add_cascade(label=MENU_FILE, underline=0, menu=file_menu)
        _accel = 'Cmd+O' if sys.platform == 'darwin' else 'Ctrl+O'
        file_menu.add_command(label=MENU_OPEN_GEDCOM, underline=0,
                              accelerator=_accel, command=self._browse)
        self._recent_menu = tk.Menu(file_menu, tearoff=0, **_popup_kw)
        file_menu.add_cascade(label=MENU_OPEN_RECENT, underline=5,
                              menu=self._recent_menu)
        self._rebuild_recent_menu()
        if sys.platform != 'darwin':
            file_menu.add_separator()
            file_menu.add_command(label=MENU_PREFERENCES, underline=0,
                                  command=self._show_preferences)
            file_menu.add_separator()
            file_menu.add_command(label=MENU_QUIT, underline=0,
                                  command=self.root.quit)

        app_menu = tk.Menu(menubar, tearoff=0, **_popup_kw)
        self._app_menu = app_menu
        menubar.add_cascade(label=MENU_MENU, underline=0, menu=app_menu)
        if sys.platform == 'darwin':
            self.root.createcommand(
                '::tk::mac::ShowPreferences', self._show_preferences)
        app_menu.add_command(label=get_menu_how_to_use(), underline=0,
                             command=self._show_how_to_use)
        app_menu.add_command(label=get_menu_keyboard_shortcuts(), underline=0,
                             command=self._show_keyboard_shortcuts)
        app_menu.add_separator()
        app_menu.add_command(label=MENU_CHECK_FOR_UPDATES, underline=0,
                             command=self._check_for_updates)
        app_menu.add_separator()
        app_menu.add_command(label=MENU_PRIVACY_POLICY, underline=1,
                             command=self._show_privacy_policy)
        if sys.platform != 'darwin':
                app_menu.add_command(label=MENU_ABOUT, underline=0,
                                     command=self._show_about)

        self.root.createcommand('::tk::mac::Quit', self.root.quit)

    # ---------------------------------------------------------- Window centering helper
    def _center_on_root(self, win, w=None, h=None):
        """Fit and center a Toplevel window over the root window."""
        self._fit_window_to_content(
            win,
            min_w=w or 400,
            min_h=h or 300,
            preferred_w=w,
            preferred_h=h,
        )
