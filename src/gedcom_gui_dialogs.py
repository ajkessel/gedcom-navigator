"""
gedcom_gui_dialogs.py

DialogsMixin — person detail, tag picker, person picker, path finder,
preferences, and documentation windows for DNAMatchFinderApp.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import os
import sys
import threading
import webbrowser
import customtkinter as ctk

from gedcom_core import bfs_find_all_paths, describe
from gedcom_relationship import (
    _extract_event, get_ancestor_depths, get_descendant_depths,
    describe_relationship,
)
from gedcom_markdown import render_markdown
from gedcom_strings import *  # noqa: F401,F403
from gedcom_theme import get_flag_bg
from gedcom_tooltip import Tooltip


class DialogsMixin:
    """Mixin providing dialog and documentation window methods."""

    def _show_person(self):
        """Open the GEDCOM record viewer for the selected person."""
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        indi_id = sel[0] if sel else self._active_id
        if not indi_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        self._show_person_for(indi_id)

    def _show_person_for(self, indi_id):
        """Open a detail window for a specific individual ID."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.transient(self.root)
        win.grab_set()

        _geo_after = [None]

        def _on_win_configure(event):
            if event.widget is not win:
                return
            if _geo_after[0]:
                win.after_cancel(_geo_after[0])
            _geo_after[0] = win.after(
                400, lambda: self._persist_show_person_geometry(win))

        win.bind('<Escape>', lambda *_: win.destroy())

        text = ctk.CTkTextbox(
            win, font=(self._mono_family, self._mono_size), wrap='none')
        text._textbox.configure(padx=8, pady=8)
        text.pack(fill='both', expand=True)
        text._textbox.tag_configure(
            'bold', font=(self._mono_family, self._mono_size, 'bold'))
        text._textbox.tag_configure('person_link')
        text._textbox.tag_bind('person_link', '<Enter>',
                               lambda *_: text._textbox.config(cursor='hand2'))
        text._textbox.tag_bind('person_link', '<Leave>',
                               lambda *_: text._textbox.config(cursor=''))

        win.bind('<Up>', lambda *_: text.yview_scroll(-1, 'units') or 'break')
        win.bind('<Down>', lambda *_: text.yview_scroll(1, 'units') or 'break')
        win.bind('<Prior>', lambda *_: text.yview_scroll(-1, 'pages') or 'break')
        win.bind('<Next>', lambda *_: text.yview_scroll(1, 'pages') or 'break')
        win.bind('<Home>', lambda *_: text.yview_moveto(0) or 'break')
        win.bind('<End>', lambda *_: text.yview_moveto(1) or 'break')

        def populate(iid):
            indi = self.individuals[iid]
            win.title(WIN_GEDCOM_RECORD.format(name=indi['name'] or iid))
            text.configure(state='normal')
            text.delete('1.0', 'end')
            self._clear_person_tags(text)

            def add(line, bold=False):
                text.insert('end', line + '\n', ('bold',) if bold else ())

            def person(pid, prefix=''):
                if prefix:
                    text.insert('end', prefix)
                tag = f'pers_{pid.strip("@")}'
                text.insert('end', describe(self.individuals[pid],
                                            show_id=self.show_ids.get()),
                            ('person_link', tag))
                text._textbox.tag_configure(tag, foreground=self._link_color)
                text._textbox.tag_bind(tag, '<Button-1>',
                                       lambda _, p=pid: populate(p))
                text.insert('end', '\n')

            add(BIO_SECTION, bold=True)
            bio_found = False

            def fmt_event(date, place):
                parts = [p for p in (date, place) if p]
                return ', '.join(parts)

            b_date, b_place = _extract_event(indi['_raw'], 'BIRT')
            if b_date or b_place:
                bio_found = True
                add(BIO_BORN.format(event=fmt_event(b_date, b_place)))

            for fam_id in indi['fams']:
                fam = self.families.get(fam_id)
                if not fam:
                    continue
                m_date = fam.get('marr_date', '')
                m_place = fam.get('marr_place', '')
                spouse_id = fam['wife'] if fam['husb'] == iid else fam['husb']
                spouse_name = (self._display_name(self.individuals[spouse_id])
                               if spouse_id and spouse_id in self.individuals else '')
                if spouse_name or m_date or m_place:
                    bio_found = True
                    parts = [p for p in (spouse_name, m_date, m_place) if p]
                    add(BIO_MARRIED.format(spouses=', '.join(parts)))

            d_date, d_place = _extract_event(indi['_raw'], 'DEAT')
            if d_date or d_place:
                bio_found = True
                add(BIO_DIED.format(event=fmt_event(d_date, d_place)))

            bu_date, bu_place = _extract_event(indi['_raw'], 'BURI')
            if bu_date or bu_place:
                bio_found = True
                add(BIO_BURIED.format(event=fmt_event(bu_date, bu_place)))

            if not bio_found:
                add(BIO_NO_INFO)
            add("")

            add(FAM_SECTION, bold=True)
            family_found = False
            parents, siblings, spouses, children = self._get_family_members(iid)

            if parents:
                family_found = True
                add(FAM_PARENTS)
                for pid in parents:
                    person(pid, prefix="    ")
            if siblings:
                family_found = True
                add(FAM_SIBLINGS)
                for sib_id in siblings:
                    person(sib_id, prefix="    ")
            if spouses:
                family_found = True
                add(FAM_SPOUSES if len(spouses) > 1 else FAM_SPOUSE)
                for sid in spouses:
                    person(sid, prefix="    ")
            if children:
                family_found = True
                add(FAM_CHILDREN)
                for child_id in children:
                    person(child_id, prefix="    ")
            if not family_found:
                add(FAM_NO_INFO)
            add("")
            add(GEDCOM_SECTION, bold=True)

            for level, xref, tag, value in indi.get('_raw', []):
                parts = [str(level)]
                if xref and self.show_ids.get():
                    parts.append(xref)
                parts.append(tag)
                if value:
                    parts.append(value)
                add(' '.join(parts))

            text.configure(state='disabled')

        populate(indi_id)

        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(4, 8))
        ctk.CTkButton(btn_frame, text=BTN_CLOSE, width=80,
                      command=win.destroy).pack(side='right', padx=8)

        if self._show_person_geometry:
            win.minsize(400, 300)
            win.geometry(self._show_person_geometry)
        else:
            self._fit_window_to_content(
                win,
                min_w=400,
                min_h=300,
                preferred_w=700,
                preferred_h=520,
            )
        win.bind('<Configure>', _on_win_configure)
        win.deiconify()
        win.focus_force()

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

        ctk.CTkButton(btn_frame, text=BTN_OK, width=80,
                      command=on_ok).pack(side='right', padx=(4, 0))
        ctk.CTkButton(btn_frame, text=BTN_CANCEL, width=80,
                      command=on_cancel).pack(side='right')

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
        search_frame.pack(fill='x', padx=8, pady=8)
        ctk.CTkLabel(search_frame, text=LBL_FIND).pack(side='left', padx=(0, 4))
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True)

        list_frame = ctk.CTkFrame(dialog, fg_color='transparent')
        list_frame.pack(fill='both', expand=True, padx=8)

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
        picker_tree.tag_configure('flagged_row', background=get_flag_bg(is_dark))

        ysb = ctk.CTkScrollbar(list_frame, orientation='vertical',
                               command=picker_tree.yview)
        picker_tree.configure(yscrollcommand=ysb.set)
        picker_tree.pack(side='left', fill='both', expand=True)
        ysb.pack(side='right', fill='y')

        after_id = [None]

        def populate(query=''):
            picker_tree.delete(*picker_tree.get_children())
            query_l = query.strip().lower()
            query_tokens = query_l.split()
            shown = 0
            for indi_id in self.sorted_ids:
                indi = self.individuals[indi_id]
                if query_tokens:
                    all_names = indi['alt_names'] or [indi['name']]
                    if not (
                        any(all(tok in name.lower() for tok in query_tokens)
                            for name in all_names)
                        or query_l in indi_id.lower()
                    ):
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
            after_id[0] = dialog.after(150, lambda: populate(search_var.get()))

        def picker_flush_and_jump():
            if after_id[0]:
                dialog.after_cancel(after_id[0])
                after_id[0] = None
                populate(search_var.get())
            self._tree_jump('first', picker_tree)

        search_var.trace_add('write', on_search_change)
        search_entry.bind('<Return>', lambda *_: picker_flush_and_jump())
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
            min_h=380,
            preferred_w=600,
            preferred_h=500,
        )
        dialog.deiconify()
        search_entry.focus_set()
        dialog.wait_window()
        return result[0]

    def _find_path(self):
        """Prompt for a target person and render paths from the current selection."""
        if self._busy:
            return
        sel = self.tree.selection()
        start_id = sel[0] if sel else self._active_id
        if not start_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_PATH_SEL_MSG)
            return

        target_id = self._pick_person(WIN_SELECT_TARGET)
        if not target_id:
            return

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

        def _do_search():
            try:
                paths, truncated = self._model.find_all_paths(
                    start_id, target_id, top_n, max_depth)
                self.root.after(0, lambda: _on_done(paths, truncated, None))
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.root.after(0, lambda: _on_done(None, None, e))

        def _on_done(paths, truncated, error):
            self._hide_progress()
            self._set_busy(False)
            if error:
                messagebox.showerror(ERR_PARSE_TITLE, str(error))
                return
            self._results_reversed = False
            self._reverse_btn.configure(text=BTN_REVERSE)
            self._last_result = {'type': 'path',
                                 'start_id': start_id, 'end_id': target_id}
            self._render_path_results(start_id, target_id, paths, truncated)

        threading.Thread(target=_do_search, daemon=True).start()

    def _render_path_results(self, start_id, end_id, paths, truncated=False):
        """Render relationship paths between two selected individuals."""
        if self._last_result and self._last_result.get('type') == 'path':
            self._last_result['paths'] = paths
            self._last_result['truncated'] = truncated

        w = self.results
        w.configure(state='normal')
        w.delete('1.0', 'end')
        self._clear_person_tags(w)

        w._textbox.tag_configure('person_link')
        w._textbox.tag_bind('person_link', '<Enter>',
                            lambda *_: w._textbox.config(cursor='hand2'))
        w._textbox.tag_bind('person_link', '<Leave>',
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

        if self._results_reversed:
            disp_start, disp_end = end_id, start_id
            disp_paths = [self._reverse_path(p, self.individuals) for p in paths]
        else:
            disp_start, disp_end = start_id, end_id
            disp_paths = paths

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
                                            descendants=descendants)
                nl(PATH_RANK.format(
                    rank=rank, rel=rel, dist=dist,
                    plural='s' if dist != 1 else ''), bold=True)
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

        self._reverse_btn.configure(state='normal')
        w.configure(state='disabled')

    def _show_preferences(self):
        """Open the preferences dialog for display, search, and cache settings."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_PREFERENCES)
        win.resizable(True, True)
        win.transient(self.root)

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=16, pady=16)

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

        def _radiobutton(parent, *, text, variable, value):
            if sys.platform == 'darwin':
                bg = _section_bg(parent)
                return tk.Radiobutton(parent, text=text, variable=variable,
                                      value=value, background=bg,
                                      activebackground=bg, highlightthickness=0)
            if sys.platform != 'darwin':
                _rb_style.configure('Pref.TRadiobutton', background=_section_bg(parent))
            return ttk.Radiobutton(parent, text=text, variable=variable,
                                   value=value, style='Pref.TRadiobutton')

        # Font size row
        font_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        font_row.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(font_row, text=FRAME_FONT_SIZE + ':').pack(side='left', padx=(0, 8))
        size_var = tk.StringVar(value=self._font_size_pref)
        for label, key in ((FONT_SMALL, "small"), (FONT_MEDIUM, "medium"), (FONT_LARGE, "large")):
            _radiobutton(
                font_row, text=label, variable=size_var, value=key,
            ).pack(side='left', padx=8)

        # Theme row
        theme_row = ctk.CTkFrame(appearance_section, fg_color='transparent')
        theme_row.pack(fill='x', padx=12, pady=(0, 4))
        ctk.CTkLabel(theme_row, text=FRAME_THEME + ':').pack(side='left', padx=(0, 8))
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
        _pref_max_depth_label = ctk.CTkLabel(search_frame, text=LBL_MAX_DEPTH_PREF)
        _pref_max_depth_label.grid(row=0, column=2, sticky='w', padx=(0, 8))
        max_depth_var = tk.IntVar(value=self.max_depth.get())
        _pref_max_depth_spin = ttk.Spinbox(
            search_frame, from_=1, to=200, textvariable=max_depth_var, width=6)
        _pref_max_depth_spin.grid(row=0, column=3, sticky='w')
        Tooltip(_pref_max_depth_label, TIP_MAX_DEPTH)
        Tooltip(_pref_max_depth_spin, TIP_MAX_DEPTH)
        _pref_fuzzy_label = ctk.CTkLabel(search_frame, text=LBL_FUZZY_THRESHOLD)
        _pref_fuzzy_label.grid(row=1, column=0, sticky='w', padx=(0, 8), pady=(6, 0))
        fuzzy_threshold_var = tk.DoubleVar(
            value=round(float(self.fuzzy_threshold.get()), 2))
        _pref_fuzzy_spin = ttk.Spinbox(
            search_frame, from_=0.0, to=1.0, increment=0.01,
            textvariable=fuzzy_threshold_var, width=6, format="%.2f")
        _pref_fuzzy_spin.grid(row=1, column=1, sticky='w', pady=(6, 0))
        Tooltip(_pref_fuzzy_label, TIP_FUZZY_THRESHOLD)
        Tooltip(_pref_fuzzy_spin, TIP_FUZZY_THRESHOLD)

        _pref_max_display_label = ctk.CTkLabel(search_frame, text=LBL_MAX_DISPLAY)
        _pref_max_display_label.grid(row=1, column=2, sticky='w', padx=(0, 8), pady=(6, 0))
        max_display_var = tk.IntVar(value=self.max_display.get())
        _pref_max_display_spin = ttk.Spinbox(
            search_frame, from_=100, to=100000, increment=500,
            textvariable=max_display_var, width=8)
        _pref_max_display_spin.grid(row=1, column=3, sticky='w', pady=(6, 0))
        Tooltip(_pref_max_display_label, TIP_MAX_DISPLAY)
        Tooltip(_pref_max_display_spin, TIP_MAX_DISPLAY)

        # Display section
        display_section = ctk.CTkFrame(outer, border_width=1)
        display_section.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(display_section, text=FRAME_DISPLAY, anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(
            anchor='nw', padx=12, pady=(8, 4))
        display_frame = ctk.CTkFrame(display_section, fg_color='transparent')
        display_frame.pack(fill='x', padx=12, pady=(0, 10))

        show_ids_var = tk.BooleanVar(value=self.show_ids.get())
        ctk.CTkCheckBox(display_frame, text=CHK_SHOW_IDS,
                        variable=show_ids_var).pack(anchor='w')

        name_order_row = ctk.CTkFrame(display_frame, fg_color='transparent')
        name_order_row.pack(anchor='w', pady=(6, 0))
        ctk.CTkLabel(name_order_row, text=LBL_NAME_FORMAT).pack(
            side='left', padx=(0, 8))
        name_order_var = tk.StringVar(value=self._name_order)
        _radiobutton(name_order_row, text=NAME_FIRST_LAST,
                     variable=name_order_var, value='first_last').pack(side='left', padx=(0, 8))
        _radiobutton(name_order_row, text=NAME_LAST_FIRST,
                     variable=name_order_var, value='last_first').pack(side='left')

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
            self.show_ids.set(show_ids_var.get())
            self._config.set_show_ids(show_ids_var.get())
            self._name_order = name_order_var.get()
            self._config.set_name_order(self._name_order)
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

        self._fit_window_to_content(win, min_w=500, min_h=420)
        win.deiconify()
        win.after(50, win.focus_force)

    def _resource_path(self, filename):
        """Locate a bundled resource whether running from source or PyInstaller."""
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, filename)

    def _show_how_to_use(self):
        """Open the help documentation window."""
        self._show_file_window(
            WIN_HOW_TO_USE, self._resource_path('docs/HELP.md'), markdown=True)

    def _show_keyboard_shortcuts(self):
        """Open the keyboard shortcuts reference window."""
        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(WIN_KEYBOARD_SHORTCUTS)
        win.transient(self.root)
        win.grab_set()
        win.resizable(True, True)
        win.bind('<Escape>', lambda *_: win.destroy())

        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=16, pady=(16, 8))

        tree_frame = ctk.CTkFrame(outer, fg_color='transparent')
        tree_frame.pack(fill='both', expand=True)

        tree = ttk.Treeview(tree_frame, columns=('key', 'action'),
                            show='headings', selectmode='browse',
                            height=len(KEYBOARD_SHORTCUT_ROWS))
        tree.heading('key', text=COL_SHORTCUT)
        tree.heading('action', text=COL_ACTION)
        tree.column('key', width=90, minwidth=70, stretch=False, anchor='center')
        tree.column('action', width=420, minwidth=200, stretch=True, anchor='w')

        is_dark = ctk.get_appearance_mode() == 'Dark'
        odd_bg  = '#2f2f2f' if is_dark else '#f5f5f5'
        tree.tag_configure('odd', background=odd_bg)

        for idx, (key, action) in enumerate(KEYBOARD_SHORTCUT_ROWS):
            tree.insert('', 'end', values=(key, action),
                        tags=('odd',) if idx % 2 else ())

        vsb = ctk.CTkScrollbar(tree_frame, orientation='vertical',
                               command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        ctk.CTkFrame(win, height=1,
                     fg_color=('gray70', 'gray30')).pack(fill='x')
        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=8)
        ctk.CTkButton(btn_frame, text=BTN_CLOSE, width=80,
                      command=win.destroy).pack(side='right')

        self._fit_window_to_content(win, min_w=540, min_h=420)
        win.deiconify()
        win.after(50, win.focus_force)

    def _show_about(self):
        """Open the about window with version and license information."""
        self._show_file_window(
            WIN_ABOUT,
            self._resource_path('docs/LICENSE.md'), markdown=True,
            preamble=f"# {APP_TITLE}  v{self._version} ({self._release_date})\n\n",
        )

    def _show_privacy_policy(self):
        """Open the privacy policy documentation window."""
        self._show_file_window(
            WIN_PRIVACY_POLICY,
            self._resource_path('docs/PRIVACY_POLICY.md'), markdown=True,
        )

    def _show_file_window(self, title, filepath, markdown=False, preamble=""):
        """Open a modal text window for a bundled documentation file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = preamble + f.read()
        except OSError as e:
            messagebox.showerror(
                ERR_FILE_NOT_FOUND_TITLE,
                ERR_FILE_NOT_FOUND_MSG.format(path=filepath, error=e))
            return

        win = ctk.CTkToplevel(self.root)
        win.withdraw()
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.bind('<Escape>', lambda *_: win.destroy())

        is_dark = ctk.get_appearance_mode() == 'Dark'
        code_bg = '#3a3a3a' if is_dark else '#f0f0f0'

        ui_size = self._FONT_SIZES[self._font_size_pref]['ui']
        ui_family = tkfont.nametofont('TkDefaultFont').actual()['family']
        text = ctk.CTkTextbox(win, wrap='word', activate_scrollbars=True,
                              font=ctk.CTkFont(family=ui_family, size=ui_size))
        text._textbox.configure(padx=12, pady=8)
        text.pack(fill='both', expand=True)

        base_dir = os.path.dirname(os.path.abspath(filepath))

        def _set_state(enabled):
            if sys.platform == 'darwin':
                if enabled:
                    text._textbox.unbind('<Key>')
                else:
                    text._textbox.bind('<Key>', lambda *_: 'break')
            else:
                text.configure(state='normal' if enabled else 'disabled')

        def _nav_handler(url):
            if not url.startswith(('http://', 'https://')) and url.endswith('.md'):
                target = os.path.normpath(os.path.join(base_dir, url))
                try:
                    with open(target, 'r', encoding='utf-8') as f:
                        new_content = f.read()
                except OSError:
                    webbrowser.open(url)
                    return
                win.title(os.path.splitext(os.path.basename(target))[0]
                          .replace('_', ' ').title())
                for tag in list(text._textbox.tag_names()):
                    if tag.startswith('_url_'):
                        text._textbox.tag_delete(tag)
                text._link_count = 0
                _set_state(True)
                text.delete('1.0', 'end')
                render_markdown(
                    text, new_content, self._link_color,
                    url_handler=_nav_handler, code_bg=code_bg)
                _set_state(False)
                text.yview_moveto(0)
            else:
                webbrowser.open(url)

        if markdown:
            render_markdown(text, content, self._link_color,
                            url_handler=_nav_handler, code_bg=code_bg)
        else:
            text.insert('1.0', content)

        if sys.platform == 'darwin':
            text._textbox.bind('<Key>', lambda *_: 'break')
        else:
            text.configure(state='disabled')

        # Thin separator
        ctk.CTkFrame(win, height=1, fg_color=("gray70", "gray30")).pack(fill='x')

        btn_frame = ctk.CTkFrame(win, fg_color='transparent')
        btn_frame.pack(fill='x', padx=12, pady=8)
        ctk.CTkButton(btn_frame, text=BTN_CLOSE, width=80,
                      command=win.destroy).pack(side='right')

        win.bind('<Up>', lambda *_: text.yview_scroll(-1, 'units') or 'break')
        win.bind('<Down>', lambda *_: text.yview_scroll(1, 'units') or 'break')
        win.bind('<Prior>', lambda *_: text.yview_scroll(-1, 'pages') or 'break')
        win.bind('<Next>', lambda *_: text.yview_scroll(1, 'pages') or 'break')
        win.bind('<Home>', lambda *_: text.yview_moveto(0) or 'break')
        win.bind('<End>', lambda *_: text.yview_moveto(1) or 'break')

        self._fit_window_to_content(
            win,
            min_w=500,
            min_h=300,
            preferred_w=820,
            preferred_h=640,
        )
        win.deiconify()
        win.focus_set()
