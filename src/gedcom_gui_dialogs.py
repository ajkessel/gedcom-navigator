#!/usr/bin/env python3
"""
gedcom_gui_dialogs.py

DialogsMixin - tag picker, person picker, path finder, and preferences dialogs
for GedcomNavigatorApp.
"""

import sys
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from gedcom_debug import log_exception
from gedcom_display import describe
from gedcom_gui_help_dialogs import HelpDialogsMixin
from gedcom_gui_person_dialog import PersonDialogMixin
from gedcom_name_search import individual_matches_query
from gedcom_relationship import (
    describe_relationship,
    get_ancestor_depths,
    get_descendant_depths,
)
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_i18n import _, get_available_languages
from gedcom_theme import get_flag_bg
from gedcom_tooltip import Tooltip


class DialogsMixin(PersonDialogMixin, HelpDialogsMixin):
    """Mixin providing picker, path finder, and preferences dialogs."""

    _PREFS_MIN_WIDTH = 500
    _PREFS_MIN_HEIGHT = 420
    _PREFS_PRE_SHOW_SETTLE_PASSES = 3
    _PREFS_WIN_REVEAL_DELAY_MS = 75
    _PREFS_HEIGHT_SETTLE_DELAYS_MS = (100, 250, 500)
    _PREFS_LANG_WIDTH_OVERHEAD = 60

    def _focus_person_picker_find_entry(self, dialog, search_entry):
        """Move keyboard focus to the person picker Find entry."""
        try:
            dialog.focus_force()
        except tk.TclError:
            return

        for widget in (search_entry, getattr(search_entry, "_entry", None)):
            if widget is None:
                continue
            try:
                widget.focus_set()
                if hasattr(widget, "select_range"):
                    widget.select_range(0, "end")
            except tk.TclError:
                continue

    @staticmethod
    def _preferences_dialog_target_height(
        outer,
        btn_frame,
        screen_h,
        *,
        min_h=_PREFS_MIN_HEIGHT,
        max_screen_ratio=0.9,
    ):
        """Return the compact Preferences height for current content metrics."""
        content_h = outer.winfo_reqheight() + 32
        btn_h = btn_frame.winfo_reqheight() + 16
        max_h = max(min_h, min(int(screen_h * max_screen_ratio), screen_h - 32))
        return max(min_h, min(content_h + btn_h, max_h))

    @staticmethod
    def _preferences_dialog_width(win, *, min_w=_PREFS_MIN_WIDTH):
        """Return a usable Preferences window width during early layout."""
        width = win.winfo_width()
        if width <= 1:
            try:
                width = int(win.geometry().split('x', 1)[0])
            except (tk.TclError, ValueError):
                width = min_w
        return max(min_w, width)

    def _view_tags(self):
        """Show tag-record definitions and allow choosing the DNA tag keyword."""
        if not self.tag_records:
            messagebox.showinfo(WIN_TAG_DEFINITIONS, MSG_NO_TAGS)
            return

        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_TAG_DEFINITIONS)
        win.transient(self.root)
        win.resizable(True, True)

        show_ids = self.show_ids.get()
        rows = sorted(self.tag_records.items())

        list_frame = ctk.CTkFrame(win, fg_color='transparent')
        list_frame.pack(fill='both', expand=True, padx=8, pady=(8, 0))

        if show_ids:
            tag_tree = ttk.Treeview(list_frame, columns=('id', 'name'),
                                    show='headings', selectmode='browse',
                                    height=min(len(rows), 20))
            tag_tree.heading('id', text=COL_TAG_ID)
            tag_tree.heading('name', text=COL_TAG_NAME)
            tag_tree.column('id', width=90, anchor='w', stretch=False)
            tag_tree.column('name', width=300, anchor='w', stretch=True)
        else:
            tag_tree = ttk.Treeview(list_frame, columns=('name',),
                                    show='headings', selectmode='browse',
                                    height=min(len(rows), 20))
            tag_tree.heading('name', text=COL_TAG_NAME)
            tag_tree.column('name', width=390, anchor='w', stretch=True)

        ysb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                               command=tag_tree.yview)
        tag_tree.configure(yscrollcommand=ysb.set)
        tag_tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        current_kw = self.tag_keyword.get().strip().lower()
        first_match = None
        for ref, name in rows:
            iid = tag_tree.insert('', 'end',
                                  values=(ref, name) if show_ids else (name,))
            if first_match is None and name.strip().lower() == current_kw:
                first_match = iid

        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=8, pady=8)

        def on_ok():
            sel = tag_tree.selection()
            if sel:
                name_val = tag_tree.set(sel[0], 'name')
                self.tag_keyword.set(name_val)
            win.destroy()

        def on_cancel():
            win.destroy()

        def on_double_click(event):
            row_id = tag_tree.identify_row(event.y)
            if not row_id:
                return 'break'
            tag_tree.focus(row_id)
            tag_tree.selection_set(row_id)
            tag_tree.see(row_id)
            on_ok()
            return 'break'

        ctk.CTkButton(btn_frame, text=BTN_OK, width=80,
                      command=on_ok).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=on_cancel).pack(side='right')

        tag_tree.bind('<Double-1>', on_double_click)
        tag_tree.bind('<Return>', lambda *_: on_ok())
        tag_tree.bind('<Home>', lambda *_: self._tree_jump(
            'first', tag_tree) or 'break')
        tag_tree.bind('<End>', lambda *_: self._tree_jump(
            'last',  tag_tree) or 'break')
        win.bind('<Escape>', lambda *_: on_cancel())

        self._fit_window_to_content(win, min_w=350, min_h=220)
        self._apply_theme_to_window(win)

        win.deiconify()
        win.focus_force()
        tag_tree.focus_set()
        target = first_match or (tag_tree.get_children()[
                                 0] if tag_tree.get_children() else None)
        if target:
            tag_tree.focus(target)
            tag_tree.selection_set(target)
            tag_tree.see(target)

    def _pick_person(self, title=WIN_SELECT_PERSON):
        """Modal dialog to pick one person from the loaded GEDCOM. Returns indi_id or None."""
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return None

        dialog = ctk.CTkToplevel(self.root)
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_force()

        result = [None]

        search_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        search_frame.pack(fill='x', padx=8, pady=(8, 0))
        ctk.CTkLabel(search_frame, text=LBL_FIND).pack(
            side='left', padx=(0, 4))
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True)
        fuzzy_var = tk.BooleanVar(value=self.fuzzy_search.get())
        ctk.CTkCheckBox(
            search_frame, text=CHK_FUZZY, variable=fuzzy_var, width=0,
        ).pack(side='left', padx=(8, 0))
        married_var = tk.BooleanVar(value=self.married_name_search.get())
        ctk.CTkCheckBox(
            search_frame, text=CHK_MARRIED_NAMES, variable=married_var, width=0,
        ).pack(side='left', padx=(8, 0))

        filter_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        filter_frame.pack(fill='x', padx=8, pady=(2, 0))
        ctk.CTkLabel(filter_frame, text=LBL_FILTER).pack(
            side='left', padx=(0, 4))
        filter_var = tk.StringVar()
        filter_entry = ctk.CTkEntry(filter_frame, textvariable=filter_var)
        filter_entry.pack(side='left', fill='x', expand=True)
        flagged_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            filter_frame, text=CHK_DNA_FLAGGED_ONLY, variable=flagged_var, width=0,
        ).pack(side='left', padx=(8, 0))

        list_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        list_frame.pack(fill='both', expand=True, padx=8, pady=(4, 0))

        picker_tree = ttk.Treeview(
            list_frame,
            columns=('name', 'birth', 'death', 'flagged'),
            show='headings',
            selectmode='browse',
        )
        picker_tree.heading('name', text=COL_NAME)
        picker_tree.heading('birth', text=COL_BIRTH)
        picker_tree.heading('death', text=COL_DEATH)
        picker_tree.heading('flagged', text=COL_DNA)
        picker_tree.column('name', width=240, anchor='w', stretch=True)
        picker_tree.column('birth', width=55, anchor='w', stretch=False)
        picker_tree.column('death', width=55, anchor='w', stretch=False)
        picker_tree.column('flagged', width=50, anchor='center', stretch=False)
        is_dark = ctk.get_appearance_mode() == 'Dark'
        picker_tree.tag_configure(
            'flagged_row', background=get_flag_bg(is_dark))

        ysb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                               command=picker_tree.yview)
        picker_tree.configure(yscrollcommand=ysb.set)
        picker_tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        after_id = [None]

        def populate():
            picker_tree.delete(*picker_tree.get_children())
            query = search_var.get().strip()
            filter_query = filter_var.get().strip().lower()
            flagged_only = flagged_var.get()
            extra_names_by_id = (
                self._model.married_name_index
                if married_var.get()
                else {}
            )
            shown = 0
            for indi_id in self.sorted_ids:
                indi = self.individuals[indi_id]
                if flagged_only and not indi['dna_markers']:
                    continue
                if query:
                    match, _score = individual_matches_query(
                        indi_id, indi, query,
                        fuzzy=fuzzy_var.get(),
                        fuzzy_threshold=self._fuzzy_threshold_value(),
                        extra_names=extra_names_by_id.get(indi_id),
                    )
                    if not match:
                        continue
                if filter_query:
                    raw_text = ' '.join(v.lower() for _, _, _, v in indi['_raw'])
                    if filter_query not in raw_text:
                        continue
                tags = ('flagged_row',) if indi['dna_markers'] else ()
                flagged_mark = '✓' if indi['dna_markers'] else ''
                picker_tree.insert(
                    '', 'end', iid=indi_id,
                    values=(self._display_name(indi),
                            indi['birth_year'] or '',
                            indi['death_year'] or '',
                            flagged_mark),
                    tags=tags,
                )
                shown += 1
                if shown >= self.MAX_LIST_DISPLAY:
                    break

        def on_search_change(*_):
            if after_id[0]:
                dialog.after_cancel(after_id[0])
            after_id[0] = dialog.after(150, populate)

        def picker_flush_and_jump():
            if after_id[0]:
                dialog.after_cancel(after_id[0])
                after_id[0] = None
                populate()
            self._tree_jump('first', picker_tree)

        for _var in (search_var, filter_var, fuzzy_var, married_var, flagged_var):
            _var.trace_add('write', on_search_change)
        search_entry.bind('<Return>', lambda *_: picker_flush_and_jump())
        filter_entry.bind('<Return>', lambda *_: picker_flush_and_jump())
        populate()

        def select():
            sel = picker_tree.selection()
            if sel:
                result[0] = sel[0]
            dialog.destroy()

        picker_tree.bind('<Double-1>', lambda *_: select())
        picker_tree.bind('<Return>', lambda *_: select())
        picker_tree.bind(
            '<Key>', lambda e: self._tree_type_ahead(e, picker_tree))
        picker_tree.bind('<Home>', lambda *_: self._tree_jump(
            'first', picker_tree) or 'break')
        picker_tree.bind('<End>', lambda *_: self._tree_jump(
            'last',  picker_tree) or 'break')
        dialog.bind('<Escape>', lambda *_: dialog.destroy())

        btn_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        btn_frame.pack(fill='x', padx=8, pady=8)
        ctk.CTkButton(btn_frame, text=BTN_SELECT, width=80,
                      command=select).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=dialog.destroy).pack(side='right')

        self._apply_theme_to_window(dialog)
        self._fit_window_to_content(
            dialog,
            min_w=500,
            min_h=420,
            preferred_w=620,
            preferred_h=540,
        )
        dialog.deiconify()

        def focus_find_entry():
            self._focus_person_picker_find_entry(dialog, search_entry)

        focus_find_entry()
        dialog.after_idle(focus_find_entry)
        dialog.after(50, focus_find_entry)
        self._picker_open = True
        try:
            dialog.wait_window()
        finally:
            self._picker_open = False
        return result[0]

    def _find_path(self):
        """Prompt for a target person and render paths from the current selection."""
        if self._busy:
            return
        if self._path_prompt_cancelled_recently():
            return
        sel = self.tree.selection()
        start_id = sel[0] if sel else self._active_id
        if not start_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_PATH_SEL_MSG)
            return

        target_id = self._pick_person(WIN_SELECT_TARGET)
        if not target_id:
            self._suppress_path_prompt_after_cancel()
            return
        self._display_path_target_id = target_id
        self._set_display_mode('paths', refresh=False)
        self._run_path_search(start_id, target_id)

    def _run_path_search(self, start_id, target_id):
        """Render relationship paths from start_id to target_id."""
        self._set_display_mode('paths', refresh=False)
        try:
            max_depth = int(self.max_depth.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(ERR_BAD_VAL_TITLE, ERR_BAD_VAL_DEPTH)
            return

        try:
            top_n = int(self.top_n.get())
        except (tk.TclError, ValueError):
            top_n = 5

        self._show_progress()
        self._set_busy(True)

        def _do_search(cancel_event):
            paths, truncated = self._model.find_all_paths(
                start_id, target_id, top_n, max_depth,
                cancel_event=cancel_event)
            home_path_data = self._find_home_path_data(
                start_id, max_depth, cancel_event=cancel_event)
            return paths, truncated, home_path_data

        def _on_cancel():
            self._hide_progress()
            self._set_busy(False)

        def _on_done(result, error):
            self._hide_search_popup()
            self._hide_progress()
            self._set_busy(False)
            if error:
                messagebox.showerror(ERR_PARSE_TITLE, str(error))
                return
            paths, truncated, home_path_data = result
            self._results_reversed = False
            self._reverse_btn.configure(text=BTN_REVERSE)
            self._display_path_target_id = target_id
            self._last_result = {'type': 'path',
                                 'start_id': start_id, 'end_id': target_id}
            self._render_path_results(
                start_id, target_id, paths, truncated, home_path_data)

        self._run_background_task(
            _do_search,
            _on_done,
            popup_message=PROGRESS_FINDING_PATH,
            cancelable=True,
            on_cancel=_on_cancel,
        )

    def _render_path_results(
            self, start_id, end_id, paths, truncated=False, home_paths=None):
        """Render relationship paths between two selected individuals."""
        if self._last_result and self._last_result.get('type') == 'path':
            self._last_result['paths'] = paths
            self._last_result['truncated'] = truncated
            self._last_result['home_paths'] = home_paths

        w = self.results
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        w._textbox.tag_configure('person_link')
        w._textbox.tag_bind('person_link', '<Enter>',
                            lambda *_: w._textbox.config(cursor='hand2'))
        w._textbox.tag_bind('person_link', '<Leave>',
                            lambda *_: w._textbox.config(cursor=''))
        w._textbox.tag_configure('relationship_link',
                                 foreground=self._link_color, underline=1)
        w._textbox.tag_bind('relationship_link', '<Enter>',
                            lambda *_: w._textbox.config(cursor='hand2'))
        w._textbox.tag_bind('relationship_link', '<Leave>',
                            lambda *_: w._textbox.config(cursor=''))

        def nl(text='', bold=False):
            w.insert('end', text + '\n', ('bold',) if bold else ())

        def person(indi_id, prefix='', suffix=''):
            if prefix:
                w.insert('end', prefix)
            tag = f'pers_{indi_id.strip("@")}'
            w.insert('end', describe(self.individuals[indi_id],
                                     show_id=self.show_ids.get()),
                     ('person_link', tag))
            w._textbox.tag_configure(tag, foreground=self._link_color)
            w._textbox.tag_bind(tag, '<Button-1>',
                                lambda _, iid=indi_id: self._navigate_to(iid))
            if suffix:
                w.insert('end', suffix)
            w.insert('end', '\n')

        def person_inline(indi_id, prefix='', suffix=''):
            if prefix:
                w.insert('end', prefix)
            tag = f'pers_{indi_id.strip("@")}'
            w.insert('end', describe(self.individuals[indi_id],
                                     show_id=self.show_ids.get()),
                     ('person_link', tag))
            w._textbox.tag_configure(tag, foreground=self._link_color)
            w._textbox.tag_bind(tag, '<Button-1>',
                                lambda _, iid=indi_id: self._navigate_to(iid))
            if suffix:
                w.insert('end', suffix)

        relationship_link_count = 0

        def relationship_line(rel, path, prefix=''):
            nonlocal relationship_link_count
            tag = f'path_graph_{relationship_link_count}'
            relationship_link_count += 1
            if prefix:
                w.insert('end', prefix)
            w.insert('end', RESULT_RELATIONSHIP.format(rel=rel),
                     ('relationship_link', tag))
            w._textbox.tag_bind(
                tag, '<Button-1>',
                lambda _, p=tuple(path), r=rel: self._show_path_graph(p, r))
            w.insert('end', '\n')

        def common_ancestor_line(ancestor_ids, prefix='', item_prefix='    '):
            if prefix:
                w.insert('end', prefix)
            if not ancestor_ids:
                w.insert('end', RESULT_COMMON_ANCESTOR)
                w.insert('end', RESULT_COMMON_ANCESTOR_NONE)
                w.insert('end', '\n')
                return
            if len(ancestor_ids) == 1:
                w.insert('end', RESULT_COMMON_ANCESTOR)
                person_inline(ancestor_ids[0])
                w.insert('end', '\n')
                return
            w.insert('end', RESULT_COMMON_ANCESTORS + '\n')
            for ancestor_id in ancestor_ids:
                person_inline(ancestor_id, prefix=item_prefix)
                w.insert('end', '\n')

        if self._results_reversed:
            disp_start, disp_end = end_id, start_id
            disp_paths = [self._reverse_path(
                p, self.individuals) for p in paths]
        else:
            disp_start, disp_end = start_id, end_id
            disp_paths = paths
        common_ancestor_ids = self._model.find_common_ancestors(
            disp_start, disp_end)

        nl(PATH_SECTION, bold=True)
        person(disp_start, prefix=PATH_FROM)
        person(disp_end,   prefix=PATH_TO)
        nl()

        if start_id == end_id:
            nl(PATH_SAME_PERSON)
        elif not disp_paths:
            nl(PATH_NOT_FOUND.format(depth=self.max_depth.get()))
        else:
            ancestors = get_ancestor_depths(
                disp_start, self.individuals, self.families)
            descendants = get_descendant_depths(
                disp_start, self.individuals, self.families)
            for rank, path in enumerate(disp_paths, 1):
                dist = len(path) - 1
                rel = describe_relationship(path, self.individuals,
                                            ancestors=ancestors,
                                            descendants=descendants,
                                            families=self.families)
                nl(PATH_RANK.format(
                    rank=rank, rel=rel, dist=dist,
                    plural='s' if dist != 1 else ''), bold=True)
                relationship_line(rel, path, prefix="  ")
                common_ancestor_line(
                    common_ancestor_ids, prefix="  ", item_prefix="    ")
                for i, (node_id, edge) in enumerate(path):
                    if i == 0:
                        person(node_id, prefix="  ")
                    else:
                        person(node_id, prefix=self._path_edge_prefix(
                            edge, "    "))
                nl()
            if truncated:
                nl(PATH_SEARCH_CAP)
        nl()

        self._render_home_path_section(
            start_id,
            home_paths,
            nl=nl,
            person=person,
            relationship_line=relationship_line,
            common_ancestor_line=common_ancestor_line,
            separator=None,
            reverse=self._results_reversed,
        )

        self._reverse_btn.configure(state='normal')
        w.configure(state='disabled')

    def _show_preferences(self):
        """Open the preferences dialog for display, search, and cache settings."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_PREFERENCES)
        win.resizable(True, True)
        win.transient(self.root)
        win.grab_set()

        _scroll_frame = ctk.CTkScrollableFrame(win, fg_color='transparent', corner_radius=0)
        _scroll_frame.pack(fill='both', expand=True)

        outer = ctk.CTkFrame(_scroll_frame, fg_color='transparent')
        outer.pack(fill='x', padx=16, pady=16)

        # Appearance section (font size + theme + tooltips)
        appearance_section = ctk.CTkFrame(outer, border_width=1)
        appearance_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(appearance_section, text=FRAME_APPEARANCE, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))

        # Resolve the CTkFrame background so ttk.Radiobutton blends in.
        # Walk up _fg_color chain past any transparent frames.
        def _section_bg(frame):
            try:
                fg = frame._fg_color
                if fg == 'transparent':
                    return _section_bg(frame.master)
                is_dark = ctk.get_appearance_mode() == 'Dark'
                return (fg[1] if is_dark else fg[0]) if isinstance(fg, (list, tuple)) else fg
            except AttributeError:
                return frame.cget('background')

        # On Windows/Linux, stamp the CTkFrame colour onto a named ttk style so
        # ttk.Radiobutton blends in.  On macOS the Aqua ttk theme ignores the
        # background style option; tk.Radiobutton (same native indicator, but
        # classic widget) does respect it, so we use that instead.
        _rb_style = ttk.Style()

        # Match ttk.Radiobutton font to CTkFont pixel sizing.  CTkFont.cget('size')
        # returns the positive pixel count; negate on Windows to use Tk's pixel
        # notation so the radiobutton text renders at the same size as CTkLabel.
        try:
            _ctk_font_obj = ctk.CTkFont()
            _size = _ctk_font_obj.cget('size')
            _rb_font = (_ctk_font_obj.cget('family'),
                        -_size if sys.platform == 'win32' else _size)
        except Exception:  # pylint: disable=broad-exception-caught
            log_exception("building preferences radiobutton font")
            _rb_font = None

        def _radiobutton(parent, *, text, variable, value):
            if sys.platform == 'darwin':
                bg = _section_bg(parent)
                return tk.Radiobutton(parent, text=text, variable=variable,
                                      value=value, background=bg,
                                      activebackground=bg, highlightthickness=0)
            if sys.platform != 'darwin':
                style_kw = {'background': _section_bg(parent)}
                if _rb_font:
                    style_kw['font'] = _rb_font
                _rb_style.configure('Pref.TRadiobutton', **style_kw)
            return ttk.Radiobutton(parent, text=text, variable=variable,
                                   value=value, style='Pref.TRadiobutton')

        # Font size row
        font_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        font_row.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(font_row, text=FRAME_FONT_SIZE +
                     ':').pack(side='left', padx=(0, 8))
        size_var = tk.StringVar(value=self._font_size_pref)
        for label, key in ((FONT_SMALL, "small"), (FONT_MEDIUM, "medium"),
                           (FONT_LARGE, "large"), (FONT_JUMBO, "jumbo")):
            _radiobutton(
                font_row, text=label, variable=size_var, value=key,
            ).pack(side='left', padx=8)

        # Theme row
        theme_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        theme_row.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(theme_row, text=FRAME_THEME +
                     ':').pack(side='left', padx=(0, 8))
        theme_var = tk.StringVar(value=self._theme_pref)
        for name in self._THEME_NAMES:
            _radiobutton(
                theme_row, text=name, variable=theme_var, value=name,
            ).pack(side='left', padx=6)

        # Hide Tooltips checkbox
        tooltip_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        tooltip_row.pack(fill='x', padx=12, pady=(0, 10))
        hide_tooltips_var = tk.BooleanVar(value=self._hide_tooltips_pref)
        hide_tooltips_chk = ctk.CTkCheckBox(
            tooltip_row, text=CHK_HIDE_TOOLTIPS, variable=hide_tooltips_var)
        hide_tooltips_chk.pack(anchor='w')
        Tooltip(hide_tooltips_chk, TIP_HIDE_TOOLTIPS)

        # Search defaults section
        search_section = ctk.CTkFrame(outer, border_width=1)
        search_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(search_section, text=FRAME_SEARCH_DEFAULTS, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        search_frame = ctk.CTkFrame(search_section, fg_color='transparent')
        search_frame.pack(fill='x', padx=12, pady=(0, 10))

        _pref_top_n_label = ctk.CTkLabel(search_frame, text=LBL_TOP_N_RESULTS)
        _pref_top_n_label.grid(row=0, column=0, sticky='w', padx=(0, 8))
        top_n_var = tk.IntVar(value=self.top_n.get())
        _pref_top_n_spin = ttk.Spinbox(
            search_frame, from_=1, to=20, textvariable=top_n_var, width=6)
        _pref_top_n_spin.grid(row=0, column=1, sticky='w', padx=(0, 24))
        Tooltip(_pref_top_n_label, TIP_TOP_N)
        Tooltip(_pref_top_n_spin, TIP_TOP_N)
        _pref_max_depth_label = ctk.CTkLabel(
            search_frame, text=LBL_MAX_DEPTH_PREF)
        _pref_max_depth_label.grid(row=0, column=2, sticky='w', padx=(0, 8))
        max_depth_var = tk.IntVar(value=self.max_depth.get())
        _pref_max_depth_spin = ttk.Spinbox(
            search_frame, from_=1, to=200, textvariable=max_depth_var, width=6)
        _pref_max_depth_spin.grid(row=0, column=3, sticky='w')
        Tooltip(_pref_max_depth_label, TIP_MAX_DEPTH)
        Tooltip(_pref_max_depth_spin, TIP_MAX_DEPTH)
        _pref_fuzzy_label = ctk.CTkLabel(
            search_frame, text=LBL_FUZZY_THRESHOLD)
        _pref_fuzzy_label.grid(
            row=1, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        fuzzy_threshold_var = tk.DoubleVar(
            value=round(float(self.fuzzy_threshold.get()), 2))
        _pref_fuzzy_spin = ttk.Spinbox(
            search_frame, from_=0.0, to=1.0, increment=0.01,
            textvariable=fuzzy_threshold_var, width=6, format="%.2f")
        _pref_fuzzy_spin.grid(row=1, column=1, sticky='w', pady=(6, 0))
        Tooltip(_pref_fuzzy_label, TIP_FUZZY_THRESHOLD)
        Tooltip(_pref_fuzzy_spin, TIP_FUZZY_THRESHOLD)

        _pref_max_display_label = ctk.CTkLabel(
            search_frame, text=LBL_MAX_DISPLAY)
        _pref_max_display_label.grid(
            row=1, column=2, sticky='w', padx=(0, 8), pady=(6, 0))
        max_display_var = tk.IntVar(value=self.max_display.get())
        _pref_max_display_spin = ttk.Spinbox(
            search_frame, from_=100, to=100000, increment=500,
            textvariable=max_display_var, width=8)
        _pref_max_display_spin.grid(row=1, column=3, sticky='w', pady=(6, 0))
        Tooltip(_pref_max_display_label, TIP_MAX_DISPLAY)
        Tooltip(_pref_max_display_spin, TIP_MAX_DISPLAY)

        _pref_tag_keyword_label = ctk.CTkLabel(
            search_frame, text=LBL_TAG_KEYWORD)
        _pref_tag_keyword_label.grid(
            row=2, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        tag_keyword_var = tk.StringVar(value=self.tag_keyword.get())
        _pref_tag_keyword_entry = ctk.CTkEntry(
            search_frame, textvariable=tag_keyword_var, width=180)
        _pref_tag_keyword_entry.grid(
            row=2, column=1, columnspan=3, sticky='ew', pady=(6, 0))
        Tooltip(_pref_tag_keyword_label, TIP_TAG_KEYWORD)
        Tooltip(_pref_tag_keyword_entry, TIP_TAG_KEYWORD)

        _pref_page_marker_label = ctk.CTkLabel(
            search_frame, text=LBL_PAGE_MARKER)
        _pref_page_marker_label.grid(
            row=3, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        page_marker_var = tk.StringVar(value=self.page_marker.get())
        _pref_page_marker_entry = ctk.CTkEntry(
            search_frame, textvariable=page_marker_var, width=180)
        _pref_page_marker_entry.grid(
            row=3, column=1, columnspan=3, sticky='ew', pady=(6, 0))
        Tooltip(_pref_page_marker_label, TIP_PAGE_MARKER)
        Tooltip(_pref_page_marker_entry, TIP_PAGE_MARKER)

        # Display section
        display_section = ctk.CTkFrame(outer, border_width=1)
        display_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(display_section, text=FRAME_DISPLAY, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        display_frame = ctk.CTkFrame(display_section, fg_color='transparent')
        display_frame.pack(fill='x', padx=12, pady=(0, 10))

        show_ids_var = tk.BooleanVar(value=self.show_ids.get())
        _show_ids_chk = ctk.CTkCheckBox(display_frame, text=CHK_SHOW_IDS,
                                        variable=show_ids_var)
        _show_ids_chk.pack(anchor='w')
        Tooltip(_show_ids_chk, TIP_SHOW_IDS)

        show_full_gedcom_var = tk.BooleanVar(value=self.show_full_gedcom.get())
        _show_full_gedcom_chk = ctk.CTkCheckBox(
            display_frame, text=CHK_SHOW_FULL_GEDCOM,
            variable=show_full_gedcom_var)
        _show_full_gedcom_chk.pack(anchor='w', pady=(4, 0))
        Tooltip(_show_full_gedcom_chk, TIP_SHOW_FULL_GEDCOM)

        name_order_row = ctk.CTkFrame(display_frame, fg_color='transparent')
        name_order_row.pack(anchor='w', pady=(6, 0))
        ctk.CTkLabel(name_order_row, text=LBL_NAME_FORMAT).pack(
            side='left', padx=(0, 8))
        name_order_var = tk.StringVar(value=self._name_order)
        _radiobutton(name_order_row, text=NAME_FIRST_LAST,
                     variable=name_order_var, value='first_last').pack(side='left', padx=(0, 8))
        _radiobutton(name_order_row, text=NAME_LAST_FIRST,
                     variable=name_order_var, value='last_first').pack(side='left')

        default_display_row = ctk.CTkFrame(display_frame, fg_color='transparent')
        default_display_row.pack(anchor='w', pady=(6, 0))
        ctk.CTkLabel(default_display_row, text=LBL_DEFAULT_DISPLAY).pack(
            side='left', padx=(0, 8))
        default_display_var = tk.StringVar(value=self._config.get_default_display())
        _radiobutton(default_display_row, text=DISPLAY_MODE_PROFILE,
                     variable=default_display_var, value='profile').pack(side='left', padx=(0, 8))
        _radiobutton(default_display_row, text=DISPLAY_MODE_MATCHES,
                     variable=default_display_var, value='matches').pack(side='left', padx=(0, 8))
        _radiobutton(default_display_row, text=DISPLAY_MODE_PATHS,
                     variable=default_display_var, value='paths').pack(side='left')

        # Language row (wraps to multiple rows on narrow windows)
        lang_row = ctk.CTkFrame(display_section, fg_color='transparent')
        lang_row.pack(fill='x', padx=12, pady=(0, 10))
        ctk.CTkLabel(lang_row, text=LBL_LANGUAGE).pack(anchor='w', pady=(0, 2))
        lang_var = tk.StringVar(value=self._config.get_language())
        lang_options = get_available_languages()

        lang_btns_frame = ctk.CTkFrame(lang_row, fg_color='transparent')
        lang_btns_frame.pack(fill='x')
        _lang_btns = [
            _radiobutton(lang_btns_frame, text=label, variable=lang_var, value=code)
            for label, code in lang_options
        ]

        def _layout_lang_buttons(event=None, _force_width=None):
            avail = _force_width if _force_width is not None else lang_btns_frame.winfo_width()
            if avail <= 1:
                return
            for b in _lang_btns:
                b.grid_forget()
            row = col = x = 0
            for b in _lang_btns:
                bw = b.winfo_reqwidth() + 12
                if col and x + bw > avail:
                    row += 1
                    col = 0
                    x = 0
                b.grid(row=row, column=col, padx=(0, 6), pady=(0, 2), sticky='w')
                x += bw
                col += 1

        lang_btns_frame.bind('<Configure>', _layout_lang_buttons)

        # Cache section
        cache_section = ctk.CTkFrame(outer, border_width=1)
        cache_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(cache_section, text=FRAME_CACHE, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        cache_frame = ctk.CTkFrame(cache_section, fg_color='transparent')
        cache_frame.pack(fill='x', padx=12, pady=(0, 10))
        ctk.CTkButton(cache_frame, text=BTN_CLEAR_CACHE,
                      command=self._clear_cache).pack(side='left')
        ctk.CTkLabel(cache_frame, text=LBL_CACHE_NOTE).pack(
            side='left', padx=(10, 0))

        # Buttons
        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=(0, 16))

        def on_ok():
            self._font_size_pref = size_var.get()
            self._apply_font_size(self._font_size_pref)
            self._save_font_preference(self._font_size_pref)
            self._apply_theme(theme_var.get())
            self._save_theme_preference(theme_var.get())
            self._hide_tooltips_pref = hide_tooltips_var.get()
            Tooltip.enabled = not self._hide_tooltips_pref
            self._save_hide_tooltips_preference(self._hide_tooltips_pref)
            try:
                self.top_n.set(max(1, int(top_n_var.get())))
                self._config.set_top_n(self.top_n.get())
            except (tk.TclError, ValueError):
                pass
            try:
                self.max_depth.set(max(1, int(max_depth_var.get())))
                self._config.set_max_depth(self.max_depth.get())
            except (tk.TclError, ValueError):
                pass
            try:
                threshold = min(
                    1.0, max(0.0, float(fuzzy_threshold_var.get())))
                self.fuzzy_threshold.set(threshold)
                self._config.set_fuzzy_threshold(threshold)
            except (tk.TclError, ValueError):
                pass
            try:
                self.max_display.set(max(100, int(max_display_var.get())))
                self._config.set_max_display(self.max_display.get())
            except (tk.TclError, ValueError):
                pass
            self.tag_keyword.set(tag_keyword_var.get())
            self._config.set_tag_keyword(tag_keyword_var.get())
            self.page_marker.set(page_marker_var.get())
            self._config.set_page_marker(page_marker_var.get())
            self.show_ids.set(show_ids_var.get())
            self._config.set_show_ids(show_ids_var.get())
            self.show_full_gedcom.set(show_full_gedcom_var.get())
            self._config.set_show_full_gedcom(show_full_gedcom_var.get())
            self._name_order = name_order_var.get()
            self._config.set_name_order(self._name_order)
            self._config.set_default_display(default_display_var.get())
            
            # Check if language has changed
            old_lang = self._config.get_language()
            new_lang = lang_var.get()
            if old_lang != new_lang:
                self._config.set_language(new_lang)
                messagebox.showinfo(
                    _(LBL_LANGUAGE_CHANGED),
                    _(MSG_LANGUAGE_CHANGED).format(old=old_lang, new=new_lang)
                )

            self._pop_sort_key = None
            self._populate_tree()
            self._refresh_result()
            win.destroy()

        def on_cancel():
            win.destroy()

        win.bind('<Escape>', lambda *_: on_cancel())
        win.bind('<Return>', lambda *_: on_ok())

        ctk.CTkButton(btn_frame, text=BTN_OK, width=80,
                      command=on_ok).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=on_cancel).pack(side='right')

        # Pre-layout language buttons at the expected inner width so we can measure
        # the accurate content height before the window is shown.  ~440 px accounts
        # for window min_w=500 minus the CTkScrollableFrame scrollbar, outer padx=16,
        # and the display-section padx=12 on each side.
        _layout_lang_buttons(_force_width=440)
        win.update_idletasks()

        _pre_target_h = self._preferences_dialog_target_height(
            outer, btn_frame, win.winfo_screenheight())

        self._fit_window_to_content(
            win,
            min_w=self._PREFS_MIN_WIDTH,
            min_h=self._PREFS_MIN_HEIGHT,
            preferred_h=_pre_target_h,
        )

        def _correct_prefs_height():
            # Re-layout at the actual window width and resize if the pre-computed
            # height was off.  Early Configure events can still report a width
            # of 1, so fall back to the known window width minus the same
            # scrollbar/padding allowance used for the pre-layout pass.
            lang_width = lang_btns_frame.winfo_width()
            if lang_width <= 1:
                lang_width = (
                    self._preferences_dialog_width(win)
                    - self._PREFS_LANG_WIDTH_OVERHEAD
                )
            _layout_lang_buttons(_force_width=max(1, lang_width))
            win.update_idletasks()
            target_h = self._preferences_dialog_target_height(
                outer, btn_frame, win.winfo_screenheight())
            geo = win.geometry()
            current_h = int(geo.split('x')[1].split('+')[0])
            if abs(target_h - current_h) > 4:
                fw = geo.split('x')[0]
                pos = geo.split('+', 1)[1]
                # Unlock CTkToplevel's scaling maxsize before resizing.
                win.maxsize(10000, 10000)
                win.geometry(f'{fw}x{target_h}+{pos}')

        for _ in range(self._PREFS_PRE_SHOW_SETTLE_PASSES):
            _correct_prefs_height()

        hidden_until_mapped = False
        if sys.platform != 'darwin':
            try:
                win.attributes('-alpha', 0.0)
                hidden_until_mapped = True
            except tk.TclError:
                hidden_until_mapped = False

        win.deiconify()
        win.update_idletasks()
        for _ in range(self._PREFS_PRE_SHOW_SETTLE_PASSES):
            _correct_prefs_height()

        def _focus_prefs_window():
            try:
                win.focus_force()
            except tk.TclError:
                pass

        def _reveal_prefs_window():
            for _ in range(self._PREFS_PRE_SHOW_SETTLE_PASSES):
                _correct_prefs_height()
            if hidden_until_mapped:
                try:
                    win.attributes('-alpha', 1.0)
                except tk.TclError:
                    pass
            _focus_prefs_window()

        if hidden_until_mapped:
            win.after(self._PREFS_WIN_REVEAL_DELAY_MS, _reveal_prefs_window)
        else:
            win.after(50, _focus_prefs_window)

        for delay_ms in self._PREFS_HEIGHT_SETTLE_DELAYS_MS:
            win.after(delay_ms, _correct_prefs_height)
